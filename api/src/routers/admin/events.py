"""Admin SSE 채널 뼈대 — Story 5.1 (AC-10).

publish는 이 스토리에서 구현하지 않음.
실제 publish는 Story 5.2(예산 경고), 8.3(RAG rebuild), 9.2(Kill-switch)에서 추가.
"""

import asyncio
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from api.src.deps.auth import require_admin
from api.src.deps.redis import get_redis

router = APIRouter(prefix="/admin", tags=["admin-events"])


@router.get("/events")
async def admin_sse_events(
    _: Any = Depends(require_admin),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Redis pub/sub `admin:events` 채널 구독 → SSE 스트리밍."""

    async def generator():
        pubsub = redis.pubsub()
        await pubsub.subscribe("admin:events")
        try:
            while True:
                msg = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )
                if msg and msg["type"] == "message":
                    data = msg["data"]
                    if isinstance(data, bytes):
                        data = data.decode()
                    yield f"data: {data}\n\n"
                else:
                    yield ": heartbeat\n\n"
                    await asyncio.sleep(15)
        finally:
            await pubsub.unsubscribe("admin:events")
            await pubsub.aclose()

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
