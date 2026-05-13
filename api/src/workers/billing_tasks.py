"""Celery 결제 배치 태스크 — Story 3.3 자동 갱신 + Story 3.4 결제 실패 재시도."""

import asyncio

import structlog

from api.src.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(name="billing.auto_renew_scan", bind=True, max_retries=0)
def auto_renew_scan(self) -> dict:
    """매일 04:00 KST — 만료 예정 활성 구독 스캔 후 charge_renewal 개별 태스크 enqueue."""
    return asyncio.run(_scan_async())


@celery_app.task(name="billing.charge_renewal", bind=True, max_retries=0)
def charge_renewal(self, subscription_id: int) -> dict:
    """개별 구독 자동 갱신 — PG 결제 + DB 업데이트 + 알림 + 실패 시 retry enqueue."""
    return asyncio.run(_charge_async(subscription_id))


# ── 비동기 내부 구현 ─────────────────────────────────────────────────────────

async def _scan_async() -> dict:
    from api.src.models.base import async_session_factory
    from api.src.services.billing_service import scan_renewals

    async with async_session_factory() as db:
        return await scan_renewals(db)


async def _charge_async(subscription_id: int) -> dict:
    from api.src.models.base import async_session_factory
    from api.src.services.billing_service import charge_renewal as svc_charge

    async with async_session_factory() as db:
        return await svc_charge(subscription_id, db)


# ── Story 3.4 ────────────────────────────────────────────────────────────────


@celery_app.task(name="billing.retry_payment", bind=True, max_retries=0)
def retry_payment_task(self, payment_id: int, attempt: int = 2) -> dict:
    """결제 실패 재시도 — Story 3.3이 countdown=86400으로 호출 시 attempt 미전달 → 기본값 2."""
    return asyncio.run(_retry_payment_async(payment_id, attempt))


async def _retry_payment_async(payment_id: int, attempt: int) -> dict:
    from api.src.models.base import async_session_factory
    from api.src.services.billing_service import retry_payment as svc_retry

    async with async_session_factory() as db:
        return await svc_retry(payment_id, attempt, db)


# ── Story 3.5 ────────────────────────────────────────────────────────────────


@celery_app.task(name="billing.finalize_cancellations", bind=True, max_retries=0)
def finalize_cancellations_task(self) -> dict:
    """매시 15분 KST — cancel_pending && current_period_end<=now 일괄 종료."""
    return asyncio.run(_finalize_async())


async def _finalize_async() -> dict:
    from api.src.models.base import async_session_factory
    from api.src.services.billing_service import (
        finalize_cancellations as svc_finalize,
    )

    async with async_session_factory() as db:
        return await svc_finalize(db)


# ── Story 9.2 — kill-switch 정지 기간 자동 구독 연장 ─────────────────────────


@celery_app.task(
    name="billing.extend_subscriptions_for_killswitch_duration",
    bind=True,
    max_retries=0,
)
def extend_subscriptions_for_killswitch_duration(
    self, killswitch_state_id: int
) -> dict:
    """수동 비상 정지 해제 시 자동 enqueue — 정지 기간만큼 활성 구독 만료일 연장."""
    return asyncio.run(_extend_subscriptions_async(killswitch_state_id))


async def _extend_subscriptions_async(killswitch_state_id: int) -> dict:
    from api.src.models.base import async_session_factory
    from api.src.services.billing_service import extend_active_subscriptions

    async with async_session_factory() as db:
        return await extend_active_subscriptions(killswitch_state_id, db)
