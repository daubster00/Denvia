"""Retention 태스크 — 오래된 감사 로그 + 결제 데이터 삭제.

- delete_old_audit_logs: audit_logs 1년 이상 (Story 5.1 / NFR-S7) — 매일 03:00 KST
- delete_old_payments  : payments 5년 이상 (Story 9.1 / NFR-C3 / 협의서 #A-07) — 매일 03:30 KST
  payments 삭제 시 ON DELETE CASCADE로 payment_events도 함께 삭제된다.
"""

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


@celery_app.task(name="retention_tasks.delete_old_payments", bind=True)
def delete_old_payments(self) -> dict:
    """payments + payment_events 5년 이상 레코드 삭제 — 매일 03:30 KST.

    NFR-C3 / 협의서 #A-07. 탈퇴 사용자(users.withdrawn_at IS NOT NULL)도 5년은 유지한다.
    payment_events는 ON DELETE CASCADE로 자동 삭제된다(0013 마이그레이션 참조).
    """
    return asyncio.run(_delete_old_payments_async())


async def _delete_old_payments_async() -> dict:
    from api.src.models.base import async_session_factory

    async with async_session_factory() as session:
        result = await session.execute(
            text("DELETE FROM payments WHERE created_at < NOW() - INTERVAL '5 years'")
        )
        await session.commit()
        deleted = result.rowcount

    logger.info("retention_tasks.delete_old_payments.done", deleted=deleted)
    return {"deleted": deleted}
