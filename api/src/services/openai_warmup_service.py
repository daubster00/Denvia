"""OpenAI 워밍업 서비스 — 일정 주기로 최소 토큰 핑을 보내 클라이언트 연결과 라우팅을 활성 상태로 유지.

마스터 관리자만 시작/정지할 수 있으며, 프로세스 단위 싱글톤 asyncio task로 동작한다.
워커가 여러 인스턴스로 늘어나면 인스턴스별로 독립 실행된다 (인스턴스별 토글이 아님 — 첫
인스턴스가 핑을 보내는 동안 나머지도 동일하게 보낸다는 의미). 단일 dev 컨테이너에서는
한 개 루프만 돈다.

설계 메모:
- 90초 주기는 인스턴스 변수로 보관 — 향후 admin 가 조절 가능.
- 모델은 ``gpt-4o-mini`` 고정 — reasoning 모델(o3-/o4-)은 내부 추론 토큰을 소비해
  "1 토큰 수준" 약속을 깬다. 워밍업은 항상 일반 chat 모델로 쏘아야 비용이 일정하다.
- 결과(usage, 마지막 핑 시각, 마지막 에러)는 in-memory 로만 보관. SSE/Redis 미사용.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import structlog

logger = structlog.get_logger(__name__)


# 워밍업 전용 — 일반 chat 모델로 고정해 reasoning 토큰 소비를 막는다.
WARMUP_MODEL = "gpt-4o-mini"
WARMUP_INTERVAL_SECONDS = 90
WARMUP_PROMPT = "hi"  # 입력도 1~2 토큰으로 최소화


@dataclass
class WarmupStatus:
    running: bool
    started_at: datetime | None
    last_ping_at: datetime | None
    last_ping_latency_ms: int | None
    last_ping_ok: bool | None
    last_error: str | None
    total_pings: int
    total_failures: int
    interval_seconds: int
    model: str


@dataclass
class _State:
    task: asyncio.Task | None = None
    started_at: datetime | None = None
    last_ping_at: datetime | None = None
    last_ping_latency_ms: int | None = None
    last_ping_ok: bool | None = None
    last_error: str | None = None
    total_pings: int = 0
    total_failures: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


_state = _State()


async def _ping_once() -> None:
    """OpenAI 에 최소 토큰 chat completion 한 번 — 실패 시 last_error 갱신 후 swallow."""
    # 지연 import — 워밍업이 비활성일 때 openai 패키지 초기화를 피한다.
    from openai import AsyncOpenAI

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY 미설정 — 워밍업 핑을 보낼 수 없습니다.")

    client = AsyncOpenAI(api_key=api_key)
    t0 = time.perf_counter()
    try:
        await client.chat.completions.create(
            model=WARMUP_MODEL,
            messages=[{"role": "user", "content": WARMUP_PROMPT}],
            max_tokens=1,
            temperature=0.0,
        )
    finally:
        # AsyncOpenAI 내부 httpx 클라이언트 정리.
        try:
            await client.close()
        except Exception:
            pass
    latency_ms = int((time.perf_counter() - t0) * 1000)

    _state.last_ping_at = datetime.now(timezone.utc)
    _state.last_ping_latency_ms = latency_ms
    _state.last_ping_ok = True
    _state.last_error = None
    _state.total_pings += 1


async def _loop() -> None:
    """90초 간격으로 _ping_once 호출. 시작 직후 첫 핑을 즉시 보낸다."""
    logger.info("openai_warmup.loop.started", interval_seconds=WARMUP_INTERVAL_SECONDS, model=WARMUP_MODEL)
    try:
        while True:
            try:
                await _ping_once()
                logger.info(
                    "openai_warmup.ping.ok",
                    latency_ms=_state.last_ping_latency_ms,
                    total_pings=_state.total_pings,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                _state.last_ping_at = datetime.now(timezone.utc)
                _state.last_ping_ok = False
                _state.last_error = f"{type(exc).__name__}: {exc}"
                _state.total_failures += 1
                logger.warning("openai_warmup.ping.failed", error=_state.last_error)
            await asyncio.sleep(WARMUP_INTERVAL_SECONDS)
    except asyncio.CancelledError:
        logger.info("openai_warmup.loop.cancelled", total_pings=_state.total_pings, total_failures=_state.total_failures)
        raise


async def start() -> WarmupStatus:
    """워밍업 루프 시작 — 이미 실행 중이면 현재 상태만 반환."""
    async with _state.lock:
        if _state.task and not _state.task.done():
            return _build_status()
        # 새 루프 시작 시 카운터·에러는 그대로 누적 (수동 정지/재시작 추적 용도).
        _state.started_at = datetime.now(timezone.utc)
        _state.task = asyncio.create_task(_loop(), name="openai_warmup_loop")
        return _build_status()


async def stop() -> WarmupStatus:
    """워밍업 루프 정지 — 실행 중이 아니면 no-op."""
    async with _state.lock:
        task = _state.task
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("openai_warmup.loop.shutdown_error")
        _state.task = None
        _state.started_at = None
        return _build_status()


def status() -> WarmupStatus:
    return _build_status()


def _build_status() -> WarmupStatus:
    running = _state.task is not None and not _state.task.done()
    return WarmupStatus(
        running=running,
        started_at=_state.started_at if running else None,
        last_ping_at=_state.last_ping_at,
        last_ping_latency_ms=_state.last_ping_latency_ms,
        last_ping_ok=_state.last_ping_ok,
        last_error=_state.last_error,
        total_pings=_state.total_pings,
        total_failures=_state.total_failures,
        interval_seconds=WARMUP_INTERVAL_SECONDS,
        model=WARMUP_MODEL,
    )


__all__ = ["start", "stop", "status", "WarmupStatus"]
