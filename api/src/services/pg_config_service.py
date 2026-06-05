"""토스 PG 설정 서비스 — Redis DB 3 SSOT, env 폴백.

관리자 페이지 `/admin/settings/payment` 에서 4개 키(test/live × client/secret) +
모드 토글(test|live)을 편집한다. 응답은 항상 마스킹된 형태로 내려가고,
수정 시 빈 값/공백만 들어오면 해당 키는 건드리지 않는다(부분 업데이트).

`get_pg_provider()` 가 이 모듈의 동기 헬퍼 `resolve_active_toss_secret_sync` 를
호출해서 활성 secret 을 얻는다. Redis 미설정 시 ``settings.toss_secret_key`` 폴백.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from redis.asyncio import Redis as AsyncRedis

# Redis 키 — 다른 runtime:* 와 동일한 namespace, db=REDIS_DB_RUNTIME_CONFIG(3).
KEY_MODE = "runtime:pg:mode"
KEY_TEST_CLIENT = "runtime:pg:toss_test_client_key"
KEY_TEST_SECRET = "runtime:pg:toss_test_secret_key"
KEY_LIVE_CLIENT = "runtime:pg:toss_live_client_key"
KEY_LIVE_SECRET = "runtime:pg:toss_live_secret_key"

MODE_TEST = "test"
MODE_LIVE = "live"
DEFAULT_MODE = MODE_TEST  # 토스 심사 통과 전까지 안전 기본값
ALLOWED_MODES: tuple[str, ...] = (MODE_TEST, MODE_LIVE)

TossMode = Literal["test", "live"]


@dataclass(frozen=True)
class TossPgKeyView:
    """관리자 응답용 단일 키 표시 — 원본 노출 없이 마스킹 + 존재 여부만."""

    masked: str          # 예: "test_ck_••••wXyZ"  (값이 없으면 빈 문자열)
    has_value: bool      # Redis/env 모두 비어있으면 False


@dataclass(frozen=True)
class TossPgSnapshot:
    """관리자 GET 응답 묶음."""

    mode: str
    test_client: TossPgKeyView
    test_secret: TossPgKeyView
    live_client: TossPgKeyView
    live_secret: TossPgKeyView


def mask_key(value: str | None) -> str:
    """키 마스킹 — 앞 4자 + ····· + 뒤 4자.

    토스 키는 `test_ck_xxxx...`, `live_sk_xxxx...` 같은 접두사를 가지므로,
    구분에 필요한 접두사는 그대로 보여주고 본체만 가린다. 너무 짧으면 모두 가림.
    """
    if not value:
        return ""
    v = value.strip()
    if len(v) <= 8:
        return "•" * len(v)
    # 접두사(test_ck_/live_sk_ 등) 포함 앞 8자 노출 + 뒤 4자 노출.
    return f"{v[:8]}••••{v[-4:]}"


async def _get_str(redis_runtime: AsyncRedis, key: str) -> str:
    """Redis GET — 바이트/문자열 호환, 없으면 빈 문자열."""
    raw = await redis_runtime.get(key)
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        return raw.decode("utf-8")
    return str(raw)


async def get_mode(redis_runtime: AsyncRedis) -> str:
    raw = await _get_str(redis_runtime, KEY_MODE)
    if raw in ALLOWED_MODES:
        return raw
    return DEFAULT_MODE


async def get_snapshot(redis_runtime: AsyncRedis) -> TossPgSnapshot:
    """관리자 페이지 prefill용 — 4개 키 모두 마스킹 + 모드.

    env 폴백 값까지 합쳐서 `has_value` 를 결정한다. env 만 있고 Redis 가 비어
    있어도 결제는 동작하므로 관리자에게 "값이 있음"으로 보여줘야 혼동이 없다.
    """
    from api.src.settings import settings

    mode = await get_mode(redis_runtime)

    test_client_redis = await _get_str(redis_runtime, KEY_TEST_CLIENT)
    test_secret_redis = await _get_str(redis_runtime, KEY_TEST_SECRET)
    live_client_redis = await _get_str(redis_runtime, KEY_LIVE_CLIENT)
    live_secret_redis = await _get_str(redis_runtime, KEY_LIVE_SECRET)

    # env 폴백 — settings.toss_secret_key 는 모드 분리 없이 하나뿐이므로
    # 현재 모드 쪽의 secret 빈자리에 폴백으로 노출. client_key 쪽 env 폴백은
    # 별도 존재하지 않음(프론트 빌드 시 env 사용했지만 이제는 Redis SSOT 로 전환).
    env_secret = (settings.toss_secret_key or "").strip()

    def _view(redis_val: str, env_val: str = "") -> TossPgKeyView:
        display = redis_val or env_val
        return TossPgKeyView(
            masked=mask_key(display),
            has_value=bool(display),
        )

    test_secret_env = env_secret if mode == MODE_TEST else ""
    live_secret_env = env_secret if mode == MODE_LIVE else ""

    return TossPgSnapshot(
        mode=mode,
        test_client=_view(test_client_redis),
        test_secret=_view(test_secret_redis, test_secret_env),
        live_client=_view(live_client_redis),
        live_secret=_view(live_secret_redis, live_secret_env),
    )


async def set_mode(redis_runtime: AsyncRedis, mode: str) -> str:
    if mode not in ALLOWED_MODES:
        raise ValueError(f"지원하지 않는 모드입니다: {mode}. 허용: {', '.join(ALLOWED_MODES)}")
    await redis_runtime.set(KEY_MODE, mode)
    return mode


async def set_key(redis_runtime: AsyncRedis, key: str, value: str) -> None:
    """단일 키 저장. 빈 문자열/None 은 호출자가 거르도록(부분 업데이트)."""
    if key not in (KEY_TEST_CLIENT, KEY_TEST_SECRET, KEY_LIVE_CLIENT, KEY_LIVE_SECRET):
        raise ValueError(f"알 수 없는 PG 키: {key}")
    await redis_runtime.set(key, value.strip())


async def get_active_client_key(redis_runtime: AsyncRedis) -> tuple[str, str]:
    """현재 활성 모드의 client_key (프론트 노출용) + 모드 반환.

    Redis 미설정 시 빈 문자열 반환 — 호출자가 안내 메시지로 처리.
    """
    mode = await get_mode(redis_runtime)
    key_name = KEY_LIVE_CLIENT if mode == MODE_LIVE else KEY_TEST_CLIENT
    client_key = await _get_str(redis_runtime, key_name)
    return (client_key, mode)


# ─────────────────────────────────────────────────────────────────────────────
# 동기 헬퍼 — get_pg_provider() 가 호출. sync Redis 클라이언트 캐시 + env 폴백.
# 6개 결제 호출 사이트가 모두 sync 시그니처로 get_pg_provider() 를 부르므로
# 여기서 async 로 끌어올리지 않고 sync 로 짧게 Redis 한 번 읽고 끝낸다.
# ─────────────────────────────────────────────────────────────────────────────

import redis as _sync_redis_pkg  # noqa: E402

_sync_client: _sync_redis_pkg.Redis | None = None


def _get_sync_client() -> _sync_redis_pkg.Redis:
    global _sync_client
    if _sync_client is None:
        from api.src.settings import REDIS_DB_RUNTIME_CONFIG, settings

        _sync_client = _sync_redis_pkg.Redis.from_url(
            settings.redis_url,
            db=REDIS_DB_RUNTIME_CONFIG,
            decode_responses=True,
            socket_timeout=2.0,
            socket_connect_timeout=2.0,
        )
    return _sync_client


def reset_sync_client_for_tests() -> None:
    """테스트 fixture 가 Redis URL을 바꿀 때 호출."""
    global _sync_client
    _sync_client = None


def resolve_active_toss_secret_sync() -> str:
    """현재 모드의 활성 토스 secret_key 를 동기 반환. Redis → env 순.

    Redis 연결 실패 시 조용히 env 로 폴백 — 결제 경로가 Redis 가용성에
    의존하지 않게 한다.
    """
    from api.src.settings import settings

    env_secret = (settings.toss_secret_key or "").strip()

    try:
        client = _get_sync_client()
        mode = client.get(KEY_MODE) or DEFAULT_MODE
        if mode not in ALLOWED_MODES:
            mode = DEFAULT_MODE
        key_name = KEY_LIVE_SECRET if mode == MODE_LIVE else KEY_TEST_SECRET
        redis_secret = client.get(key_name)
        if redis_secret:
            return str(redis_secret).strip()
    except Exception:
        # 로그는 호출자 측 어댑터에서 결제 실패 시 자연스럽게 남는다.
        pass

    return env_secret
