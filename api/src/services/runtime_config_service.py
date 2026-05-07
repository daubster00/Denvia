"""서비스 전체 런타임 설정 서비스 — Redis DB 3 게이트웨이.

QA flow는 ``api.src.services.qa_service`` 의 ``_resolve_*`` helper로 동일 키들을
이미 읽고 있다. 본 모듈은 컨텐츠 관리 페이지 어드민 편집 경로 전용.
"""

from __future__ import annotations

from fastapi import Request
from redis.asyncio import Redis as AsyncRedis

from api.src.schemas.admin.runtime_config import (
    RuntimeConfigResponse,
    RuntimeConfigUpdateRequest,
)


# 4 키 — seed_runtime_config.py 와 동일한 namespace.
KEY_SHOW_SUBSCRIBE = "runtime:show_subscribe_button"
KEY_FREE_DAILY_QUOTA = "runtime:free_daily_quota"
KEY_FREE_DELAY_ENABLED = "runtime:free_delay_enabled"
KEY_FREE_DELAY = "runtime:free_delay"
# Story 7.1 — 쪽지함 미리보기 동시 노출 최대 개수 (관리자 CS 페이지에서 편집).
KEY_INBOX_PREVIEW_MAX_COUNT = "runtime:inbox_preview_max_count"

# QA flow 기본값과 일치 (qa_service.DEFAULT_FREE_DAILY_QUOTA / DEFAULT_FREE_DELAY_SECONDS).
DEFAULT_SHOW_SUBSCRIBE = True
DEFAULT_FREE_DAILY_QUOTA = 10
DEFAULT_FREE_DELAY_ENABLED = True
DEFAULT_FREE_DELAY_SECONDS = 3
DEFAULT_INBOX_PREVIEW_MAX_COUNT = 1
INBOX_PREVIEW_MAX_COUNT_MIN = 1
INBOX_PREVIEW_MAX_COUNT_MAX = 5


def _to_bool(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    return str(raw).lower() not in ("0", "false", "off", "no")


def _to_int(raw: str | None, default: int) -> int:
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


async def get_runtime_config(redis_runtime: AsyncRedis) -> RuntimeConfigResponse:
    show_raw = await redis_runtime.get(KEY_SHOW_SUBSCRIBE)
    quota_raw = await redis_runtime.get(KEY_FREE_DAILY_QUOTA)
    delay_enabled_raw = await redis_runtime.get(KEY_FREE_DELAY_ENABLED)
    delay_raw = await redis_runtime.get(KEY_FREE_DELAY)

    return RuntimeConfigResponse(
        show_subscribe_button=_to_bool(show_raw, DEFAULT_SHOW_SUBSCRIBE),
        free_daily_quota=_to_int(quota_raw, DEFAULT_FREE_DAILY_QUOTA),
        free_delay_enabled=_to_bool(delay_enabled_raw, DEFAULT_FREE_DELAY_ENABLED),
        free_delay_seconds=_to_int(delay_raw, DEFAULT_FREE_DELAY_SECONDS),
    )


async def update_runtime_config(
    request: Request,
    body: RuntimeConfigUpdateRequest,
    redis_runtime: AsyncRedis,
) -> RuntimeConfigResponse:
    before = await get_runtime_config(redis_runtime)

    await redis_runtime.set(KEY_SHOW_SUBSCRIBE, "true" if body.show_subscribe_button else "false")
    await redis_runtime.set(KEY_FREE_DAILY_QUOTA, str(body.free_daily_quota))
    await redis_runtime.set(KEY_FREE_DELAY_ENABLED, "true" if body.free_delay_enabled else "false")
    await redis_runtime.set(KEY_FREE_DELAY, str(body.free_delay_seconds))

    after = RuntimeConfigResponse(
        show_subscribe_button=body.show_subscribe_button,
        free_daily_quota=body.free_daily_quota,
        free_delay_enabled=body.free_delay_enabled,
        free_delay_seconds=body.free_delay_seconds,
    )

    request.state.audit_target_type = "runtime_config"
    request.state.audit_diff = {
        "before": before.model_dump(),
        "after": after.model_dump(),
    }

    return after


def _clamp_preview_max_count(raw: int) -> int:
    return max(
        INBOX_PREVIEW_MAX_COUNT_MIN,
        min(INBOX_PREVIEW_MAX_COUNT_MAX, raw),
    )


async def get_inbox_preview_max_count(redis_runtime: AsyncRedis) -> int:
    raw = await redis_runtime.get(KEY_INBOX_PREVIEW_MAX_COUNT)
    return _clamp_preview_max_count(_to_int(raw, DEFAULT_INBOX_PREVIEW_MAX_COUNT))


async def set_inbox_preview_max_count(
    redis_runtime: AsyncRedis, value: int
) -> int:
    clamped = _clamp_preview_max_count(value)
    await redis_runtime.set(KEY_INBOX_PREVIEW_MAX_COUNT, str(clamped))
    return clamped


# =============================================================================
# Story 5.5 — USD→KRW 환산 환율 (read-only, runtime:usd_to_krw)
# 운영자가 환율 변경 시 redis-cli SET 수동 실행. 편집 UI는 후속 스토리 책임.
# =============================================================================

KEY_USD_TO_KRW = "runtime:usd_to_krw"
DEFAULT_USD_TO_KRW = 1400
USD_TO_KRW_MIN = 1000
USD_TO_KRW_MAX = 3000


async def get_usd_to_krw(redis_runtime: AsyncRedis) -> int:
    """USD→KRW 환산 환율 조회. 미설정 또는 sanity(1000~3000) 위반 시 기본 1400."""
    raw = await redis_runtime.get(KEY_USD_TO_KRW)
    if raw is None:
        return DEFAULT_USD_TO_KRW
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_USD_TO_KRW
    if not (USD_TO_KRW_MIN <= v <= USD_TO_KRW_MAX):
        return DEFAULT_USD_TO_KRW
    return v
