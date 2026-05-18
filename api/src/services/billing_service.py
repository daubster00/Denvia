"""BillingService — 플랜 조회(Story 3.1) + 빌링키 발급·구독 시작(Story 3.2)."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.integrations.payment import get_pg_provider
from api.src.models.billing_key import BillingKey
from api.src.models.killswitch_state import MODE_MANUAL_TOTAL, KillswitchState
from api.src.models.payment import Payment
from api.src.models.payment_event import PaymentEvent
from api.src.models.subscription import Subscription
from api.src.models.user import User
from api.src.schemas.billing import PlanResponse
from api.src.settings import settings
from api.src.utils.fernet import decrypt_billing_key, encrypt_billing_key

logger = structlog.get_logger(__name__)

# Basic 플랜 기능 목록 — 관리자 편집 대상 아니므로 코드 상수로 관리
_FREE_FEATURES = [
    "하루 3회 Q&A",
    "기본 보험청구·행정 답변",
    "질문 재구성 제안",
]

# Pro 플랜 기능 목록
_PRO_FEATURES = [
    "무제한 Q&A",
    "심화 보험청구·행정 답변",
    "응답 속도 우선",
    "질문 재구성 제안",
    "피드백 기능",
]


def get_billing_plans() -> list[PlanResponse]:
    """구독 플랜 목록을 반환한다. 가격은 settings에서 로드 (AR 규칙: 하드코딩 금지)."""
    return [
        PlanResponse(
            tier="free",
            name="Basic",
            price_krw=0,
            period=None,
            features=_FREE_FEATURES,
            cta_label="현재 이용 중",
            is_recommended=False,
        ),
        PlanResponse(
            tier="pro",
            name="Pro",
            price_krw=settings.pro_monthly_price_krw,
            period="/ 월",
            features=_PRO_FEATURES,
            cta_label="Pro 시작하기",
            is_recommended=True,
        ),
    ]


# ── Story 3.2 ────────────────────────────────────────────────────────────────


async def _notify_first_charge(
    user: User, amount_krw: int, next_charge_at: datetime
) -> None:
    """최초 결제 성공 알림 fire-and-forget — 실패해도 결제 응답에 영향 없음."""
    try:
        from api.src.integrations.messaging.notification_service import (
            get_notification_service,
        )

        svc = get_notification_service()
        await svc.send(
            user_id=user.id,
            phone=user.phone or "",
            template_code="billing.first_charge_success",
            variables={
                "amount_krw": str(amount_krw),
                "next_charge_at": next_charge_at.strftime("%Y년 %m월 %d일"),
            },
            idempotency_key=f"first_charge:{user.id}:{int(datetime.now(UTC).timestamp())}",
        )
    except Exception:
        logger.warning("billing.notify_first_charge.failed", user_id=user.id)


async def issue_billing_key(
    user: User,
    pg_token: str,
    customer_key: str,
    db: AsyncSession,
) -> dict:
    """PG 토큰으로 빌링키를 발급하고 암호화 저장한다."""
    pg = get_pg_provider()
    result = await pg.issue_billing_key(user.id, pg_token, customer_key)
    encrypted = encrypt_billing_key(result["billing_key"])

    # 기존 활성 빌링키 revoke
    existing = await db.execute(
        select(BillingKey).where(
            BillingKey.user_id == user.id, BillingKey.is_active == True  # noqa: E712
        )
    )
    for bk in existing.scalars().all():
        bk.is_active = False
        bk.revoked_at = datetime.now(UTC)

    bk = BillingKey(
        user_id=user.id,
        provider=settings.pg_provider,
        billing_key_encrypted=encrypted,
        customer_key=customer_key,
        card_last4=result["card_last4"],
        card_company=result["card_company"],
        is_active=True,
    )
    db.add(bk)
    await db.commit()
    await db.refresh(bk)

    # Story 3.4: 카드 변경 시 기존 예약된 retry 태스크 취소 — 이중 청구 방지
    from api.src.workers.celery_app import celery_app as _celery_app

    fp_result = await db.execute(
        select(Payment).where(
            Payment.user_id == user.id,
            Payment.status == "failed",
            Payment.retry_task_id.is_not(None),
        )
    )
    pending_retries = fp_result.scalars().all()
    for fp in pending_retries:
        try:
            _celery_app.control.revoke(fp.retry_task_id, terminate=True)
        except Exception:
            # revoke 실패가 카드 등록 결과를 되돌리면 안 됨 — warning만 남기고 계속
            logger.warning(
                "billing.revoke_retry.failed",
                payment_id=fp.id,
                task_id=fp.retry_task_id,
            )
        fp.retry_task_id = None
    if pending_retries:
        await db.commit()

    last4 = bk.card_last4
    return {
        "billing_key_id": bk.id,
        "card_last4": last4,
        "card_company": bk.card_company,
        "masked_number": f"**** **** **** {last4}" if last4 else None,
    }


async def start_subscription(user: User, db: AsyncSession) -> dict:
    """활성 빌링키로 최초 결제 후 구독을 시작한다."""
    if user.subscription_status == "pro":
        raise SubscriptionAlreadyActive()

    # 활성 빌링키 조회
    result = await db.execute(
        select(BillingKey).where(
            BillingKey.user_id == user.id, BillingKey.is_active == True  # noqa: E712
        )
    )
    bk = result.scalar_one_or_none()
    if bk is None:
        raise BillingKeyRequired()

    billing_key_plain = decrypt_billing_key(bk.billing_key_encrypted)

    order_id = f"denvia-pro-{uuid.uuid4().hex}"
    amount = settings.pro_monthly_price_krw
    pg = get_pg_provider()

    charge_result = await pg.charge(billing_key_plain, bk.customer_key or "", amount, order_id)

    now = datetime.now(UTC)
    # 최초 결제 회차: now ~ now+30일. 구독 row 생성 전이라 sub.id가 없지만,
    # 회차 기간 자체는 결제 시점에 결정되므로 미리 스냅샷 가능.
    initial_period_end = now + timedelta(days=30)
    payment = Payment(
        user_id=user.id,
        subscription_id=None,
        provider=settings.pg_provider,
        provider_order_id=order_id,
        amount_krw=amount,
        status="success" if charge_result["success"] else "failed",
        failure_reason=charge_result["failure_reason"],
        attempt_count=1,
        charged_at=now,
        subscription_period_start=now if charge_result["success"] else None,
        subscription_period_end=initial_period_end if charge_result["success"] else None,
    )
    db.add(payment)
    await db.flush()

    event = PaymentEvent(
        payment_id=payment.id,
        event_type="charge_success" if charge_result["success"] else "charge_failed",
        raw_response_json=charge_result["raw_response"],
    )
    db.add(event)

    if not charge_result["success"]:
        await db.commit()
        raise BillingCardDeclined(
            pg_error_code=charge_result["raw_response"].get("code", "UNKNOWN"),
            message=charge_result["failure_reason"] or "카드 결제가 거절되었습니다.",
        )

    # 구독 생성
    current_period_end = initial_period_end
    sub = Subscription(
        user_id=user.id,
        status="active",
        started_at=now,
        current_period_end=current_period_end,
        next_charge_at=current_period_end,
    )
    db.add(sub)
    await db.flush()

    # payment.subscription_id 역참조
    payment.subscription_id = sub.id

    # users.subscription_status 갱신
    await db.execute(
        sa_update(User).where(User.id == user.id).values(subscription_status="pro")
    )

    await db.commit()

    logger.info(
        "billing.first_charge.completed",
        user_id=user.id,
        amount_krw=amount,
        provider=settings.pg_provider,
        order_id=order_id,
    )

    # fire-and-forget 알림 — 실패가 결제 응답을 blocking하면 안 됨
    asyncio.ensure_future(_notify_first_charge(user, amount, current_period_end))

    return {
        "subscription_id": sub.id,
        "started_at": sub.started_at.isoformat(),
        "current_period_end": current_period_end.isoformat(),
        "amount_krw": amount,
    }


# ── Story 3.3 ────────────────────────────────────────────────────────────────


async def scan_renewals(db: AsyncSession) -> dict:
    """next_charge_at <= now() AND status='active' 구독을 스캔 후 charge_renewal enqueue.

    cancel_pending / canceled / refund_pending 구독은 status='active' 조건에서 자동 제외.
    """
    from api.src.workers.celery_app import celery_app

    start = datetime.now(UTC)
    result = await db.execute(
        select(Subscription).where(
            Subscription.status == "active",
            Subscription.next_charge_at <= start,
        )
    )
    subscriptions = result.scalars().all()

    total_scanned = len(subscriptions)
    success_count = 0
    failed_count = 0

    for sub in subscriptions:
        try:
            celery_app.send_task("billing.charge_renewal", args=[sub.id])
            success_count += 1
        except Exception:
            failed_count += 1
            logger.error("billing.auto_renew.enqueue_failed", subscription_id=sub.id)

    duration_ms = int((datetime.now(UTC) - start).total_seconds() * 1000)
    logger.info(
        "billing.auto_renew.batch_completed",
        total_scanned=total_scanned,
        success_count=success_count,
        failed_count=failed_count,
        duration_ms=duration_ms,
    )
    return {"enqueued": success_count}


async def charge_renewal(subscription_id: int, db: AsyncSession) -> dict:
    """단일 구독 자동 갱신 — PG 결제 → DB 업데이트 → 알림/실패처리."""
    import uuid as _uuid

    import sentry_sdk

    from api.src.workers.celery_app import celery_app

    start = datetime.now(UTC)

    # 구독 조회 — row-level lock으로 동시 실행 직렬화
    sub_result = await db.execute(
        select(Subscription)
        .where(Subscription.id == subscription_id)
        .with_for_update()
    )
    sub = sub_result.scalar_one_or_none()
    if sub is None:
        logger.error(
            "billing.charge_renewal.subscription_not_found",
            subscription_id=subscription_id,
        )
        return {"status": "error", "reason": "subscription_not_found"}

    # 실행 시점 재검증 — stale/duplicate task 방어
    if sub.status != "active" or sub.next_charge_at > start:
        logger.info(
            "billing.charge_renewal.skipped",
            subscription_id=subscription_id,
            status=sub.status,
            next_charge_at=sub.next_charge_at.isoformat() if sub.next_charge_at else None,
        )
        return {
            "status": "skipped",
            "subscription_id": subscription_id,
            "reason": "status_not_active" if sub.status != "active" else "already_renewed",
        }

    # 활성 빌링키 조회
    bk_result = await db.execute(
        select(BillingKey).where(
            BillingKey.user_id == sub.user_id,
            BillingKey.is_active == True,  # noqa: E712
        )
    )
    bk = bk_result.scalar_one_or_none()
    if bk is None:
        logger.error(
            "billing.charge_renewal.no_active_billing_key",
            subscription_id=subscription_id,
            user_id=sub.user_id,
        )
        return {"status": "error", "reason": "no_active_billing_key"}

    billing_key_plain = decrypt_billing_key(bk.billing_key_encrypted)
    # order_id: renewal-{subscription_id}-{uuid hex 12자리} — UNIQUE 보장
    order_id = f"renewal-{subscription_id}-{_uuid.uuid4().hex[:12]}"
    amount = settings.pro_monthly_price_krw

    pg = get_pg_provider()

    try:
        charge_result = await pg.charge(billing_key_plain, bk.customer_key or "", amount, order_id)
    except Exception as exc:
        exc_now = datetime.now(UTC)
        # 실패 결제는 회차가 확정되지 않았으므로 snapshot 컬럼 NULL
        payment = Payment(
            user_id=sub.user_id,
            subscription_id=subscription_id,
            provider=settings.pg_provider,
            provider_order_id=order_id,
            amount_krw=amount,
            status="failed",
            failure_reason=str(exc),
            attempt_count=1,
            charged_at=exc_now,
            subscription_period_start=None,
            subscription_period_end=None,
        )
        db.add(payment)
        await db.flush()

        db.add(
            PaymentEvent(
                payment_id=payment.id,
                event_type="charge_failed",
                raw_response_json={"exception": str(exc)},
            )
        )

        # Story 3.4: send_task 반환 task id를 payment.retry_task_id + retry_scheduled 이벤트에 동시 기록
        retry_task = celery_app.send_task(
            "billing.retry_payment", args=[payment.id], countdown=86400
        )
        payment.retry_task_id = retry_task.id
        db.add(
            PaymentEvent(
                payment_id=payment.id,
                event_type="retry_scheduled",
                raw_response_json={
                    "reason": "pg_exception",
                    "next_attempt": 2,
                    "countdown_sec": 86400,
                    "task_id": retry_task.id,
                },
            )
        )
        await db.commit()

        sentry_sdk.add_breadcrumb(
            category="billing",
            message="billing.charge_renewal.failed",
            data={"subscription_id": subscription_id, "failure_reason": str(exc)},
            level="error",
        )
        logger.warning(
            "billing.charge_renewal.failed",
            subscription_id=subscription_id,
            user_id=sub.user_id,
            failure_reason=str(exc),
        )

        duration_ms = int((datetime.now(UTC) - start).total_seconds() * 1000)
        return {
            "status": "failed",
            "subscription_id": subscription_id,
            "payment_id": payment.id,
            "duration_ms": duration_ms,
        }

    now = datetime.now(UTC)

    # 자동 갱신 회차: 기존 sub.current_period_end ~ +30일.
    # success일 때만 scope 회차로 박제하고, fail은 NULL로 둔다.
    new_period_end_renewal = sub.current_period_end + timedelta(days=30)
    payment = Payment(
        user_id=sub.user_id,
        subscription_id=subscription_id,
        provider=settings.pg_provider,
        provider_order_id=order_id,
        amount_krw=amount,
        status="success" if charge_result["success"] else "failed",
        failure_reason=charge_result.get("failure_reason"),
        attempt_count=1,
        charged_at=now,
        subscription_period_start=(
            sub.current_period_end if charge_result["success"] else None
        ),
        subscription_period_end=(
            new_period_end_renewal if charge_result["success"] else None
        ),
    )
    db.add(payment)
    await db.flush()  # payment.id 확보

    db.add(
        PaymentEvent(
            payment_id=payment.id,
            event_type="charge_success" if charge_result["success"] else "charge_failed",
            raw_response_json=charge_result.get("raw_response"),
        )
    )

    if charge_result["success"]:
        # 구독 기간 30일 고정 연장 (윤달·말일 보정 없음)
        new_period_end = new_period_end_renewal
        sub.current_period_end = new_period_end
        sub.next_charge_at = new_period_end
        await db.commit()

        logger.info(
            "billing.charge_renewal.success",
            subscription_id=subscription_id,
            user_id=sub.user_id,
            amount_krw=amount,
            new_period_end=new_period_end.isoformat(),
        )

        # 2026-05-18 고객 검수 v4 — 자동 갱신 성공 알림(1-2)은 발송 안 함.
        # billing.auto_renew_success 카탈로그 제거에 따라 호출 자체 비활성화.

        duration_ms = int((datetime.now(UTC) - start).total_seconds() * 1000)
        return {
            "status": "success",
            "subscription_id": subscription_id,
            "duration_ms": duration_ms,
        }
    else:
        # Story 3.4: send_task 반환 task id를 payment.retry_task_id + retry_scheduled 이벤트에 동시 기록
        retry_task = celery_app.send_task(
            "billing.retry_payment", args=[payment.id], countdown=86400
        )
        payment.retry_task_id = retry_task.id
        db.add(
            PaymentEvent(
                payment_id=payment.id,
                event_type="retry_scheduled",
                raw_response_json={
                    "reason": "auto_renewal_failed",
                    "next_attempt": 2,
                    "countdown_sec": 86400,
                    "task_id": retry_task.id,
                },
            )
        )
        await db.commit()

        sentry_sdk.add_breadcrumb(
            category="billing",
            message="billing.charge_renewal.failed",
            data={
                "subscription_id": subscription_id,
                "failure_reason": charge_result.get("failure_reason"),
            },
            level="error",
        )
        logger.warning(
            "billing.charge_renewal.failed",
            subscription_id=subscription_id,
            user_id=sub.user_id,
            failure_reason=charge_result.get("failure_reason"),
        )

        duration_ms = int((datetime.now(UTC) - start).total_seconds() * 1000)
        return {
            "status": "failed",
            "subscription_id": subscription_id,
            "payment_id": payment.id,
            "duration_ms": duration_ms,
        }


# 2026-05-18 고객 검수 v4 — `_notify_renewal()` 제거.
# 자동 갱신 성공(billing.auto_renew_success) 알림은 고객 요청으로 발송 폐지.


# ── Story 3.4 ────────────────────────────────────────────────────────────────

# attempt=4까지가 최종 재시도 (총 3회 재시도: attempt 2·3·4)
_MAX_RETRY_ATTEMPT = 4

# 재시도 간격(키 = 예약될 다음 attempt 번호 기준):
#   - attempt=2 예약 시 86400초(1일) — Story 3.3이 직접 사용
#   - attempt=3 예약 시 259200초(3일) — attempt=2 실패 후
#   - attempt=4 예약 시 259200초(3일) — attempt=3 실패 후
_RETRY_COUNTDOWNS = {2: 86400, 3: 259200, 4: 259200}


async def retry_payment(payment_id: int, attempt: int, db: AsyncSession) -> dict:
    """결제 실패 재시도 — Story 3.3의 send_task('billing.retry_payment', args=[payment_id]) 계약 이행.

    Args:
        payment_id: 최초 실패한 payments.id (Story 3.3 charge_renewal 생성)
        attempt: 2(기본값) → 3 → 4(최종). 3.3에서 attempt 없이 호출 시 기본값 2.
    """
    import sentry_sdk

    from api.src.workers.celery_app import celery_app

    start = datetime.now(UTC)

    if attempt < 2 or attempt > _MAX_RETRY_ATTEMPT:
        logger.warning(
            "billing.retry_payment.invalid_attempt",
            payment_id=payment_id,
            attempt=attempt,
        )
        return {"status": "error", "reason": "invalid_attempt"}

    # ── payment 조회 — row-level lock으로 동일 payment 재시도 직렬화 ─────────
    pay_result = await db.execute(
        select(Payment).where(Payment.id == payment_id).with_for_update()
    )
    payment = pay_result.scalar_one_or_none()
    if payment is None:
        logger.error("billing.retry_payment.payment_not_found", payment_id=payment_id)
        return {"status": "error", "reason": "payment_not_found"}

    # ── 멱등성 체크 — 이미 성공 처리된 결제는 no-op (kill-switch보다 먼저) ───
    if payment.status == "success":
        logger.info("billing.retry_payment.already_success", payment_id=payment_id)
        return {"status": "no-op", "reason": "already_success"}

    # 동일 attempt 중복 실행은 PG 호출 전에 종료 — DB 이벤트/재예약 중복 방지
    if payment.attempt_count >= attempt:
        logger.info(
            "billing.retry_payment.duplicate_attempt",
            payment_id=payment_id,
            attempt=attempt,
            attempt_count=payment.attempt_count,
        )
        return {"status": "no-op", "reason": "duplicate_attempt"}

    # ── kill-switch 훅 (Epic 9 A-502 연결점) ──────────────────────────────────
    # auto_free_only 모드는 결제 재시도에 영향 없음(무료 Q&A 차단만 적용).
    ks_result = await db.execute(
        select(KillswitchState)
        .where(
            KillswitchState.mode == MODE_MANUAL_TOTAL,
            KillswitchState.deactivated_at.is_(None),
        )
        .limit(1)
    )
    if ks_result.scalar_one_or_none() is not None:
        # kill-switch 활성 — PG는 호출하지 않되, 동일 attempt를 일정 시간 뒤 재예약하여
        # 해제 후 자동으로 처리되도록 한다. attempt_count는 증가시키지 않는다(소비 X).
        ks_countdown = 3600
        ks_task = celery_app.send_task(
            "billing.retry_payment",
            args=[payment_id, attempt],
            countdown=ks_countdown,
        )
        payment.retry_task_id = ks_task.id
        db.add(
            PaymentEvent(
                payment_id=payment_id,
                event_type="retry_scheduled",
                raw_response_json={
                    "reason": "kill_switch_active",
                    "attempt": attempt,
                    "countdown_sec": ks_countdown,
                    "task_id": ks_task.id,
                },
            )
        )
        await db.commit()
        logger.info(
            "billing.retry_payment.deferred_kill_switch",
            payment_id=payment_id,
            attempt=attempt,
            task_id=ks_task.id,
            countdown_sec=ks_countdown,
        )
        return {
            "status": "deferred",
            "reason": "kill_switch_active",
            "task_id": ks_task.id,
        }

    # ── 구독 + 활성 빌링키 조회 ───────────────────────────────────────────────
    if payment.subscription_id is None:
        logger.error("billing.retry_payment.no_subscription_id", payment_id=payment_id)
        return {"status": "error", "reason": "no_subscription_id"}

    sub_result = await db.execute(
        select(Subscription).where(Subscription.id == payment.subscription_id)
    )
    sub = sub_result.scalar_one_or_none()
    if sub is None:
        logger.error(
            "billing.retry_payment.subscription_not_found",
            payment_id=payment_id,
            subscription_id=payment.subscription_id,
        )
        return {"status": "error", "reason": "subscription_not_found"}

    bk_result = await db.execute(
        select(BillingKey).where(
            BillingKey.user_id == payment.user_id,
            BillingKey.is_active == True,  # noqa: E712
        )
    )
    bk = bk_result.scalar_one_or_none()
    if bk is None:
        logger.error(
            "billing.retry_payment.no_active_billing_key",
            payment_id=payment_id,
            user_id=payment.user_id,
        )
        return {"status": "error", "reason": "no_active_billing_key"}

    # ── PG 재결제 ─────────────────────────────────────────────────────────────
    billing_key_plain = decrypt_billing_key(bk.billing_key_encrypted)
    # 결정적 order_id — 동일 attempt 재호출 시 PG idempotency/중복 주문 방어용 2차 가드.
    # 토스 허용 문자(영문/숫자/'-'/'_')에 맞춰 ':' 대신 '-' 사용.
    order_id = f"retry-{payment_id}-{attempt}"
    amount = settings.pro_monthly_price_krw

    pg = get_pg_provider()
    try:
        charge_result = await pg.charge(
            billing_key_plain, bk.customer_key or "", amount, order_id
        )
    except Exception as exc:
        # PG transport/예외도 실패 attempt로 처리 — Celery 밖으로 raise하지 않고
        # _handle_retry_failure 경로(다음 attempt 예약 또는 cancel_pending)를 그대로 사용.
        charge_result = {
            "success": False,
            "failure_reason": str(exc),
            "raw_response": {
                "exception": str(exc),
                "exception_type": exc.__class__.__name__,
                "reason": "pg_exception",
            },
        }

    now = datetime.now(UTC)
    latency_ms = int((now - start).total_seconds() * 1000)

    if charge_result["success"]:
        await _handle_retry_success(payment, sub, attempt, order_id, charge_result, now, db)
        logger.info(
            "billing.retry.attempted",
            payment_id=payment_id,
            attempt=attempt,
            result="success",
            latency_ms=latency_ms,
        )
        # 2026-05-18 고객 검수 v4 — 재시도 성공 알림(1-3, billing.retry_success)은 발송 안 함.
        return {
            "status": "success",
            "payment_id": payment_id,
            "attempt": attempt,
            "latency_ms": latency_ms,
        }

    await _handle_retry_failure(
        payment, sub, attempt, order_id, charge_result, now, celery_app, db
    )
    sentry_sdk.add_breadcrumb(
        category="billing",
        message="billing.retry_payment.failed",
        data={
            "payment_id": payment_id,
            "attempt": attempt,
            "reason": charge_result.get("failure_reason"),
        },
        level="error",
    )
    logger.warning(
        "billing.retry.attempted",
        payment_id=payment_id,
        attempt=attempt,
        result="failed",
        failure_reason=charge_result.get("failure_reason"),
        latency_ms=latency_ms,
    )
    # 단계별 알림 (N=attempt-1: attempt=2→N=1, attempt=3→N=2, attempt=4→N=3)
    n = attempt - 1
    try:
        await _notify_retry(
            user_id=payment.user_id,
            template_code=f"billing.retry_failed_{n}",
            variables={"amount_krw": str(amount)},
            idempotency_key=f"retry_failed:{payment_id}:{attempt}",
        )
    except Exception:
        pass
    return {
        "status": "failed",
        "payment_id": payment_id,
        "attempt": attempt,
        "latency_ms": latency_ms,
    }


async def _handle_retry_success(
    payment: Payment,
    sub: Subscription,
    attempt: int,
    order_id: str,
    charge_result: dict,
    now: datetime,
    db: AsyncSession,
) -> None:
    """재시도 성공 처리 — payment 업데이트 + 구독 30일 연장 + retry_task_id 초기화."""
    # 재시도 성공도 회차 스냅샷 박제 — 기존 current_period_end ~ +30일.
    new_period_end = sub.current_period_end + timedelta(days=30)

    payment.status = "success"
    payment.attempt_count = attempt
    payment.provider_order_id = order_id
    payment.failure_reason = None
    payment.charged_at = now
    payment.retry_task_id = None  # 성공했으므로 revoke 불필요
    payment.subscription_period_start = sub.current_period_end
    payment.subscription_period_end = new_period_end

    db.add(
        PaymentEvent(
            payment_id=payment.id,
            event_type="charge_success",
            raw_response_json=charge_result.get("raw_response"),
        )
    )

    # 구독 기간 30일 고정 연장 — charge_renewal 패턴 동일
    sub.current_period_end = new_period_end
    sub.next_charge_at = new_period_end

    await db.commit()


async def _handle_retry_failure(
    payment: Payment,
    sub: Subscription,
    attempt: int,
    order_id: str,
    charge_result: dict,
    now: datetime,
    celery_app,
    db: AsyncSession,
) -> str | None:
    """재시도 실패 처리 — attempt < MAX: 다음 재시도 예약. attempt == MAX: cancel_pending 전환."""
    payment.attempt_count = attempt
    payment.provider_order_id = order_id
    payment.failure_reason = charge_result.get("failure_reason")

    db.add(
        PaymentEvent(
            payment_id=payment.id,
            event_type="charge_failed",
            raw_response_json=charge_result.get("raw_response"),
        )
    )

    task_id: str | None = None

    if attempt < _MAX_RETRY_ATTEMPT:
        next_attempt = attempt + 1
        countdown = _RETRY_COUNTDOWNS[next_attempt]  # attempt=2 fail→3=259200, 3 fail→4=259200
        task = celery_app.send_task(
            "billing.retry_payment",
            args=[payment.id, next_attempt],
            countdown=countdown,
        )
        task_id = task.id
        payment.retry_task_id = task_id  # revoke-on-card-change용
        db.add(
            PaymentEvent(
                payment_id=payment.id,
                event_type="retry_scheduled",
                raw_response_json={
                    "next_attempt": next_attempt,
                    "countdown_sec": countdown,
                    "task_id": task_id,
                },
            )
        )
    else:
        # 최종 실패 — cancel_pending 전환 (Story 3.5 finalize_cancellations Beat가 종료 처리)
        payment.retry_task_id = None
        sub.status = "cancel_pending"
        sub.canceled_at = now
        sub.cancel_reason = "payment_retry_exhausted"
        # users.subscription_status는 변경하지 않음 — Story 3.5 책임

    await db.commit()
    return task_id


async def _notify_retry(
    user_id: int,
    template_code: str,
    variables: dict,
    idempotency_key: str,
) -> None:
    """재시도 알림 fire-and-forget — 실패해도 재시도 결과에 영향 없음."""
    try:
        from api.src.models.base import async_session_factory

        async with async_session_factory() as db:
            result = await db.execute(
                select(User).where(User.id == user_id, User.withdrawn_at.is_(None))
            )
            user = result.scalar_one_or_none()
            if user is None:
                return

        from api.src.integrations.messaging.notification_service import (
            get_notification_service,
        )

        svc = get_notification_service()
        await svc.send(
            user_id=user_id,
            phone=user.phone or "",
            template_code=template_code,
            variables=variables,
            idempotency_key=idempotency_key,
        )
    except Exception:
        logger.warning(
            "billing.notify_retry.failed",
            user_id=user_id,
            template_code=template_code,
        )


# ── Story 3.5 ────────────────────────────────────────────────────────────────


async def cancel_subscription(user: User, reason: str, db: AsyncSession) -> dict:
    """active 구독을 cancel_pending으로 전이. 멱등 처리 포함.

    Raises:
        SubscriptionAlreadyCanceled: 이미 status='canceled'인 구독만 존재
        SubscriptionNotFound: 활성/대기 + canceled 모두 0건
    Returns:
        { "status": "cancel_pending", "effective_at": ISO8601 }
    """
    sub_result = await db.execute(
        select(Subscription)
        .where(
            Subscription.user_id == user.id,
            Subscription.status.in_(("active", "cancel_pending")),
        )
        .with_for_update()
        .limit(1)
    )
    sub = sub_result.scalar_one_or_none()
    if sub is None:
        # canceled 1건만 있는지(이미 종료) vs 0건인지 분기
        any_result = await db.execute(
            select(Subscription)
            .where(
                Subscription.user_id == user.id,
                Subscription.status == "canceled",
            )
            .limit(1)
        )
        if any_result.scalar_one_or_none() is not None:
            raise SubscriptionAlreadyCanceled()
        raise SubscriptionNotFound()

    now = datetime.now(UTC)

    # 멱등: 이미 cancel_pending이면 변경 없이 현재 상태 반환
    if sub.status == "cancel_pending":
        logger.info(
            "subscription.cancel_requested.idempotent",
            user_id=user.id,
            subscription_id=sub.id,
        )
        return {
            "status": "cancel_pending",
            "effective_at": sub.current_period_end.isoformat(),
        }

    sub.status = "cancel_pending"
    sub.canceled_at = now
    sub.cancel_reason = reason
    await db.commit()

    logger.info(
        "subscription.cancel_requested",
        user_id=user.id,
        subscription_id=sub.id,
        effective_at=sub.current_period_end.isoformat(),
    )

    # fire-and-forget 알림 (실패가 응답을 막지 않음)
    # 2026-05-18 v4: 본문 예시(2026-06-15)에 맞춰 YYYY-MM-DD 포맷으로 통일.
    try:
        await _notify_subscription_event(
            user_id=user.id,
            template_code="subscription.cancel_requested",
            variables={
                "effective_at": sub.current_period_end.strftime("%Y-%m-%d"),
            },
            idempotency_key=f"cancel_requested:{sub.id}:{int(now.timestamp())}",
        )
    except Exception:
        pass

    return {
        "status": "cancel_pending",
        "effective_at": sub.current_period_end.isoformat(),
    }


async def resume_subscription(user: User, db: AsyncSession) -> dict:
    """cancel_pending 구독을 active로 복원. active 입력 시 멱등 200.

    Raises:
        SubscriptionAlreadyCanceled: status='canceled' OR cancel_pending && expired
        ResumeNotApplicable: 활성/대기 0건 + canceled 0건
    Returns:
        { "status": "active", "next_charge_at": ISO8601|None }
    """
    sub_result = await db.execute(
        select(Subscription)
        .where(
            Subscription.user_id == user.id,
            Subscription.status.in_(("active", "cancel_pending")),
        )
        .with_for_update()
        .limit(1)
    )
    sub = sub_result.scalar_one_or_none()
    if sub is None:
        # canceled가 있으면 적용 완료, 아니면 신규 구독 안내
        any_result = await db.execute(
            select(Subscription)
            .where(
                Subscription.user_id == user.id,
                Subscription.status == "canceled",
            )
            .limit(1)
        )
        if any_result.scalar_one_or_none() is not None:
            raise SubscriptionAlreadyCanceled()
        raise ResumeNotApplicable()

    now = datetime.now(UTC)

    # active 멱등: 비즈니스 변경 없음
    if sub.status == "active":
        return {
            "status": "active",
            "next_charge_at": sub.next_charge_at.isoformat() if sub.next_charge_at else None,
        }

    # cancel_pending && 만료 직전 race — finalize 적용 후로 간주
    if sub.current_period_end <= now:
        raise SubscriptionAlreadyCanceled()

    sub.status = "active"
    sub.canceled_at = None
    sub.cancel_reason = None
    await db.commit()

    logger.info(
        "subscription.resume",
        user_id=user.id,
        subscription_id=sub.id,
        next_charge_at=sub.next_charge_at.isoformat() if sub.next_charge_at else None,
    )

    # 2026-05-18 v4: 본문이 단일 문장으로 간결화되어 next_charge_at 변수 제거.
    try:
        await _notify_subscription_event(
            user_id=user.id,
            template_code="subscription.resumed",
            variables={},
            idempotency_key=f"resume:{sub.id}:{int(now.timestamp())}",
        )
    except Exception:
        pass

    return {
        "status": "active",
        "next_charge_at": sub.next_charge_at.isoformat() if sub.next_charge_at else None,
    }


async def finalize_cancellations(db: AsyncSession) -> dict:
    """매시 15분 — cancel_pending && current_period_end <= now 일괄 종료.

    각 레코드를 한 트랜잭션으로 상태 전이하고 알림을 fire-and-forget으로 발송.
    부분 실패가 다른 건의 commit을 막지 않도록 건별 트랜잭션으로 분리.
    """
    start = datetime.now(UTC)

    result = await db.execute(
        select(Subscription).where(
            Subscription.status == "cancel_pending",
            Subscription.current_period_end <= start,
        )
    )
    targets = result.scalars().all()

    finalized = 0
    for sub in targets:
        # 개별 row-level lock으로 동시 실행 직렬화
        relock = await db.execute(
            select(Subscription)
            .where(Subscription.id == sub.id)
            .with_for_update()
        )
        s = relock.scalar_one_or_none()
        if s is None or s.status != "cancel_pending":
            continue
        if s.current_period_end > datetime.now(UTC):
            continue

        s.status = "canceled"
        s.next_charge_at = None
        await db.execute(
            sa_update(User)
            .where(User.id == s.user_id)
            .values(subscription_status="free")
        )
        await db.commit()

        logger.info(
            "subscription.canceled_finalized",
            subscription_id=s.id,
            user_id=s.user_id,
            cancel_reason=s.cancel_reason,
            current_period_end=s.current_period_end.isoformat(),
        )

        # 2026-05-18 v4: 본문에 {user_name} 님은 {effective_at} 일 부터... 추가.
        # user_name은 _notify_subscription_event 내부에서 email local-part로 자동 주입됨.
        try:
            await _notify_subscription_event(
                user_id=s.user_id,
                template_code="subscription.canceled_finalized",
                variables={
                    "effective_at": s.current_period_end.strftime("%Y-%m-%d"),
                },
                idempotency_key=f"canceled_finalized:{s.id}",
            )
        except Exception:
            pass

        finalized += 1

    duration_ms = int((datetime.now(UTC) - start).total_seconds() * 1000)
    logger.info(
        "subscription.finalize_cancellations.batch_completed",
        scanned=len(targets),
        finalized=finalized,
        duration_ms=duration_ms,
    )
    return {"scanned": len(targets), "finalized": finalized, "duration_ms": duration_ms}


async def extend_active_subscriptions(
    killswitch_state_id: int,
    db: AsyncSession,
) -> dict:
    """Story 9.2 — manual_total 해제 시 활성/cancel_pending 구독의 만료일 자동 연장.

    - 정지 기간 = killswitch_state.deactivated_at - activated_at
    - 대상 구독: status IN (active, cancel_pending) AND created_at <= deactivated_at
                AND current_period_end > activated_at
    - 100건 단위 chunk commit + chunk 사이 50ms sleep (부하 분산).
    - 알림톡 idempotency_key: f"killswitch:{killswitch_state_id}:sub:{sub.id}".
    - audit_logs INSERT (action='subscription.extended_killswitch', actor_user_id=NULL=시스템).
    """
    from api.src.models.audit_log import AuditLog
    from api.src.models.killswitch_state import KillswitchState as KSModel

    ks = (await db.execute(
        select(KSModel).where(KSModel.id == killswitch_state_id)
    )).scalar_one_or_none()
    if ks is None:
        logger.error(
            "billing.extend_subscriptions.killswitch_not_found",
            killswitch_state_id=killswitch_state_id,
        )
        return {"status": "skip", "reason": "not_found"}
    if ks.mode != MODE_MANUAL_TOTAL or ks.deactivated_at is None:
        logger.info(
            "billing.extend_subscriptions.invalid_state",
            killswitch_state_id=killswitch_state_id,
            mode=ks.mode,
            deactivated_at=str(ks.deactivated_at),
        )
        return {"status": "skip", "reason": "invalid_state"}

    activated_at = ks.activated_at
    deactivated_at = ks.deactivated_at
    if activated_at.tzinfo is None:
        activated_at = activated_at.replace(tzinfo=UTC)
    if deactivated_at.tzinfo is None:
        deactivated_at = deactivated_at.replace(tzinfo=UTC)
    duration: timedelta = deactivated_at - activated_at
    duration_seconds = int(duration.total_seconds())

    # 연장 대상 SELECT — active + cancel_pending, 정지 종료 시점까지 살아있던 구독.
    targets_result = await db.execute(
        select(Subscription).where(
            Subscription.status.in_(("active", "cancel_pending")),
            Subscription.created_at <= deactivated_at,
            Subscription.current_period_end > activated_at,
        )
    )
    targets = list(targets_result.scalars().all())
    extended_count = 0

    chunk_size = 100
    for i in range(0, len(targets), chunk_size):
        chunk = targets[i : i + chunk_size]
        for sub in chunk:
            # 개별 row-level lock — finalize_cancellations 등과 race 방지.
            relock = await db.execute(
                select(Subscription).where(Subscription.id == sub.id).with_for_update()
            )
            s = relock.scalar_one_or_none()
            if s is None or s.status not in ("active", "cancel_pending"):
                continue

            # 멱등성 체크 — 동일 killswitch_state_id + 구독 조합은 한 번만 처리한다.
            # (워커 재시작·중복 enqueue로 태스크가 두 번 실행되어도 기간이 이중 연장되지 않음)
            existing_ext = (await db.execute(
                select(AuditLog).where(
                    AuditLog.action == "subscription.extended_killswitch",
                    AuditLog.target_type == "subscription",
                    AuditLog.target_id == s.id,
                    AuditLog.diff_json["killswitch_state_id"].astext
                    == str(killswitch_state_id),
                ).limit(1)
            )).scalar_one_or_none()
            if existing_ext is not None:
                logger.info(
                    "billing.extend_subscriptions.already_extended",
                    subscription_id=s.id,
                    killswitch_state_id=killswitch_state_id,
                )
                continue

            old_period_end = s.current_period_end
            s.current_period_end = old_period_end + duration
            if s.next_charge_at is not None:
                s.next_charge_at = s.next_charge_at + duration

            db.add(
                AuditLog(
                    actor_user_id=None,  # 시스템 actor
                    action="subscription.extended_killswitch",
                    target_type="subscription",
                    target_id=s.id,
                    diff_json={
                        "duration_seconds": duration_seconds,
                        "extended_to": s.current_period_end.isoformat(),
                        "killswitch_state_id": killswitch_state_id,
                    },
                )
            )
            extended_count += 1

            # 2026-05-18 — `subscription.extended_due_to_killswitch` 알림톡 발송 폐지.
            # 클라이언트 v4 검수서(Google Docs 2026-05-15)에 미포함 → 발송 안 함.
            # 킬스위치 발동 시 구독 기간 연장 자체는 그대로 수행하되,
            # 사용자 안내는 인앱 공지·1:1 쪽지 등 별도 채널로 대체.

        await db.commit()
        # 부하 분산 — chunk 사이 50ms sleep.
        await asyncio.sleep(0.05)

    logger.info(
        "billing.extend_subscriptions.completed",
        killswitch_state_id=killswitch_state_id,
        extended_count=extended_count,
        duration_seconds=duration_seconds,
    )
    return {
        "status": "ok",
        "extended_count": extended_count,
        "duration_seconds": duration_seconds,
        "killswitch_state_id": killswitch_state_id,
    }


async def get_current_subscription(user: User, db: AsyncSession) -> dict:
    """active/cancel_pending 1건 조회. 없으면 status='none'."""
    result = await db.execute(
        select(Subscription)
        .where(
            Subscription.user_id == user.id,
            Subscription.status.in_(("active", "cancel_pending")),
        )
        .order_by(Subscription.id.desc())
        .limit(1)
    )
    sub = result.scalar_one_or_none()
    if sub is None:
        return {
            "status": "none",
            "started_at": None,
            "current_period_end": None,
            "next_charge_at": None,
            "canceled_at": None,
            "cancel_reason": None,
        }

    return {
        "status": sub.status,
        "started_at": sub.started_at.isoformat(),
        "current_period_end": sub.current_period_end.isoformat(),
        "next_charge_at": sub.next_charge_at.isoformat() if sub.next_charge_at else None,
        "canceled_at": sub.canceled_at.isoformat() if sub.canceled_at else None,
        "cancel_reason": sub.cancel_reason,
    }


async def _notify_subscription_event(
    user_id: int,
    template_code: str,
    variables: dict,
    idempotency_key: str,
) -> None:
    """구독 이벤트 알림 fire-and-forget — 실패해도 상태 전이 결과에 영향 없음.

    호출 측이 `user_name`을 명시하지 않은 경우, User 모델에 별도 표시 이름 컬럼이
    없으므로 email의 local-part(@ 앞부분)를 fallback 으로 자동 주입한다.
    (예: `pro_user@denvia.kr` → `user_name="pro_user"`)
    """
    try:
        from api.src.models.base import async_session_factory

        async with async_session_factory() as db:
            result = await db.execute(
                select(User).where(User.id == user_id, User.withdrawn_at.is_(None))
            )
            user = result.scalar_one_or_none()
            if user is None:
                return

        merged_variables = dict(variables)
        if "user_name" not in merged_variables:
            email = user.email or ""
            merged_variables["user_name"] = email.split("@", 1)[0] or "고객"

        from api.src.integrations.messaging.notification_service import (
            get_notification_service,
        )

        svc = get_notification_service()
        await svc.send(
            user_id=user_id,
            phone=user.phone or "",
            template_code=template_code,
            variables=merged_variables,
            idempotency_key=idempotency_key,
        )
    except Exception:
        logger.warning(
            "subscription.notify.failed",
            user_id=user_id,
            template_code=template_code,
        )


# ── Story 3.6 v1.1 — 청약철회 (Cooling-off Refund) ────────────────────────────
# v1.1 정책 변경(2026-05-12, ADR-0001 편차 #5)으로 자가 환불 요청 폼·수동 검토 큐 폐기.
# 본 섹션은 청약철회 단일 경로만 담당: 7일 이내 + 질문 0건 → 즉시 해지 + 전액 환불.
# 운영 환불(관리자 부분/전액)은 Story 9.1 v1.1 책임.


_COOLING_OFF_DAYS_LIMIT = 7
# Toss cancelReason 길이 제한 — 안전 cushion(200자로 truncate)
_TOSS_CANCEL_REASON_MAX = 200
_COOLING_OFF_REASON = "cooling_off"


async def check_refund_eligibility(user: User, db: AsyncSession) -> dict:
    """청약철회 가능 여부를 read-only로 조회한다 (Story 3.6 v1.1 AC1).

    마이페이지(Story 4.4)가 "구독 취소" 다이얼로그에서 "즉시 해지 + 전액 환불"
    옵션을 노출할지 결정하는 용도. 상태 변경·side effect 없음.

    Returns:
        {
          "eligible": bool,
          "payment_id": int|None,
          "amount_krw": int|None,
          "charged_at": datetime|None,
          "days_since_charge": int|None,
          "qa_count_during_period": int|None,
          "reason_code": "ok"|"period_exceeded"|"qa_count_exceeded"|"both"|"no_active_payment",
        }
    """
    from sqlalchemy import desc

    # 1. 현재 활성/대기 구독 — 가장 최근 1건
    sub_stmt = (
        select(Subscription)
        .where(
            Subscription.user_id == user.id,
            Subscription.status.in_(("active", "cancel_pending")),
        )
        .order_by(desc(Subscription.id))
        .limit(1)
    )
    sub = (await db.execute(sub_stmt)).scalar_one_or_none()
    if sub is None:
        logger.info(
            "billing.refund.eligibility_checked",
            user_id=user.id,
            eligible=False,
            reason_code="no_active_payment",
        )
        return {
            "eligible": False,
            "payment_id": None,
            "amount_krw": None,
            "charged_at": None,
            "days_since_charge": None,
            "qa_count_during_period": None,
            "reason_code": "no_active_payment",
        }

    # 2. 해당 구독의 가장 최근 success 결제
    payment = await _find_latest_success_payment(user.id, sub.id, db)
    if payment is None:
        logger.info(
            "billing.refund.eligibility_checked",
            user_id=user.id,
            eligible=False,
            reason_code="no_active_payment",
        )
        return {
            "eligible": False,
            "payment_id": None,
            "amount_krw": None,
            "charged_at": None,
            "days_since_charge": None,
            "qa_count_during_period": None,
            "reason_code": "no_active_payment",
        }

    # 3. 청약철회 조건 평가
    eligible, qa_count, days_since, reason_code = (
        await _evaluate_cooling_off_eligibility(payment, sub, db)
    )

    logger.info(
        "billing.refund.eligibility_checked",
        user_id=user.id,
        eligible=eligible,
        reason_code=("ok" if eligible else reason_code),
    )
    return {
        "eligible": eligible,
        "payment_id": payment.id,
        "amount_krw": payment.amount_krw,
        "charged_at": payment.charged_at.isoformat() if payment.charged_at else None,
        "days_since_charge": days_since,
        "qa_count_during_period": qa_count,
        "reason_code": "ok" if eligible else (reason_code or "period_exceeded"),
    }


async def cancel_with_refund(user: User, db: AsyncSession) -> dict:
    """청약철회 — 구독 즉시 해지 + 전액 환불 (Story 3.6 v1.1 AC2~6).

    호출 동선은 마이페이지(Story 4.4) 구독 취소 다이얼로그의 "즉시 해지 + 전액 환불" 옵션.
    백엔드는 클라이언트 사전 조회(AC1) 우회를 방어하기 위해 조건을 다시 검증한다.

    Returns:
        {
          "status": "refunded",
          "refund_kind": "cooling_off",
          "amount_krw": int,
          "refunded_at": ISO8601,
          "subscription_status": "canceled",
        }

    Raises:
        NoActiveSubscription, NoRefundablePayment,
        RefundNotEligible, RefundAlreadyProcessed, RefundAlreadyRequested,
        PaymentNotRefundable, RefundProviderUnavailable.
    """
    from sqlalchemy import desc

    # 1. 활성/대기 구독 조회
    sub_stmt = (
        select(Subscription)
        .where(
            Subscription.user_id == user.id,
            Subscription.status.in_(("active", "cancel_pending")),
        )
        .order_by(desc(Subscription.id))
        .limit(1)
    )
    sub = (await db.execute(sub_stmt)).scalar_one_or_none()
    if sub is None:
        raise NoActiveSubscription()

    # 2. 가장 최근 success payment
    payment_candidate = await _find_latest_success_payment(user.id, sub.id, db)
    if payment_candidate is None:
        raise NoRefundablePayment()

    # 3. row-level lock — 동시 호출 직렬화
    pay_lock_stmt = (
        select(Payment)
        .where(Payment.id == payment_candidate.id, Payment.user_id == user.id)
        .with_for_update()
    )
    payment = (await db.execute(pay_lock_stmt)).scalar_one_or_none()
    if payment is None:
        raise NoRefundablePayment()

    # 4. payment.status 분기 (이중 진입 차단)
    if payment.status == "refunded":
        logger.info(
            "billing.refund.duplicate",
            payment_id=payment.id,
            user_id=user.id,
            existing_status="refunded",
        )
        raise RefundAlreadyProcessed()
    if payment.status == "refund_pending":
        logger.info(
            "billing.refund.duplicate",
            payment_id=payment.id,
            user_id=user.id,
            existing_status="refund_pending",
        )
        raise RefundAlreadyRequested()
    if payment.status != "success":
        raise PaymentNotRefundable()

    # 5. 청약철회 조건 서버 재검증 (클라이언트 우회 방어)
    eligible, qa_count, days_since, reason_code = (
        await _evaluate_cooling_off_eligibility(payment, sub, db)
    )
    if not eligible:
        logger.info(
            "billing.refund.not_eligible",
            user_id=user.id,
            payment_id=payment.id,
            reason_code=reason_code,
        )
        raise RefundNotEligible(reason_code or "period_exceeded")

    # 6. 환불 실행
    return await _execute_cooling_off_refund(payment, qa_count, days_since, db)


async def _find_latest_success_payment(
    user_id: int, subscription_id: int, db: AsyncSession
) -> Payment | None:
    """주어진 구독의 가장 최근 success payment를 반환한다 (read-only)."""
    from sqlalchemy import desc

    stmt = (
        select(Payment)
        .where(
            Payment.user_id == user_id,
            Payment.subscription_id == subscription_id,
            Payment.status == "success",
        )
        .order_by(desc(Payment.charged_at))
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _evaluate_cooling_off_eligibility(
    payment: Payment, subscription: Subscription, db: AsyncSession
) -> tuple[bool, int, int, str | None]:
    """청약철회 조건 검증 — 7일 이내 + qa_logs 0건.

    Returns:
        (eligible, qa_count, days_since, reason_code)
        reason_code ∈ {None(eligible), "period_exceeded", "qa_count_exceeded", "both"}.
    """
    from sqlalchemy import func as sa_func

    from api.src.models.qa_log import QALog

    now = datetime.now(UTC)
    days_since = (now - payment.charged_at).days if payment.charged_at else 999

    qa_result = await db.execute(
        select(sa_func.count(QALog.id)).where(
            QALog.user_id == payment.user_id,
            QALog.created_at >= subscription.started_at,
            QALog.created_at <= subscription.current_period_end,
        )
    )
    qa_count = int(qa_result.scalar() or 0)

    period_ok = days_since <= _COOLING_OFF_DAYS_LIMIT
    qa_ok = qa_count == 0

    if period_ok and qa_ok:
        return True, qa_count, days_since, None
    if not period_ok and not qa_ok:
        return False, qa_count, days_since, "both"
    if not period_ok:
        return False, qa_count, days_since, "period_exceeded"
    return False, qa_count, days_since, "qa_count_exceeded"


async def _execute_cooling_off_refund(
    payment: Payment,
    qa_count: int,
    days_since: int,
    db: AsyncSession,
) -> dict:
    """청약철회 환불 실행 — PG 전액 호출 + DB 강제 전이 + 알림 fire-and-forget."""
    # refund_pending로 전이 + commit (lock release; 동시 진입 차단은 status로 보장)
    payment.status = "refund_pending"
    await db.commit()

    pg = get_pg_provider()
    truncated_reason = _COOLING_OFF_REASON[:_TOSS_CANCEL_REASON_MAX]

    try:
        result = await pg.refund(
            payment.provider_order_id,
            payment.amount_krw,
            truncated_reason,
        )
    except Exception:
        # transport 장애 — 원복(흔적 미생성) + 502
        payment.status = "success"
        await db.commit()
        logger.warning(
            "billing.refund.cooling_off_failed",
            payment_id=payment.id,
            user_id=payment.user_id,
            failure_kind="transport",
            pg_error_code=None,
        )
        raise RefundProviderUnavailable("transport_failure") from None

    if not result["success"]:
        # 4xx — refund_denied 이벤트 보존 + status 원복 + 502
        payment.status = "success"
        raw_response = result.get("raw_response") or {}
        db.add(
            PaymentEvent(
                payment_id=payment.id,
                event_type="refund_denied",
                refund_kind="cooling_off",
                raw_response_json=raw_response,
            )
        )
        await db.commit()
        pg_error_code = (
            raw_response.get("code") if isinstance(raw_response, dict) else None
        )
        logger.warning(
            "billing.refund.cooling_off_failed",
            payment_id=payment.id,
            user_id=payment.user_id,
            failure_kind="api_4xx",
            pg_error_code=pg_error_code,
        )
        raise RefundProviderUnavailable("api_4xx", pg_error_code=pg_error_code)

    # 성공: payment + payment_events + subscription + user 강제 전이
    now = datetime.now(UTC)
    payment.status = "refunded"
    raw_response = result.get("raw_response") or {}
    db.add(
        PaymentEvent(
            payment_id=payment.id,
            event_type="refund_success",
            refund_kind="cooling_off",
            # JSONB 인라인 refund_kind는 마이그 0035 도입 후에도 한 사이클 호환 유지.
            raw_response_json={
                "refund_kind": "cooling_off",
                "refund_amount_krw": payment.amount_krw,
                "pg": raw_response,
            },
        )
    )

    sub_result = await db.execute(
        select(Subscription)
        .where(Subscription.id == payment.subscription_id)
        .with_for_update()
    )
    sub = sub_result.scalar_one()
    sub.status = "canceled"
    sub.next_charge_at = None
    sub.canceled_at = now
    sub.cancel_reason = "cooling_off_refund"

    await db.execute(
        sa_update(User)
        .where(User.id == payment.user_id)
        .values(subscription_status="free")
    )
    # PG 환불은 이미 성공 — 최종 DB 전이는 한 트랜잭션으로 묶어 원자성 유지.
    # commit 실패 시 payment.status='refund_pending'으로 남고 PG는 이미 환불된 상태이므로
    # 운영자 reconcile이 가능하도록 식별자를 강하게 남기고 예외는 숨기지 않는다.
    try:
        await db.commit()
    except Exception as commit_exc:
        logger.error(
            "billing.refund.commit_failed_after_pg_success",
            payment_id=payment.id,
            user_id=payment.user_id,
            subscription_id=payment.subscription_id,
            provider_order_id=payment.provider_order_id,
            amount_krw=payment.amount_krw,
            raw_response=raw_response,
            error=str(commit_exc),
            error_type=commit_exc.__class__.__name__,
        )
        raise

    logger.info(
        "billing.refund.cooling_off_succeeded",
        payment_id=payment.id,
        user_id=payment.user_id,
        subscription_id=sub.id,
        amount_krw=payment.amount_krw,
        days_since_charge=days_since,
    )

    # fire-and-forget 알림 — 실패해도 환불 결과에 영향 없음
    try:
        await _notify_refund(
            user_id=payment.user_id,
            amount_krw=payment.amount_krw,
            refund_amount_krw=payment.amount_krw,
            refunded_at=now,
            payment_id=payment.id,
            refund_reason="cooling_off",
            idempotency_key=f"refund:{payment.id}:cooling_off",
        )
    except Exception:
        pass

    return {
        "status": "refunded",
        "refund_kind": "cooling_off",
        "amount_krw": payment.amount_krw,
        "refunded_at": now.isoformat(),
        "subscription_status": "canceled",
    }


_REFUND_REASON_LABELS = {
    "cooling_off": "즉시 해지 및 전액 환불",
    "manual_full": "전액 환불",
    "manual_partial": "부분 환불",
}


async def _notify_refund(
    user_id: int,
    amount_krw: int,
    refund_amount_krw: int,
    refunded_at: datetime,
    payment_id: int,
    refund_reason: str,
    idempotency_key: str,
) -> None:
    """환불 성공 알림 fire-and-forget — _notify_subscription_event 패턴.

    Story 3.6 v1.1 청약철회 + Story 9.1 v1.1 운영 환불(부분/전액) 공용.
    refund_reason ∈ {"cooling_off", "manual_full", "manual_partial"} →
    `refund_reason_label` 한국어로 매핑되어 알림톡 본문에 노출된다.
    """
    try:
        from api.src.models.base import async_session_factory

        async with async_session_factory() as db:
            result = await db.execute(
                select(User).where(User.id == user_id, User.withdrawn_at.is_(None))
            )
            user = result.scalar_one_or_none()
            if user is None:
                return

        from api.src.integrations.messaging.notification_service import (
            get_notification_service,
        )

        label = _REFUND_REASON_LABELS.get(refund_reason, refund_reason)

        svc = get_notification_service()
        await svc.send(
            user_id=user_id,
            phone=user.phone or "",
            template_code="billing.refund_success",
            variables={
                "refund_reason_label": label,
                "amount_krw": f"{amount_krw:,}",
                "refund_amount_krw": f"{refund_amount_krw:,}",
                "effective_at": refunded_at.strftime("%Y년 %m월 %d일"),
            },
            idempotency_key=idempotency_key,
        )
    except Exception:
        logger.warning(
            "billing.refund.notify.failed",
            user_id=user_id,
            payment_id=payment_id,
        )


# ── 예외 클래스 ───────────────────────────────────────────────────────────────


class BillingCardDeclined(Exception):
    """카드 결제가 거절됨."""

    def __init__(self, pg_error_code: str, message: str) -> None:
        super().__init__(message)
        self.pg_error_code = pg_error_code


class SubscriptionAlreadyActive(Exception):
    """이미 Pro 구독이 활성화된 사용자."""


class BillingKeyRequired(Exception):
    """활성 빌링키가 없어 구독을 시작할 수 없음."""


class SubscriptionNotFound(Exception):
    """활성/대기 구독을 찾을 수 없음."""


class SubscriptionAlreadyCanceled(Exception):
    """이미 종료된 구독에 대한 cancel/resume 시도."""


class ResumeNotApplicable(Exception):
    """철회 대상 구독이 없음(active 단독 제외)."""


# ── Story 3.6 예외 ───────────────────────────────────────────────────────────


class PaymentNotFound(Exception):
    """결제 미존재 또는 타인 결제(404 enumeration 차단).

    Story 9.1 v1.1 관리자 환불 다이얼로그에서 재사용 가능. v1.1 사용자 동선은
    구독 → 결제를 서비스가 직접 조회하므로 직접 raise하지 않는다.
    """


class PaymentNotRefundable(Exception):
    """status가 success가 아닌 환불 불가 결제(failed/pending 등)."""


class RefundAlreadyProcessed(Exception):
    """이미 환불된 결제에 대한 재요청."""


class RefundAlreadyRequested(Exception):
    """이미 환불 요청 중(refund_pending)인 결제."""


class NoActiveSubscription(Exception):
    """청약철회 대상 활성/대기 구독이 없음 (Story 3.6 v1.1)."""


class NoRefundablePayment(Exception):
    """청약철회 대상 success payment가 없음 (Story 3.6 v1.1)."""


class RefundNotEligible(Exception):
    """청약철회 조건 미충족 — 7일 초과 또는 질문 1건 이상 (Story 3.6 v1.1).

    클라이언트 사전 조회(AC1)를 우회한 직접 호출 방어용. 라우터에서 422로 매핑.
    reason_code ∈ {"period_exceeded", "qa_count_exceeded", "both"}.
    """

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class RefundProviderUnavailable(Exception):
    """PG transport 장애 또는 4xx 응답 — 502 매핑."""

    def __init__(self, failure_kind: str, pg_error_code: str | None = None) -> None:
        super().__init__(failure_kind)
        self.failure_kind = failure_kind
        self.pg_error_code = pg_error_code
