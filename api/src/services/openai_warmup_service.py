"""OpenAI 워밍업 서비스 — 실제 chat 경로(LangChain ChatOpenAI)와 동일한 httpx 풀을
일정 주기 ping 으로 따뜻하게 유지한다.

설계 핵심 (2026-05-29 재작성):
- ping 은 ``openai.AsyncOpenAI`` 가 아니라 실제 chat 이 쓰는 ``langchain_openai.ChatOpenAI``
  인스턴스로 보낸다. 두 라이브러리는 내부 httpx 클라이언트가 다르고, 매 ping 마다 클라이언트를
  새로 만들면 TLS 핸드셰이크가 매번 발생해 keep-alive 효과가 0 이 된다. 이번 재작성은
  ``ChatOpenAI`` 인스턴스를 모듈 전역으로 캐시하고, 실제 chat 이 그 풀과 같은 라이브러리
  경로를 타도록 만든다.
- 모델은 admin/settings 에서 지정한 ``runtime:chat_model`` 을 매 ping 마다 읽는다. 관리자가
  모델을 바꾸면 다음 ping 부터 새 모델을 데우고, 캐시된 ChatOpenAI 인스턴스도 새로 만든다.
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
# 최소 비용 핑 — 입력 1~2 토큰, 출력 1 토큰.
WARMUP_PROMPT = "hi"
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
    # 마지막으로 ping 에 사용한 모델 — 표시/상태용. 실제 모델 결정은 매 ping 마다 Redis 조회.
    last_model: str | None = None
    # 캐시된 LangChain ChatOpenAI 인스턴스 — 실제 chat 과 같은 httpx 풀을 공유하려는 목적.
    # 모델이 바뀌면 무효화하고 새로 만든다. (cached_model, llm) 튜플.
    cached_llm: tuple[str, object] | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


_state = _State()


async def _resolve_chat_model() -> str:
    """admin/settings 의 ``runtime:chat_model`` 을 읽는다.

    Redis 미설정/장애 시 ``DEFAULT_CHAT_MODEL`` (o4-mini). 화이트리스트 강제는 admin UI 가 이미 검증.
    """
    from api.src.services.runtime_config_service import ALLOWED_CHAT_MODELS, DEFAULT_CHAT_MODEL

    try:
        r = aioredis.from_url(
            settings.redis_url,
            db=REDIS_DB_RUNTIME_CONFIG,
            decode_responses=True,
        )
        async with r:
            raw = await r.get("runtime:chat_model")
    except Exception as exc:
        logger.warning("openai_warmup.chat_model_read_failed", error=str(exc))
        return DEFAULT_CHAT_MODEL

    if raw and raw in ALLOWED_CHAT_MODELS:
        return raw
    return DEFAULT_CHAT_MODEL


def _get_or_build_llm(model: str):
    """캐시된 LangChain ChatOpenAI 인스턴스 반환 — 모델이 바뀌면 재생성.

    실제 chat 경로(``build_chat_llm``) 와 동일한 라이브러리·동일한 클래스로 만든다.
    매 ping 마다 같은 인스턴스를 재사용함으로써 ChatOpenAI 내부의 httpx 클라이언트(=keep-alive
    풀)가 따뜻한 상태로 유지된다. 실제 chat 요청도 같은 ChatOpenAI 클래스를 쓰므로 OpenAI
    측 라우팅·로컬 TLS 세션 캐시·DNS 캐시가 공통으로 데워진다.
    """
    from api.src.integrations.openai.client import build_chat_llm

    cached = _state.cached_llm
    if cached is not None and cached[0] == model:
        return cached[1]

    # streaming=False — 워밍업은 콜백/스트리밍 인프라를 거치지 않고 짧게 끝낸다.
    # max_tokens=1 — 출력 1 토큰. reasoning 모델(o3-/o4-)도 build_chat_llm 가 temperature 를
    # 빼고 max_tokens 만 전달하도록 처리해 둠. reasoning 토큰이 일부 소비되지만 비용 영향 미미.
    llm = build_chat_llm(
        streaming=False,
        callbacks=None,
        temperature=0.0,
        max_tokens=1,
        model_name=model,
    )
    _state.cached_llm = (model, llm)
    return llm


async def _ping_once() -> None:
    """LangChain ChatOpenAI 로 1 토큰 chat completion 한 번.

    Redis 에서 현재 chat_model 을 읽고 캐시된 LLM 인스턴스를 재사용. 모델이 바뀌어 있으면
    캐시 무효화 후 재생성. 실패는 last_error 갱신 후 swallow (loop 가 계속 돈다).
    """
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY 미설정 — 워밍업 핑을 보낼 수 없습니다.")

    model = await _resolve_chat_model()
    llm = _get_or_build_llm(model)

    t0 = time.perf_counter()
    # ChatOpenAI.ainvoke — 동기 invoke 의 async 버전. 내부에서 openai.AsyncOpenAI 의 httpx
    # async 클라이언트를 거치며, 인스턴스 캐시 덕분에 keep-alive 풀이 유지된다.
    await llm.ainvoke(WARMUP_PROMPT)
    latency_ms = int((time.perf_counter() - t0) * 1000)

    _state.last_ping_at = datetime.now(timezone.utc)
    _state.last_ping_latency_ms = latency_ms
    _state.last_ping_ok = True
    _state.last_error = None
    _state.total_pings += 1
    _state.last_model = model


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
        # 캐시된 LLM 인스턴스도 정지 시 비워서, 다음 start 가 현재 모델로 새로 만들도록 한다.
        _state.cached_llm = None
        if persist:
            await _persist_enabled(False)
        return _build_status()


def status() -> WarmupStatus:
    return _build_status()


def _build_status() -> WarmupStatus:
    running = _state.task is not None and not _state.task.done()
    # 표시용 모델 — 마지막 ping 에 쓴 모델이 가장 정확. 아직 한 번도 안 갔으면 캐시·기본값.
    from api.src.services.runtime_config_service import DEFAULT_CHAT_MODEL

    display_model = (
        _state.last_model
        or (_state.cached_llm[0] if _state.cached_llm else None)
        or DEFAULT_CHAT_MODEL
    )
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
