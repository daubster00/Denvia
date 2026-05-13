# DEPRECATED v1.1 (ADR-0001 편차 #5, 2026-05-13) — 신규 흐름은 admin_payment_service.create_refund.
# 본 모듈은 폐지된 사용자 자가 환불 폼(POST /billing/payments/{id}/refund) → manual_refund_queue
# 큐 → 관리자 approve/deny 흐름의 잔여물이다. 자가 환불 폼은 Story 3.6 v1.1 Phase 1에서
# `cancel-with-refund`(청약철회 단일 경로)로 통합되며 폐기되었고, 관리자 환불은 본 v1.1에서
# `POST /api/v1/admin/payments/{payment_id}/refunds`로 단일화되었다. manual_refund_queue 테이블
# 자체와 본 모듈의 실제 제거는 Phase 3에서 결정한다(잔여 큐 row가 0건임을 확인한 후).
# 신규 환불 작업은 절대 본 모듈을 import하지 말 것.
"""Admin 수동 환불 검토 서비스 (Story 9.3 A-503) — [DEPRECATED v1.1].

GET   list_queue   manual_refund_queue 목록 (status/from/to/q + 페이지네이션)
POST  approve      PG refund 호출 + payment.status='refunded' + 알림톡 + 쪽지함 + SSE
POST  deny         payment.status 원복 + 알림톡(거부) + 쪽지함 + SSE

3.6 _execute_auto_refund 패턴 답습:
- with_for_update()로 queue + payment 동시 잠금
- payment_events INSERT → payment.status 전이 → subscription cancel → user.subscription_status='free'
- commit 후 알림톡 fire-and-forget + Redis admin:events publish
"""

from __future__ import annotations

import html as _html
import json
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import structlog
from fastapi import HTTPException, Request
from sqlalchemy import case, desc, func, or_, select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.integrations.payment import get_pg_provider
from api.src.middleware.audit_actions import (
    AUDIT_REFUND_MANUAL_APPROVE,
    AUDIT_REFUND_MANUAL_DENY,
)
from api.src.models.billing_key import BillingKey
from api.src.models.inbox_message import InboxMessage
from api.src.models.manual_refund_queue import ManualRefundQueue
from api.src.models.payment import Payment
from api.src.models.payment_event import PaymentEvent
from api.src.models.subscription import Subscription
from api.src.models.user import User
from api.src.schemas.admin.refunds import (
    RefundActionResponse,
    RefundQueueItem,
    RefundQueueListResponse,
)
from api.src.services.analytics_service import _mask_email
from api.src.utils.html_sanitize import sanitize_body_html

logger = structlog.get_logger(__name__)

_TOSS_CANCEL_REASON_MAX = 200
_INBOX_TITLE_APPROVED = "환불 요청 승인 안내"
_INBOX_TITLE_DENIED = "환불 요청 거부 안내"
_KST = ZoneInfo("Asia/Seoul")
_VALID_REASON_CODES = {"period_exceeded", "qa_count_exceeded", "both", "no_subscription"}


def _kst_date_range(f: date | None, t: date | None) -> tuple[datetime | None, datetime | None]:
    start_dt: datetime | None = None
    end_dt: datetime | None = None
    if f is not None:
        start_dt = datetime.combine(f, time.min).replace(tzinfo=_KST)
    if t is not None:
        end_dt = datetime.combine(t + timedelta(days=1), time.min).replace(tzinfo=_KST)
    return start_dt, end_dt


def _escape_ilike(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def _fetch_reason_code(db: AsyncSession, payment_id: int) -> str | None:
    """payment_events에서 가장 최근 refund_requested의 raw_response_json.reason_code 추출."""
    stmt = (
        select(PaymentEvent.raw_response_json)
        .where(
            PaymentEvent.payment_id == payment_id,
            PaymentEvent.event_type == "refund_requested",
        )
        .order_by(desc(PaymentEvent.created_at), desc(PaymentEvent.id))
        .limit(1)
    )
    row = (await db.execute(stmt)).first()
    if row is None or not row[0]:
        return None
    raw = row[0]
    code = raw.get("reason_code") if isinstance(raw, dict) else None
    if code in _VALID_REASON_CODES:
        return code
    return None


async def list_queue(
    db: AsyncSession,
    *,
    status: str = "pending",
    f: date | None = None,
    t: date | None = None,
    q: str | None = None,
    page: int = 1,
    per_page: int = 50,
) -> RefundQueueListResponse:
    """수동 환불 큐 목록 — pending FIFO 정렬 + flat 페이지네이션."""
    # latest billing_key for card_last4 / card_company (provider별 1건)
    base = (
        select(
            ManualRefundQueue.id.label("queue_id"),
            ManualRefundQueue.payment_id,
            ManualRefundQueue.user_id,
            User.email.label("user_email"),
            Payment.amount_krw,
            BillingKey.card_last4,
            BillingKey.card_company,
            ManualRefundQueue.days_since_charge,
            ManualRefundQueue.qa_count_during_period,
            ManualRefundQueue.reason.label("reason_text"),
            ManualRefundQueue.requested_at,
            ManualRefundQueue.status,
            ManualRefundQueue.reviewer_user_id,
            ManualRefundQueue.reviewer_note,
            ManualRefundQueue.reviewed_at,
        )
        .join(User, User.id == ManualRefundQueue.user_id)
        .join(Payment, Payment.id == ManualRefundQueue.payment_id)
        .outerjoin(
            BillingKey,
            (BillingKey.user_id == ManualRefundQueue.user_id)
            & (BillingKey.is_active.is_(True)),
        )
    )
    count_q = (
        select(func.count())
        .select_from(ManualRefundQueue)
        .join(User, User.id == ManualRefundQueue.user_id)
        .join(Payment, Payment.id == ManualRefundQueue.payment_id)
    )

    filters = []
    if status in ("pending", "approved", "denied"):
        filters.append(ManualRefundQueue.status == status)

    start_dt, end_dt = _kst_date_range(f, t)
    if start_dt is not None:
        filters.append(ManualRefundQueue.requested_at >= start_dt)
    if end_dt is not None:
        filters.append(ManualRefundQueue.requested_at < end_dt)

    if q:
        pattern = f"%{_escape_ilike(q)}%"
        filters.append(
            or_(
                User.email.ilike(pattern, escape="\\"),
                ManualRefundQueue.reason.ilike(pattern, escape="\\"),
            )
        )

    for ftr in filters:
        base = base.where(ftr)
        count_q = count_q.where(ftr)

    total = (await db.execute(count_q)).scalar_one()

    pending_first = case(
        (ManualRefundQueue.status == "pending", 0),
        else_=1,
    )
    rows = (
        await db.execute(
            base.order_by(pending_first, ManualRefundQueue.requested_at.asc(), ManualRefundQueue.id.asc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
    ).all()

    # reviewer email 조회 — N건이면 1쿼리로 (이미 review 완료된 row만)
    reviewer_ids = {r.reviewer_user_id for r in rows if r.reviewer_user_id is not None}
    reviewer_email_map: dict[int, str] = {}
    if reviewer_ids:
        rev_rows = (
            await db.execute(select(User.id, User.email).where(User.id.in_(reviewer_ids)))
        ).all()
        reviewer_email_map = {rr.id: rr.email for rr in rev_rows}

    items: list[RefundQueueItem] = []
    for r in rows:
        reason_code = await _fetch_reason_code(db, r.payment_id)
        reviewer_masked = (
            _mask_email(reviewer_email_map[r.reviewer_user_id])
            if r.reviewer_user_id is not None and r.reviewer_user_id in reviewer_email_map
            else None
        )
        items.append(
            RefundQueueItem(
                queue_id=r.queue_id,
                payment_id=r.payment_id,
                user_id=r.user_id,
                user_email_masked=_mask_email(r.user_email),
                amount_krw=r.amount_krw,
                card_last4=r.card_last4,
                card_company=r.card_company,
                days_since_charge=r.days_since_charge,
                qa_count_during_period=r.qa_count_during_period,
                reason_code=reason_code,
                reason_text=r.reason_text,
                requested_at=r.requested_at,
                status=r.status,
                reviewer_user_email_masked=reviewer_masked,
                reviewer_note=r.reviewer_note,
                reviewed_at=r.reviewed_at,
            )
        )

    return RefundQueueListResponse(items=items, page=page, per_page=per_page, total=total)


async def count_pending(db: AsyncSession) -> int:
    """탭 카운트 — status='pending' 만 집계."""
    return (
        await db.execute(
            select(func.count())
            .select_from(ManualRefundQueue)
            .where(ManualRefundQueue.status == "pending")
        )
    ).scalar_one()


async def _lock_queue_and_payment(
    db: AsyncSession, queue_id: int
) -> tuple[ManualRefundQueue, Payment]:
    queue = (
        await db.execute(
            select(ManualRefundQueue)
            .where(ManualRefundQueue.id == queue_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if queue is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "QUEUE_NOT_FOUND", "message": "환불 요청을 찾을 수 없습니다."},
        )
    payment = (
        await db.execute(
            select(Payment).where(Payment.id == queue.payment_id).with_for_update()
        )
    ).scalar_one()
    return queue, payment


async def approve(
    request: Request,
    db: AsyncSession,
    queue_id: int,
    note: str,
    *,
    admin_id: int,
) -> RefundActionResponse:
    """수동 환불 승인 — PG 호출 + 9 테이블 동시 전이.

    실패 시나리오:
    - queue.status != 'pending' → 409 (이중 처리 방어)
    - payment.status not in ('refund_pending', 'success') → 409
    - PG 4xx → 502 + payment_events refund_denied INSERT
    - PG transport → 502 + rollback
    """
    queue, payment = await _lock_queue_and_payment(db, queue_id)

    if queue.status != "pending":
        raise HTTPException(
            status_code=409,
            detail={"code": "QUEUE_NOT_PENDING", "message": "이미 처리된 요청입니다."},
        )
    if payment.status not in ("refund_pending", "success"):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "PAYMENT_NOT_REFUNDABLE",
                "message": "환불 불가능한 결제 상태입니다.",
                "current_status": payment.status,
            },
        )

    pg = get_pg_provider()
    truncated = note[:_TOSS_CANCEL_REASON_MAX]
    try:
        result = await pg.refund(payment.provider_order_id, payment.amount_krw, truncated)
    except Exception:
        logger.warning(
            "admin.refunds.approve.transport_failure",
            queue_id=queue_id,
            payment_id=payment.id,
            admin_id=admin_id,
        )
        # rollback (with_for_update lock 해제)
        await db.rollback()
        raise HTTPException(
            status_code=502,
            detail={
                "code": "PG_REFUND_UNAVAILABLE",
                "message": "PG 통신 장애. 잠시 후 다시 시도해주세요.",
            },
        ) from None

    if not result.get("success"):
        raw = result.get("raw_response") or {}
        db.add(
            PaymentEvent(
                payment_id=payment.id,
                event_type="refund_denied",
                raw_response_json=raw,
            )
        )
        await db.commit()
        pg_error_code = raw.get("code") if isinstance(raw, dict) else None
        pg_error_message = raw.get("message") if isinstance(raw, dict) else None
        logger.warning(
            "admin.refunds.approve.pg_failed",
            queue_id=queue_id,
            payment_id=payment.id,
            admin_id=admin_id,
            pg_error_code=pg_error_code,
        )
        raise HTTPException(
            status_code=502,
            detail={
                "code": "PG_REFUND_FAILED",
                "message": "PG가 환불을 거부했습니다.",
                "pg_error_code": pg_error_code,
                "pg_error_message": pg_error_message,
            },
        )

    # 성공 — payment / sub / user / queue / payment_events / inbox 동시 전이
    now = datetime.now(UTC)
    # KST 자정~오전 9시 사이 처리 시 UTC 날짜가 전날이 될 수 있으므로 사용자 노출은 항상 KST로 변환
    now_kst = now.astimezone(_KST)
    payment.status = "refunded"
    db.add(
        PaymentEvent(
            payment_id=payment.id,
            event_type="refund_success",
            raw_response_json=result.get("raw_response"),
        )
    )

    if payment.subscription_id is not None:
        sub_row = (
            await db.execute(
                select(Subscription)
                .where(Subscription.id == payment.subscription_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if sub_row is not None:
            sub_row.status = "canceled"
            sub_row.next_charge_at = None
            sub_row.canceled_at = now
            sub_row.cancel_reason = "manual_admin_refund"

    await db.execute(
        sa_update(User).where(User.id == payment.user_id).values(subscription_status="free")
    )

    queue.status = "approved"
    queue.reviewer_user_id = admin_id
    queue.reviewed_at = now
    queue.reviewer_note = note

    db.add(
        InboxMessage(
            user_id=payment.user_id,
            notice_id=None,
            popup_id=None,
            type="billing",
            title=_INBOX_TITLE_APPROVED,
            body_html=sanitize_body_html(
                f"<p>환불 요청이 <strong>승인</strong>되었습니다.</p>"
                f"<p>금액: {payment.amount_krw:,}원</p>"
                f"<p>처리일: {now_kst.strftime('%Y년 %m월 %d일')}</p>"
            ),
        )
    )

    reason_code = await _fetch_reason_code(db, payment.id)

    request.state.audit_action = AUDIT_REFUND_MANUAL_APPROVE
    request.state.audit_target_type = "manual_refund_queue"
    request.state.audit_target_id = queue.id
    request.state.audit_diff = json.dumps(
        {
            "amount_krw": payment.amount_krw,
            "payment_id": payment.id,
            "reason_code": reason_code,
            "note_length": len(note),
        },
        ensure_ascii=False,
    )

    # 라우터의 fire-and-forget post-response를 위해 state에 저장
    request.state.refund_action_kind = "approve"
    request.state.refund_action_user_id = payment.user_id
    request.state.refund_action_payment_id = payment.id
    request.state.refund_action_queue_id = queue.id
    request.state.refund_action_amount_krw = payment.amount_krw
    request.state.refund_action_now = now

    await db.commit()

    logger.info(
        "admin.refunds.approved",
        queue_id=queue.id,
        payment_id=payment.id,
        admin_id=admin_id,
        amount_krw=payment.amount_krw,
    )

    return RefundActionResponse(
        queue_id=queue.id,
        payment_id=payment.id,
        status="approved",
        amount_krw=payment.amount_krw,
        refunded_at=now,
    )


async def deny(
    request: Request,
    db: AsyncSession,
    queue_id: int,
    note: str,
    *,
    admin_id: int,
) -> RefundActionResponse:
    """수동 환불 거부 — payment.status를 success로 원복 + 큐 row를 denied 마감.

    실패 시나리오:
    - queue.status != 'pending' → 409 (이중 처리 방어)
    - payment.status != 'refund_pending' → 409
      (이미 refunded/failed 등으로 전이된 결제를 success로 되살리는 사고 방지)
    """
    queue, payment = await _lock_queue_and_payment(db, queue_id)

    if queue.status != "pending":
        raise HTTPException(
            status_code=409,
            detail={"code": "QUEUE_NOT_PENDING", "message": "이미 처리된 요청입니다."},
        )
    if payment.status != "refund_pending":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "PAYMENT_NOT_REFUND_PENDING",
                "message": "환불 대기 상태가 아닌 결제는 거부 처리할 수 없습니다.",
                "current_status": payment.status,
            },
        )

    now = datetime.now(UTC)
    # 3.6의 _enqueue_manual_review가 payment.status='refund_pending'로 전환 → 거부 시 success 복원
    payment.status = "success"
    queue.status = "denied"
    queue.reviewer_user_id = admin_id
    queue.reviewed_at = now
    queue.reviewer_note = note

    reason_code = await _fetch_reason_code(db, payment.id)

    db.add(
        PaymentEvent(
            payment_id=payment.id,
            event_type="refund_denied",
            raw_response_json={
                "manual_review": True,
                "reviewer_note_length": len(note),
                "reason_code": reason_code,
            },
        )
    )

    db.add(
        InboxMessage(
            user_id=payment.user_id,
            notice_id=None,
            popup_id=None,
            type="billing",
            title=_INBOX_TITLE_DENIED,
            body_html=sanitize_body_html(
                f"<p>환불 요청이 <strong>거부</strong>되었습니다.</p>"
                f"<p>금액: {payment.amount_krw:,}원</p>"
                f"<p>관리자 메모: {_html.escape(note)[:200]}</p>"
            ),
        )
    )

    request.state.audit_action = AUDIT_REFUND_MANUAL_DENY
    request.state.audit_target_type = "manual_refund_queue"
    request.state.audit_target_id = queue.id
    request.state.audit_diff = json.dumps(
        {
            "amount_krw": payment.amount_krw,
            "payment_id": payment.id,
            "reason_code": reason_code,
            "note_length": len(note),
        },
        ensure_ascii=False,
    )

    request.state.refund_action_kind = "deny"
    request.state.refund_action_user_id = payment.user_id
    request.state.refund_action_payment_id = payment.id
    request.state.refund_action_queue_id = queue.id
    request.state.refund_action_amount_krw = payment.amount_krw
    request.state.refund_action_note_summary = note[:80]

    await db.commit()

    logger.info(
        "admin.refunds.denied",
        queue_id=queue.id,
        payment_id=payment.id,
        admin_id=admin_id,
    )

    return RefundActionResponse(
        queue_id=queue.id,
        payment_id=payment.id,
        status="denied",
        amount_krw=payment.amount_krw,
        refunded_at=None,
    )


async def notify_refund_approved(
    *, user_id: int, payment_id: int, amount_krw: int, refunded_at: datetime
) -> None:
    """fire-and-forget 알림톡 — billing.refund_success."""
    try:
        from api.src.integrations.messaging.notification_service import (
            get_notification_service,
        )
        from api.src.models.base import async_session_factory

        async with async_session_factory() as db:
            user = (
                await db.execute(
                    select(User).where(User.id == user_id, User.withdrawn_at.is_(None))
                )
            ).scalar_one_or_none()
        if user is None:
            return
        svc = get_notification_service()
        await svc.send(
            user_id=user_id,
            phone=user.phone or "",
            template_code="billing.refund_success",
            variables={
                "amount_krw": str(amount_krw),
                "effective_at": refunded_at.astimezone(_KST).strftime("%Y년 %m월 %d일"),
            },
            idempotency_key=f"refund:{payment_id}:manual_approve",
        )
    except Exception:
        logger.warning(
            "admin.refunds.approve.notify_failed",
            user_id=user_id,
            payment_id=payment_id,
        )


async def notify_refund_denied(
    *, user_id: int, payment_id: int, reason_summary: str
) -> None:
    """fire-and-forget 알림톡 — billing.refund_denied."""
    try:
        from api.src.integrations.messaging.notification_service import (
            get_notification_service,
        )
        from api.src.models.base import async_session_factory

        async with async_session_factory() as db:
            user = (
                await db.execute(
                    select(User).where(User.id == user_id, User.withdrawn_at.is_(None))
                )
            ).scalar_one_or_none()
        if user is None:
            return
        svc = get_notification_service()
        await svc.send(
            user_id=user_id,
            phone=user.phone or "",
            template_code="billing.refund_denied",
            variables={"reason_summary": reason_summary},
            idempotency_key=f"refund:{payment_id}:manual_deny",
        )
    except Exception:
        logger.warning(
            "admin.refunds.deny.notify_failed",
            user_id=user_id,
            payment_id=payment_id,
        )


async def publish_admin_event(payload: dict) -> None:
    """fire-and-forget Redis admin:events publish."""
    try:
        from api.src.deps.redis import get_redis_client

        redis = get_redis_client()
        await redis.publish("admin:events", json.dumps(payload, ensure_ascii=False))
    except Exception:
        logger.warning("admin.refunds.sse_publish_failed", payload=payload)


__all__ = [
    "list_queue",
    "count_pending",
    "approve",
    "deny",
    "notify_refund_approved",
    "notify_refund_denied",
    "publish_admin_event",
]
