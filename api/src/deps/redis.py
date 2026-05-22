"""Redis 비동기 클라이언트 Dep — Story 5.1 + Story 2.3 (Quota DB 4 / Runtime DB 3 분리)."""

from collections.abc import AsyncGenerator

import redis.asyncio as aioredis

from api.src.settings import (
    REDIS_DB_QUOTA,
    REDIS_DB_RATE_LIMIT,
    REDIS_DB_RUNTIME_CONFIG,
    settings,
)

_redis_pool: aioredis.Redis | None = None
_redis_quota_pool: aioredis.Redis | None = None
_redis_runtime_pool: aioredis.Redis | None = None
_redis_rate_limit_pool: aioredis.Redis | None = None


def get_redis_client() -> aioredis.Redis:
    """Redis DB 0 (default) — Celery broker·rate-limit 등."""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis_pool


def get_redis_quota_client() -> aioredis.Redis:
    """Redis DB 4 — 일일 Q&A 카운터 (quota:user:{id}:{YYYY-MM-DD})."""
    global _redis_quota_pool
    if _redis_quota_pool is None:
        _redis_quota_pool = aioredis.from_url(
            settings.redis_url, db=REDIS_DB_QUOTA, decode_responses=True
        )
    return _redis_quota_pool


def get_redis_runtime_client() -> aioredis.Redis:
    """Redis DB 3 — 관리자 편집 런타임 구성 (runtime:free_daily_quota 등)."""
    global _redis_runtime_pool
    if _redis_runtime_pool is None:
        _redis_runtime_pool = aioredis.from_url(
            settings.redis_url, db=REDIS_DB_RUNTIME_CONFIG, decode_responses=True
        )
    return _redis_runtime_pool


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    yield get_redis_client()


async def get_redis_quota() -> AsyncGenerator[aioredis.Redis, None]:
    yield get_redis_quota_client()


async def get_redis_runtime() -> AsyncGenerator[aioredis.Redis, None]:
    yield get_redis_runtime_client()


def get_redis_rate_limit_client() -> aioredis.Redis:
    """Redis DB 2 — 브루트포스 카운터·락아웃 (auth_service 의 _make_redis_rl 과 동일 DB)."""
    global _redis_rate_limit_pool
    if _redis_rate_limit_pool is None:
        _redis_rate_limit_pool = aioredis.from_url(
            settings.redis_url, db=REDIS_DB_RATE_LIMIT, decode_responses=True
        )
    return _redis_rate_limit_pool


async def get_redis_rate_limit() -> AsyncGenerator[aioredis.Redis, None]:
    yield get_redis_rate_limit_client()
