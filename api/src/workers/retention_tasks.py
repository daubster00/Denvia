"""Retention 태스크 — 오래된 감사 로그 삭제 (Story 5.1, NFR-S7)."""

import asyncio

import structlog
from sqlalchemy import text

from api.src.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(name="retention_tasks.delete_old_audit_logs", bind=True)
def delete_old_audit_logs(self) -> dict:
    """audit_logs 중 1년 이상 된 레코드 삭제 — 매일 03:00 KST."""
    return asyncio.run(_delete_old_audit_logs_async())


async def _delete_old_audit_logs_async() -> dict:
    from api.src.models.base import async_session_factory

    async with async_session_factory() as session:
        result = await session.execute(
            text("DELETE FROM audit_logs WHERE created_at < NOW() - INTERVAL '1 year'")
        )
        await session.commit()
        deleted = result.rowcount

    logger.info("retention_tasks.delete_old_audit_logs.done", deleted=deleted)
    return {"deleted": deleted}
