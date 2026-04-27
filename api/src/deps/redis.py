"""Redis 비동기 클라이언트 Dep — Story 5.1."""

from collections.abc import AsyncGenerator

import redis.asyncio as aioredis

from api.src.settings import settings

_redis_pool: aioredis.Redis | None = None


def get_redis_client() -> aioredis.Redis:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis_pool


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    yield get_redis_client()
