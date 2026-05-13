"""Celery 컨텐츠 스케줄 태스크 — F-502 야간 광고 차단 상태 전환 (Story 4.2)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import structlog

from api.src.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(name="content_schedule_tasks.toggle_night_block_on", bind=True)
def toggle_night_block_on(self) -> dict:
    """매일 21:00 KST 발화 — runtime:night_block_active=true."""
    return asyncio.run(_set_active(True))


@celery_app.task(name="content_schedule_tasks.toggle_night_block_off", bind=True)
def toggle_night_block_off(self) -> dict:
    """매일 08:00 KST 발화 — runtime:night_block_active=false."""
    return asyncio.run(_set_active(False))


async def _set_active(active: bool) -> dict:
    import redis.asyncio as aioredis

    from api.src.services.runtime_config_service import KEY_NIGHT_BLOCK_ACTIVE
    from api.src.settings import REDIS_DB_RUNTIME_CONFIG, settings

    redis_client = aioredis.from_url(
        f"{settings.redis_url}/{REDIS_DB_RUNTIME_CONFIG}",
        decode_responses=True,
    )
    try:
        await redis_client.set(KEY_NIGHT_BLOCK_ACTIVE, "true" if active else "false")
        logger.info(
            "content_schedule.night_block_toggled",
            active=active,
            triggered_at=datetime.now(timezone.utc).isoformat(),
        )
        return {"active": active}
    finally:
        await redis_client.aclose()
