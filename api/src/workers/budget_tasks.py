"""Story 5.2 — Celery Beat 매시간 예산 임계 감시 + auto kill-switch."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.src.integrations.messaging.adapters.stub import StubMessagingAdapter
from api.src.integrations.messaging.notification_service import NotificationService, SendResult
from api.src.models.notification_queue import STATUS_SENT
from api.src.models.budget_threshold import BudgetThreshold
from api.src.models.killswitch_state import KillswitchState, MODE_AUTO_FREE_ONLY
from api.src.models.user import User
from api.src.services.budget_service import get_current_month_snapshot
from api.src.settings import REDIS_DB_CELERY, settings
from api.src.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(name="budget_tasks.check_thresholds")
def check_thresholds() -> dict:
    """매시간 정시 호출 — 동기 wrapper."""
    return asyncio.run(_check_thresholds_async())


async def _check_thresholds_async() -> dict:
    import redis.asyncio as aioredis

    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    redis = aioredis.from_url(
        f"{settings.redis_url}/{REDIS_DB_CELERY}", decode_responses=True
    )
    try:
        notification = _build_notification_service(session_factory, redis)
        async with session_factory() as session:
            snapshot = await get_current_month_snapshot(session)
            await session.commit()

            ym = snapshot.year_month
            spent = snapshot.spent_usd
            percent = snapshot.percent
            limit = snapshot.monthly_limit_usd

            admin_user, admin_phone = await _resolve_admin_target(session)

            row = (await session.execute(
                select(BudgetThreshold).where(BudgetThreshold.year_month == ym)
            )).scalar_one()

            actions: list[str] = []

            # 80% 임계
            if percent >= 80 and row.warning_80_sent_at is None:
                send_result = await _try_notify(
                    notification, admin_user, admin_phone,
                    "admin.budget_warning.80",
                    {"percent": f"{percent:.2f}", "spent_usd": f"{spent:.2f}", "limit_usd": f"{limit:.2f}"},
                    f"budget.warn80:{ym}",
                )
                if send_result and send_result.status == STATUS_SENT:
                    row.warning_80_sent_at = datetime.now(timezone.utc)
                    await session.commit()
                await _publish(redis, {
                    "type": "budget_warning",
                    "threshold": 80,
                    "spent_usd": float(spent),
                    "percent": percent,
                })
                actions.append("warn80")

            # 95% 임계
            if percent >= 95 and row.warning_95_sent_at is None:
                send_result = await _try_notify(
                    notification, admin_user, admin_phone,
                    "admin.budget_warning.95",
                    {"percent": f"{percent:.2f}", "spent_usd": f"{spent:.2f}", "limit_usd": f"{limit:.2f}"},
                    f"budget.warn95:{ym}",
                )
                if send_result and send_result.status == STATUS_SENT:
                    row.warning_95_sent_at = datetime.now(timezone.utc)
                    await session.commit()
                await _publish(redis, {
                    "type": "budget_warning",
                    "threshold": 95,
                    "spent_usd": float(spent),
                    "percent": percent,
                })
                actions.append("warn95")

            # 100% → auto_free_only kill-switch
            if percent >= 100 and row.killswitch_triggered_at is None:
                insert_stmt = (
                    pg_insert(KillswitchState)
                    .values(
                        mode=MODE_AUTO_FREE_ONLY,
                        reason=f"auto:budget_hard_cap_{ym}",
                    )
                    .on_conflict_do_nothing(
                        index_elements=["mode"],
                        index_where=KillswitchState.deactivated_at.is_(None),
                    )
                )
                await session.execute(insert_stmt)
                row.killswitch_triggered_at = datetime.now(timezone.utc)
                await session.commit()
                logger.warning(
                    "killswitch.auto_activated",
                    mode=MODE_AUTO_FREE_ONLY,
                    year_month=ym,
                    spent_usd=float(spent),
                    percent=percent,
                )
                await _try_notify(
                    notification, admin_user, admin_phone,
                    "admin.budget_hard_cap_reached",
                    {"limit_usd": f"{limit:.2f}"},
                    f"budget.hardcap:{ym}",
                )
                await _publish(redis, {
                    "type": "killswitch_status",
                    "mode": MODE_AUTO_FREE_ONLY,
                    "active": True,
                })
                actions.append("hardcap")

            # 자동 해제 (< 100%)
            if percent < 100:
                active = (await session.execute(
                    select(KillswitchState).where(
                        KillswitchState.mode == MODE_AUTO_FREE_ONLY,
                        KillswitchState.deactivated_at.is_(None),
                    )
                )).scalars().all()
                if active:
                    for ks in active:
                        ks.deactivated_at = datetime.now(timezone.utc)
                    await session.commit()
                    await _publish(redis, {
                        "type": "killswitch_status",
                        "mode": MODE_AUTO_FREE_ONLY,
                        "active": False,
                    })
                    actions.append("hardcap_release")

            return {"year_month": ym, "percent": percent, "actions": actions}
    finally:
        await redis.aclose()
        await engine.dispose()


async def _resolve_admin_target(session) -> tuple[User | None, str | None]:
    env_phone = settings.denvia_admin_phone
    if env_phone:
        admin = (await session.execute(
            select(User).where(User.role == "admin").order_by(User.id).limit(1)
        )).scalar_one_or_none()
        if admin:
            return admin, env_phone
    admin = (await session.execute(
        select(User).where(User.role == "admin", User.phone.is_not(None))
        .order_by(User.id).limit(1)
    )).scalar_one_or_none()
    return admin, (admin.phone if admin else None)


async def _try_notify(
    notification: NotificationService | None,
    user: User | None,
    phone: str | None,
    template: str,
    variables: dict[str, str],
    idem: str,
) -> SendResult | None:
    if user is None or phone is None or notification is None:
        logger.warning("budget.admin_phone_missing", template=template)
        return None
    try:
        return await notification.send(
            user_id=user.id,
            phone=phone,
            template_code=template,
            variables=variables,
            idempotency_key=idem,
        )
    except Exception:
        logger.error("budget.notification_failed", template=template, exc_info=True)
        return None


async def _publish(redis, payload: dict) -> None:
    try:
        await redis.publish("admin:events", json.dumps(payload))
    except Exception:
        logger.error("budget.redis_publish_failed", payload=payload, exc_info=True)


def _build_notification_service(
    session_factory: async_sessionmaker,
    redis,
) -> NotificationService:
    """HOLD-MSG 동안 stub provider 사용."""
    provider = StubMessagingAdapter()
    return NotificationService(
        provider=provider, session_factory=session_factory, redis=redis
    )
