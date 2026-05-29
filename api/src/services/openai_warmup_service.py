"""OpenAI 워밍업 서비스 — 실제 chat 과 동일한 RetrievalQA 경로를 일정 주기 더미 호출해
ChatOpenAI 인스턴스 캐시·httpx keep-alive 풀·LangChain lazy import 를 따뜻하게 유지한다.

설계 핵심 (2026-05-29 재작성):
- ping 은 ``query_runner.warmup_once()`` 로 위임. 이 함수가 실제 ``stream_rag_answer`` 와
  동일한 ``build_chat_llm`` 호출 + RetrievalQA 조립 + chain.invoke 를 1회 수행한다.
  ``build_chat_llm`` 의 모듈 전역 캐시(_LLM_CACHE)가 같은 옵션이면 같은 ChatOpenAI 인스턴스를
  반환하므로, 워밍업이 데우는 인스턴스 == 첫 사용자 질문이 받는 인스턴스. httpx 풀·TLS
  세션·OpenAI 측 라우팅 캐시가 공통 자산으로 살아 있다.
- 모델은 admin/settings 의 ``runtime:chat_model`` 을 매 ping 마다 다시 읽는다(``warmup_once``
  내부의 ``_load_runtime_params``). 관리자가 모델을 바꾸면 다음 ping(≤90초)부터 새 모델 풀이
  자동으로 데워진다.
- ON/OFF 토글 상태는 Redis(``runtime:openai_warmup_enabled``)에 영속화한다. 컨테이너
  재시작/재배포 후에도 lifespan 이 이 키를 읽고 자동 복원한다. 이전 in-memory only 였던
  탓에 운영 배포 한 번에 토글이 silently OFF 되던 버그를 막는다.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import redis.asyncio as aioredis
import structlog

from api.src.settings import REDIS_DB_RUNTIME_CONFIG, settings

logger = structlog.get_logger(__name__)


# 워밍업 주기 — 90초가 OpenAI 측 idle 풀 만료(보통 1~2분)와 자체 풀 keep-alive 사이에서 무난.
WARMUP_INTERVAL_SECONDS = 90
# Redis 키 — 토글 상태 영속화 (DB 3, runtime_config 와 동일 namespace).
REDIS_KEY_WARMUP_ENABLED = "runtime:openai_warmup_enabled"


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
    # 마지막으로 ping 에 사용한 모델 — 표시/상태용. 실제 모델 결정은 매 ping 마다
    # query_runner.warmup_once() 안에서 _load_runtime_params 로 다시 읽는다.
    last_model: str | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


_state = _State()


async def _ping_once() -> None:
    """실제 chat 과 100% 동일한 RetrievalQA 경로로 1회 더미 호출.

    ``query_runner.warmup_once()`` 가 실제 ``stream_rag_answer`` 와 같은 ``build_chat_llm``
    호출 + RetrievalQA 조립 + chain.invoke 를 수행한다. ``build_chat_llm`` 의 모듈 전역
    캐시(_LLM_CACHE)가 같은 옵션이면 같은 ChatOpenAI 인스턴스를 반환하므로, 워밍업이
    데워두는 인스턴스 == 첫 사용자 질문이 받는 인스턴스. 결과적으로 httpx keep-alive
    풀·TLS 세션이 ping 사이에 살아 있고, 첫 질문의 LLM TTFT cold-start 가 사라진다.

    모델은 ``runtime:chat_model`` (admin/settings) 을 매 ping 마다 다시 읽는다 — 관리자가
    모델을 바꾸면 다음 ping(≤90초)에 새 모델 ChatOpenAI 가 캐시에 자리잡고, 그 다음 사용자
    질문부터 새 모델 풀이 데워진 채로 시작한다.
    """
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY 미설정 — 워밍업 핑을 보낼 수 없습니다.")

    from api.src.rag_integration import query_runner

    t0 = time.perf_counter()
    info = await query_runner.warmup_once()
    latency_ms = int((time.perf_counter() - t0) * 1000)

    _state.last_ping_at = datetime.now(timezone.utc)
    _state.last_ping_latency_ms = latency_ms
    _state.last_ping_ok = True
    _state.last_error = None
    _state.total_pings += 1
    _state.last_model = info.get("model") or _state.last_model


async def _loop() -> None:
    """주기 ping. 시작 직후 즉시 첫 ping → asyncio.sleep(주기) 반복."""
    logger.info("openai_warmup.loop.started", interval_seconds=WARMUP_INTERVAL_SECONDS)
    try:
        while True:
            try:
                await _ping_once()
                logger.info(
                    "openai_warmup.ping.ok",
                    latency_ms=_state.last_ping_latency_ms,
                    total_pings=_state.total_pings,
                    model=_state.last_model,
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
        logger.info(
            "openai_warmup.loop.cancelled",
            total_pings=_state.total_pings,
            total_failures=_state.total_failures,
        )
        raise


async def _persist_enabled(enabled: bool) -> None:
    """Redis 에 ON/OFF 상태 영속화 — 재시작 후 복원용. 실패는 swallow (in-memory 토글은 유효)."""
    try:
        r = aioredis.from_url(
            settings.redis_url,
            db=REDIS_DB_RUNTIME_CONFIG,
            decode_responses=True,
        )
        async with r:
            if enabled:
                await r.set(REDIS_KEY_WARMUP_ENABLED, "1")
            else:
                await r.delete(REDIS_KEY_WARMUP_ENABLED)
    except Exception as exc:
        logger.warning("openai_warmup.persist_failed", enabled=enabled, error=str(exc))


async def is_persisted_enabled() -> bool:
    """lifespan 부팅 시 호출 — Redis 에 ON 상태가 남아 있으면 True 반환."""
    try:
        r = aioredis.from_url(
            settings.redis_url,
            db=REDIS_DB_RUNTIME_CONFIG,
            decode_responses=True,
        )
        async with r:
            raw = await r.get(REDIS_KEY_WARMUP_ENABLED)
    except Exception as exc:
        logger.warning("openai_warmup.persisted_state_read_failed", error=str(exc))
        return False
    return raw == "1"


async def start(*, persist: bool = True) -> WarmupStatus:
    """워밍업 루프 시작. ``persist=True`` 면 Redis 에 ON 영속화 (관리자 토글).

    lifespan 자동 복원 호출은 ``persist=False`` 로 보낸다 — 이미 Redis 에 있는 키를 다시 set 할
    필요가 없고, 멱등성 보장에도 도움."""
    async with _state.lock:
        if _state.task and not _state.task.done():
            if persist:
                await _persist_enabled(True)
            return _build_status()
        _state.started_at = datetime.now(timezone.utc)
        _state.task = asyncio.create_task(_loop(), name="openai_warmup_loop")
        if persist:
            await _persist_enabled(True)
        return _build_status()


async def stop(*, persist: bool = True) -> WarmupStatus:
    """워밍업 루프 정지. ``persist=True`` 면 Redis 에서 OFF 키 삭제.

    lifespan 종료 시에는 ``persist=False`` 로 — 컨테이너 재시작 후 자동 복원이 되어야 하므로
    정지 영속화는 관리자 명시 토글에서만 발생해야 한다."""
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
        if persist:
            await _persist_enabled(False)
        return _build_status()


def status() -> WarmupStatus:
    return _build_status()


def _build_status() -> WarmupStatus:
    running = _state.task is not None and not _state.task.done()
    # 표시용 모델 — 마지막 ping 에 쓴 모델이 가장 정확. 아직 한 번도 안 갔으면 기본값.
    from api.src.services.runtime_config_service import DEFAULT_CHAT_MODEL

    display_model = _state.last_model or DEFAULT_CHAT_MODEL
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
        model=display_model,
    )


__all__ = [
    "start",
    "stop",
    "status",
    "is_persisted_enabled",
    "WarmupStatus",
    "REDIS_KEY_WARMUP_ENABLED",
]
