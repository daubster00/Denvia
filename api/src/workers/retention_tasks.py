"""Retention 태스크 — 오래된 감사 로그 + 결제 데이터 + 질의응답/쪽지 삭제.

- delete_old_audit_logs: audit_logs 1년 이상 (Story 5.1 / NFR-S7) — 매일 03:00 KST
- delete_old_payments  : payments 5년 이상 (Story 9.1 / NFR-C3 / 협의서 #A-07) — 매일 03:30 KST
  payments 삭제 시 ON DELETE CASCADE로 payment_events도 함께 삭제된다.
- delete_old_qa_logs   : qa_logs 1년 이상 (처리방침 §4 "서비스 이용 로그 1년") — 매일 03:15 KST
- purge_old_inbox_messages: inbox_messages 휴지통 30일 OR 발송 1년 — 매일 03:45 KST
  · deleted_at 이 30일 이상 경과 → 영구 삭제
  · created_at 이 1년 이상 경과 → 영구 삭제(휴지통 거치지 않은 묵은 쪽지)
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


@celery_app.task(name="retention_tasks.delete_old_qa_logs", bind=True)
def delete_old_qa_logs(self) -> dict:
    """qa_logs 중 1년 이상 된 레코드 삭제 — 매일 03:15 KST.

    처리방침 §4: "서비스 이용 로그(질의 내역) 1년". 사용자 질문 원문 + 답변이
    이 테이블에 보관되므로 약속된 기간을 초과해서 보관되지 않도록 한다.
    """
    return asyncio.run(_delete_old_qa_logs_async())


async def _delete_old_qa_logs_async() -> dict:
    from api.src.models.base import async_session_factory

    async with async_session_factory() as session:
        result = await session.execute(
            text("DELETE FROM qa_logs WHERE created_at < NOW() - INTERVAL '1 year'")
        )
        await session.commit()
        deleted = result.rowcount

    logger.info("retention_tasks.delete_old_qa_logs.done", deleted=deleted)
    return {"deleted": deleted}


@celery_app.task(name="retention_tasks.purge_old_inbox_messages", bind=True)
def purge_old_inbox_messages(self) -> dict:
    """inbox_messages 영구 삭제 — 매일 03:45 KST.

    두 조건 중 하나라도 만족하면 삭제(OR):
    - 사용자가 휴지통에 보낸 지 30일 경과 (deleted_at < NOW - 30d)
    - 발송 후 1년 경과 (created_at < NOW - 1y) — 사용자가 안 지운 묵은 쪽지

    notice/popup 경로 row도 동일 정책으로 정리한다(공지 본문 자체는 notices
    테이블에 별도 보존되므로 사용자별 사본만 삭제).
    """
    return asyncio.run(_purge_old_inbox_messages_async())


async def _purge_old_inbox_messages_async() -> dict:
    from api.src.models.base import async_session_factory

    async with async_session_factory() as session:
        result = await session.execute(
            text(
                "DELETE FROM inbox_messages "
                "WHERE (deleted_at IS NOT NULL AND deleted_at < NOW() - INTERVAL '30 days') "
                "OR created_at < NOW() - INTERVAL '1 year'"
            )
        )
        await session.commit()
        deleted = result.rowcount

    logger.info("retention_tasks.purge_old_inbox_messages.done", deleted=deleted)
    return {"deleted": deleted}
