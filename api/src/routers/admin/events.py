"""Admin SSE 채널 — Story 5.1/8.3.

SSE `event:` 라인 삽입으로 EventSource.addEventListener("type", ...) 발화 보장.
"""

import asyncio
import json as _json
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
        last_heartbeat = asyncio.get_event_loop().time()
        try:
            while True:
                msg = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )
                if msg and msg["type"] == "message":
                    data = msg["data"]
                    if isinstance(data, bytes):
                        data = data.decode()
                    try:
                        _parsed = _json.loads(data)
                        _etype = _parsed.get("type", "message")
                        yield f"event: {_etype}\ndata: {data}\n\n"
                    except Exception:
                        yield f"data: {data}\n\n"
                else:
                    now = asyncio.get_event_loop().time()
                    if now - last_heartbeat >= 15:
                        yield ": heartbeat\n\n"
                        last_heartbeat = now
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
