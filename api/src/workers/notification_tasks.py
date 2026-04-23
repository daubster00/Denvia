"""Celery 알림 태스크 — 큐 발송 및 지연 발송 처리 (Story 4.1)."""

import asyncio
from datetime import datetime, timezone

import structlog
from sqlalchemy import select, update

from api.src.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(name="notification_tasks.dispatch_queued", bind=True, max_retries=3)
def dispatch_queued(self) -> dict:
    """status='queued' 항목을 처리한다 (Epic 3 billing 이벤트 대기열).

    Celery Beat 스케줄: 5분마다 실행 (celery_app.py 참조).
    """
    return asyncio.run(_dispatch_queued_async())


@celery_app.task(name="notification_tasks.dispatch_deferred", bind=True, max_retries=3)
def dispatch_deferred(self) -> dict:
    """status='deferred' | 'rate_limited_deferred' 항목 중 deferred_until <= now()를 처리한다.

    Celery Beat 스케줄: 매일 08:05 KST (야간 차단 해제 직후).
    추가로 매 시간 정각에 rate_limited_deferred 재처리 (celery_app.py 참조).
    """
    return asyncio.run(_dispatch_deferred_async())


# ── 비동기 내부 구현 ────────────────────────────────────────────────────────

async def _dispatch_queued_async() -> dict:
    """queued 항목을 claim → STATUS_PROCESSING → 발송한다 (2-phase dispatch).

    Phase 1: SELECT FOR UPDATE SKIP LOCKED → bulk UPDATE STATUS_PROCESSING → COMMIT
             (락 해제 후 다른 워커가 동일 행 재처리하지 않음)
    Phase 2: 락 없이 각 항목 발송 → SendResult 기반으로 기존 행 status 갱신
    """
    from api.src.integrations.messaging.notification_service import (
        SendResult,
        get_notification_service,
    )
    from api.src.models.base import async_session_factory
    from api.src.models.notification_queue import (
        STATUS_FAILED,
        STATUS_PROCESSING,
        STATUS_QUEUED,
        STATUS_SENT,
        NotificationQueue,
    )

    sent_count = 0
    failed_count = 0

    # Phase 1: atomic claim
    async with async_session_factory() as session:
        result = await session.execute(
            select(NotificationQueue)
            .where(NotificationQueue.status == STATUS_QUEUED)
            .limit(100)
            .with_for_update(skip_locked=True)
        )
        items = result.scalars().all()

        if not items:
            logger.info("notification_tasks.dispatch_queued.done", sent=0, failed=0)
            return {"sent": 0, "failed": 0}

        await session.execute(
            update(NotificationQueue)
            .where(NotificationQueue.id.in_([item.id for item in items]))
            .values(status=STATUS_PROCESSING)
        )
        await session.commit()  # lock released; STATUS_PROCESSING prevents double-claim

    # Phase 2: process without holding lock
    service = get_notification_service()

    for item in items:
        phone = await _get_user_phone(item.user_id)
        if phone is None:
            await _update_status(
                item.id,
                STATUS_FAILED,
                last_error="user phone not found or user withdrawn",
            )
            failed_count += 1
            logger.warning(
                "notification_tasks.dispatch_queued.no_phone",
                notification_id=item.id,
                user_id=item.user_id,
            )
            continue

        try:
            send_result: SendResult = await service.send(
                user_id=item.user_id,
                phone=phone,
                template_code=item.template_code,
                variables=item.variables or {},
                idempotency_key=item.idempotency_key,
            )
            await _update_status(
                item.id,
                send_result.status,
                deferred_until=send_result.deferred_until,
                last_error=send_result.error,
            )
            if send_result.status == STATUS_SENT:
                sent_count += 1
            elif send_result.status == STATUS_FAILED:
                failed_count += 1
        except Exception as exc:
            await _update_status(item.id, STATUS_FAILED, last_error=str(exc))
            failed_count += 1
            logger.error(
                "notification_tasks.dispatch_queued.error",
                notification_id=item.id,
                error=str(exc),
            )

    logger.info(
        "notification_tasks.dispatch_queued.done",
        sent=sent_count,
        failed=failed_count,
    )
    return {"sent": sent_count, "failed": failed_count}


async def _dispatch_deferred_async() -> dict:
    """deferred / rate_limited_deferred 항목 중 deferred_until <= now()를 claim → 발송한다."""
    from api.src.integrations.messaging.notification_service import (
        SendResult,
        get_notification_service,
    )
    from api.src.models.base import async_session_factory
    from api.src.models.notification_queue import (
        STATUS_DEFERRED,
        STATUS_FAILED,
        STATUS_PROCESSING,
        STATUS_RATE_LIMITED,
        STATUS_SENT,
        NotificationQueue,
    )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    sent_count = 0
    failed_count = 0

    # Phase 1: atomic claim
    async with async_session_factory() as session:
        result = await session.execute(
            select(NotificationQueue)
            .where(
                NotificationQueue.status.in_([STATUS_DEFERRED, STATUS_RATE_LIMITED]),
                NotificationQueue.deferred_until <= now,
            )
            .limit(100)
            .with_for_update(skip_locked=True)
        )
        items = result.scalars().all()

        if not items:
            logger.info("notification_tasks.dispatch_deferred.done", sent=0, failed=0)
            return {"sent": 0, "failed": 0}

        await session.execute(
            update(NotificationQueue)
            .where(NotificationQueue.id.in_([item.id for item in items]))
            .values(status=STATUS_PROCESSING)
        )
        await session.commit()  # lock released; STATUS_PROCESSING prevents double-claim

    # Phase 2: process without holding lock
    service = get_notification_service()

    for item in items:
        phone = await _get_user_phone(item.user_id)
        if phone is None:
            await _update_status(
                item.id,
                STATUS_FAILED,
                last_error="user phone not found or user withdrawn",
            )
            failed_count += 1
            logger.warning(
                "notification_tasks.dispatch_deferred.no_phone",
                notification_id=item.id,
                user_id=item.user_id,
            )
            continue

        try:
            send_result: SendResult = await service.send(
                user_id=item.user_id,
                phone=phone,
                template_code=item.template_code,
                variables=item.variables or {},
                idempotency_key=item.idempotency_key,
            )
            await _update_status(
                item.id,
                send_result.status,
                deferred_until=send_result.deferred_until,
                last_error=send_result.error,
            )
            if send_result.status == STATUS_SENT:
                sent_count += 1
            elif send_result.status == STATUS_FAILED:
                failed_count += 1
        except Exception as exc:
            await _update_status(item.id, STATUS_FAILED, last_error=str(exc))
            failed_count += 1
            logger.error(
                "notification_tasks.dispatch_deferred.error",
                notification_id=item.id,
                error=str(exc),
            )

    logger.info(
        "notification_tasks.dispatch_deferred.done",
        sent=sent_count,
        failed=failed_count,
    )
    return {"sent": sent_count, "failed": failed_count}


async def _get_user_phone(user_id: int | None) -> str | None:
    """users 테이블에서 휴대폰 번호를 조회한다."""
    if user_id is None:
        return None

    from api.src.models.base import async_session_factory
    from api.src.models.user import User

    async with async_session_factory() as session:
        result = await session.execute(
            select(User.phone).where(User.id == user_id, User.withdrawn_at.is_(None))
        )
        return result.scalar_one_or_none() or None  # 빈 문자열 전화번호 None 처리


async def _update_status(
    notification_id: int,
    status: str,
    last_error: str | None = None,
    deferred_until: datetime | None = None,
) -> None:
    """notification_queue의 status를 업데이트한다."""
    from api.src.models.base import async_session_factory
    from api.src.models.notification_queue import NotificationQueue

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    values: dict = {
        "status": status,
        "attempts": NotificationQueue.attempts + 1,
    }
    if status == "sent":
        values["sent_at"] = now
    if last_error:
        values["last_error"] = last_error
    if deferred_until is not None:
        values["deferred_until"] = deferred_until

    async with async_session_factory() as session:
        await session.execute(
            update(NotificationQueue)
            .where(NotificationQueue.id == notification_id)
            .values(**values)
        )
        await session.commit()
