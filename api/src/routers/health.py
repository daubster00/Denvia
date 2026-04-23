"""헬스체크 엔드포인트 — /healthz, /readyz."""

import redis.asyncio as aioredis
from fastapi import APIRouter
from sqlalchemy import text

from api.src.models.base import get_session
from api.src.settings import settings

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict:
    """DB와 Redis 연결 상태를 동시에 확인한다."""
    db_status = "up"
    redis_status = "up"

    # DB 헬스체크
    try:
        async for session in get_session():
            await session.execute(text("SELECT 1"))
    except Exception:
        db_status = "down"

    # Redis 헬스체크
    try:
        r = aioredis.from_url(settings.redis_url)
        await r.ping()
        await r.aclose()
    except Exception:
        redis_status = "down"

    return {"status": "ok", "db": db_status, "redis": redis_status}


@router.get("/readyz")
async def readyz() -> dict:
    """기동 준비 완료 여부를 반환한다."""
    return {"status": "ok"}
