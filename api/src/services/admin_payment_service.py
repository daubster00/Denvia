"""Admin 운영 환불 v1.1 — 환불 실행 서비스 (T9, Story 9.1 v1.1).

ADR-0001 편차 #5 환불 정책 v1.1. 관리자가 결제 건당 환불 금액을 자유 입력해 부분/전액
환불을 실행하는 단일 엔드포인트(`POST /api/v1/admin/payments/{payment_id}/refunds`)의
서비스 본체. read-only 계산은 `refund_quote_service`가, 실제 INSERT/PG 호출은 본 모듈이
담당한다.

v1.0 자가 환불 폼(Story 9.3 — `manual_refund_queue` 승인 큐 기반, Phase 4에서 삭제됨)과
대비되는 v1.1 운영 환불 흐름의 특징:
1. 큐 row가 없다 — payment_id로 직접 진입.
2. 다회 부분환불을 지원한다 — `refunds` 테이블에 시계열 row INSERT, `refund_sequence`로 순번 보존.
3. 잔액(payment.amount_krw − SUM(cancel_amount))이 0이 될 때만 `payment.status='refunded'`로
   마감한다. **subscription cancel + user.subscription_status='free'는 부분/전액 무관
   모든 환불에서 즉시 수행**한다 (2026-05-28 정책 — 환불=서비스 종료 의사,
   장애 보상은 별도 구독 일수 연장 경로 사용).
4. 멱등 키 패턴: `refund:{payment_id}:manual:{refund_sequence}` — 동일 결제 다회 환불
   누적을 지원하기 위해 sequence를 키에 포함한다.

9 테이블 전이(모든 환불): refunds INSERT → payment_events INSERT → payment UPDATE(잔액 0일 때만
'refunded') → subscription UPDATE(canceled) → user UPDATE(free) → inbox_messages INSERT →
audit_logs (미들웨어가 INSERT) → notification_queue (fire-and-forget) → admin events
(fire-and-forget Redis publish). 부분/전액 무관 환불 즉시 구독 종료
(2026-05-28 정책 — 장애 보상은 별도 구독 일수 연장 경로 사용).

설계 노트:
- payment를 `SELECT ... FOR UPDATE`로 잠그면 동일 결제의 동시 환불 요청은 직렬화된다.
  refunds 행 잠금은 별도로 잡지 않는다 — `uq_refunds_payment_sequence`가 race 차단.
- PG 호출은 `with_for_update`로 잠겨 있는 동안 수행한다. PG가 느릴 경우 타 admin은 동일
  payment에 대해 대기하지만, 동일 결제에 대한 환불은 본질적으로 직렬이어야 안전하므로
  이 비용은 의도된 것이다.
- transport 장애 → 즉시 rollback + 502. PG 4xx → `refund_denied` 이벤트 보존 후 commit + 502.
  성공 응답 후 commit 실패 → 환불은 PG에 이미 반영되었으므로 reconcile 식별자를 강하게 로깅하고
  예외는 숨기지 않는다.
- 알림톡 발송은 `billing.refund_manual`(UI_1758) 전용 템플릿을 사용한다 (docs/ALIMTALK_TEMPLATES.md §6 18번).
  본문에 처리 유형 라벨이 없어 manual_full/manual_partial 모두 동일 본문으로 발송된다.
  청약철회(cooling_off)는 본 서비스가 다루지 않으며 billing_service._notify_refund 경로에서
  `billing.refund_success`(UH_9832)로 별도 발송된다.
- audit_diff는 잔액·sequence·reason_category·memo 길이·여부 등 사후 추적에 필요한 메타만 담는다.
  메모 원문은 audit에 남기지 않는다 (PII 가능성 있음 → `refunds.memo`에만 보존).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from fastapi import HTTPException, Request
from sqlalchemy import func, select, update as sa_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.integrations.payment import get_pg_provider
from api.src.middleware.audit_actions import AUDIT_REFUND_OPERATIONAL_CREATE
from api.src.models.inbox_message import InboxMessage
from api.src.models.payment import Payment
from api.src.models.payment_event import PaymentEvent
from api.src.models.refund import Refund
from api.src.models.subscription import Subscription
from api.src.models.user import User
from api.src.schemas.admin.payment_refunds import (
    RefundCreateRequest,
    RefundCreateResponse,
    RefundListItem,
    RefundListResponse,
)
from api.src.utils.html_sanitize import sanitize_body_html
from api.src.utils.mask import mask_email

logger = structlog.get_logger(__name__)

_KST = ZoneInfo("Asia/Seoul")
# 토스 페이먼츠 cancelReason 한도.
_TOSS_CANCEL_REASON_MAX = 200
_INBOX_TITLE_FULL = "환불 처리 완료 안내"
_INBOX_TITLE_PARTIAL = "부분 환불 처리 완료 안내"
# 2026-05-26 — 운영 환불은 `billing.refund_manual`(UI_1758) 전용 템플릿으로 분리.
# 본문에 처리 유형 라벨을 노출하지 않으므로 별도 라벨 매핑 없이 발송한다.
# 참고: 청약철회(cooling_off)는 여전히 `billing.refund_success`(UH_9832)를 사용하며,
# 그쪽의 라벨 매핑은 billing_service._REFUND_REASON_LABELS만 유지.


async def create_refund(
    request: Request,
    db: AsyncSession,
    payment_id: int,
    payload: RefundCreateRequest,
    *,
    admin_id: int,
) -> RefundCreateResponse:
    """관리자 운영 환불(부분/전액) 실행.

    동작:
    1. payment를 `FOR UPDATE`로 잠근다 → 동일 결제 동시 환불 직렬화.
    2. refunds SUM·MAX를 재계산해 잔액과 다음 sequence를 결정.
    3. PG `cancel` 호출.
       - transport 장애: rollback + 502 PG_REFUND_UNAVAILABLE
       - 4xx 거절: refund_denied 이벤트 INSERT + commit + 502 PG_REFUND_FAILED
    4. 성공 시 refunds INSERT + payment_events refund_success INSERT.
    5. **모든 환불에서** subscription cancel + user.subscription_status='free' 즉시 적용.
       잔액이 0이 될 때만 payment.status='refunded'로 마감. 부분환불 후에도 구독은 종료
       (2026-05-28 정책 — 환불=서비스 종료 의사, 장애 보상은 구독 일수 연장 경로 사용).
    6. inbox_messages INSERT + audit_diff/state 설정 → commit.
    7. 라우터가 본 함수 반환 후 background_tasks로 알림톡·Redis publish를 발행한다 — 본 함수는
       `request.state`에 후처리 페이로드만 박아둔다.

    Raises:
        HTTPException 404 — payment_id 없음.
        HTTPException 409 — payment.status가 환불 불가 상태(예: pending/failed/refund_pending)
                            또는 잔액이 cancel_amount 미만.
        HTTPException 502 — PG transport 장애 또는 4xx 거절.
    """
    payment = (
        await db.execute(
            select(Payment).where(Payment.id == payment_id).with_for_update()
        )
    ).scalar_one_or_none()
    if payment is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "PAYMENT_NOT_FOUND", "message": "결제를 찾을 수 없습니다."},
        )

    # status 가드 — 운영 환불은 'success'에서만 가능.
    # 'refunded'는 잔액 0이라 본질적으로 더 환불할 수 없고, 'pending'/'failed'/'refund_pending'은
    # PG가 거절하거나 회계 오염을 일으킬 수 있어 명시적으로 차단한다.
    if payment.status != "success":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "PAYMENT_NOT_REFUNDABLE",
                "message": "환불 가능한 결제 상태가 아닙니다.",
                "current_status": payment.status,
            },
        )

    refunded_total, next_sequence = await _aggregate_refunds(db, payment_id)
    refundable_balance = payment.amount_krw - refunded_total

    if refundable_balance <= 0:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "NO_REFUNDABLE_BALANCE",
                "message": "이 결제는 이미 전액 환불되었습니다.",
                "refundable_balance": refundable_balance,
            },
        )
    if payload.cancel_amount > refundable_balance:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CANCEL_AMOUNT_EXCEEDS_BALANCE",
                "message": "환불 금액이 잔액을 초과합니다.",
                "refundable_balance": refundable_balance,
                "requested": payload.cancel_amount,
            },
        )

    idempotency_key = f"refund:{payment_id}:manual:{next_sequence}"
    # PG에 전달할 cancelReason — 관리자 메모를 우선하고, 없으면 reason_category enum 값을 사용.
    cancel_reason_for_pg = (
        (payload.memo or payload.reason_category)[:_TOSS_CANCEL_REASON_MAX]
    )

    # 전액/부분 판정 — sequence==1 AND cancel_amount==amount_krw일 때만 'manual_full'.
    # 다회 부분환불 누적으로 잔액이 0이 되더라도 'manual_partial'로 본다 (단발 전액과 회계 구분).
    is_full_single_shot = (
        next_sequence == 1 and payload.cancel_amount == payment.amount_krw
    )
    refund_reason = "manual_full" if is_full_single_shot else "manual_partial"

    pg = get_pg_provider()
    try:
        result = await pg.refund(
            payment.provider_order_id, payload.cancel_amount, cancel_reason_for_pg
        )
    except Exception:
        logger.warning(
            "admin.payments.refund.transport_failure",
            payment_id=payment_id,
            admin_id=admin_id,
            cancel_amount=payload.cancel_amount,
        )
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
                refund_kind=refund_reason,
                raw_response_json={
                    "refund_kind": refund_reason,
                    "attempted_cancel_amount": payload.cancel_amount,
                    "attempted_sequence": next_sequence,
                    "pg": raw,
                },
            )
        )
        await db.commit()
        pg_error_code = raw.get("code") if isinstance(raw, dict) else None
        pg_error_message = raw.get("message") if isinstance(raw, dict) else None
        logger.warning(
            "admin.payments.refund.pg_failed",
            payment_id=payment_id,
            admin_id=admin_id,
            cancel_amount=payload.cancel_amount,
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

    now = datetime.now(UTC)
    now_kst = now.astimezone(_KST)
    raw_response: dict[str, Any] = result.get("raw_response") or {}

    refund_row = Refund(
        payment_id=payment.id,
        admin_id=admin_id,
        cancel_amount=payload.cancel_amount,
        original_payment_amount=payment.amount_krw,
        prorated_suggestion=None,
        reason_category=payload.reason_category,
        memo=payload.memo,
        refund_sequence=next_sequence,
        toss_response_json=raw_response,
        idempotency_key=idempotency_key,
    )
    db.add(refund_row)

    db.add(
        PaymentEvent(
            payment_id=payment.id,
            event_type="refund_success",
            refund_kind=refund_reason,
            raw_response_json={
                "refund_kind": refund_reason,
                "refund_amount_krw": payload.cancel_amount,
                "refund_sequence": next_sequence,
                "pg": raw_response,
            },
        )
    )

    new_total = refunded_total + payload.cancel_amount
    is_fully_refunded = new_total >= payment.amount_krw

    # 잔액이 0이 되면 payment를 'refunded'로 마감(회계상 잔액 0 표시).
    # 부분환불이 누적되지 않은 시점에는 payment.status='success'를 유지해 추가 환불 여지를 남긴다.
    if is_fully_refunded:
        payment.status = "refunded"

    # 2026-05-28 정책 — 환불은 부분/전액 무관 즉시 구독 종료.
    # 환불은 사용자의 서비스 종료 의사로 본다. 시스템 장애 보상은 환불이 아니라
    # 별도 "구독 일수 연장" 경로(추후 구현)를 사용한다.
    if payment.subscription_id is not None:
        sub_row = (
            await db.execute(
                select(Subscription)
                .where(Subscription.id == payment.subscription_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if sub_row is not None and sub_row.status != "canceled":
            sub_row.status = "canceled"
            sub_row.next_charge_at = None
            sub_row.canceled_at = now
            sub_row.cancel_reason = "manual_admin_refund"
    await db.execute(
        sa_update(User)
        .where(User.id == payment.user_id)
        .values(subscription_status="free")
    )

    inbox_title = _INBOX_TITLE_FULL if is_full_single_shot else _INBOX_TITLE_PARTIAL
    inbox_body = _render_inbox_body(
        cancel_amount=payload.cancel_amount,
        original_amount=payment.amount_krw,
        refunded_total_after=new_total,
        is_fully_refunded=is_fully_refunded,
        is_full_single_shot=is_full_single_shot,
        processed_at_kst=now_kst,
    )
    db.add(
        InboxMessage(
            user_id=payment.user_id,
            notice_id=None,
            popup_id=None,
            type="billing",
            title=inbox_title,
            body_html=sanitize_body_html(inbox_body),
        )
    )

    # 감사 메타 — 메모 원문은 남기지 않고 길이·여부만 기록.
    request.state.audit_action = AUDIT_REFUND_OPERATIONAL_CREATE
    request.state.audit_target_type = "payment"
    request.state.audit_target_id = payment.id
    request.state.audit_diff = json.dumps(
        {
            "payment_id": payment.id,
            "cancel_amount": payload.cancel_amount,
            "original_payment_amount": payment.amount_krw,
            "refunded_total_after": new_total,
            "refund_sequence": next_sequence,
            "reason_category": payload.reason_category,
            "memo_length": len(payload.memo) if payload.memo else 0,
            "refund_reason": refund_reason,
            "is_fully_refunded": is_fully_refunded,
            "idempotency_key": idempotency_key,
        },
        ensure_ascii=False,
    )

    # fire-and-forget 페이로드를 라우터로 전달.
    request.state.refund_op_user_id = payment.user_id
    request.state.refund_op_payment_id = payment.id
    request.state.refund_op_amount_krw = payment.amount_krw  # 결제 원금
    request.state.refund_op_cancel_amount = payload.cancel_amount  # 이번 환불
    request.state.refund_op_refund_reason = refund_reason
    request.state.refund_op_idempotency_key = idempotency_key
    request.state.refund_op_now = now

    try:
        await db.commit()
    except IntegrityError as exc:
        # uq_refunds_payment_sequence 또는 uq_refunds_idempotency_key 충돌 → 동시 요청 race.
        # PG는 이미 환불됐을 수 있어 reconcile 식별자를 강하게 로깅한다.
        logger.error(
            "admin.payments.refund.commit_unique_violation",
            payment_id=payment.id,
            admin_id=admin_id,
            cancel_amount=payload.cancel_amount,
            refund_sequence=next_sequence,
            idempotency_key=idempotency_key,
            provider_order_id=payment.provider_order_id,
            error=str(exc),
        )
        raise HTTPException(
            status_code=409,
            detail={
                "code": "REFUND_RACE_DETECTED",
                "message": "동시 환불 요청이 감지되었습니다. PG에 이미 처리되었을 수 있으니 잠시 후 환불 이력을 확인해주세요.",
            },
        ) from None
    except Exception as exc:
        logger.error(
            "admin.payments.refund.commit_failed_after_pg_success",
            payment_id=payment.id,
            admin_id=admin_id,
            cancel_amount=payload.cancel_amount,
            refund_sequence=next_sequence,
            idempotency_key=idempotency_key,
            provider_order_id=payment.provider_order_id,
            raw_response=raw_response,
            error=str(exc),
            error_type=exc.__class__.__name__,
        )
        raise

    logger.info(
        "admin.payments.refund.created",
        payment_id=payment.id,
        admin_id=admin_id,
        cancel_amount=payload.cancel_amount,
        refund_sequence=next_sequence,
        refund_reason=refund_reason,
        is_fully_refunded=is_fully_refunded,
    )

    return RefundCreateResponse(
        refund_id=refund_row.id,
        refund_sequence=next_sequence,
        cancel_amount=payload.cancel_amount,
        refunded_at=now,
    )


async def _aggregate_refunds(
    db: AsyncSession, payment_id: int
) -> tuple[int, int]:
    """기존 환불 누적 합계 + 다음 sequence를 1쿼리로 조회한다.

    Returns:
        (refunded_total, next_refund_sequence)
    """
    row = (
        await db.execute(
            select(
                func.coalesce(func.sum(Refund.cancel_amount), 0),
                func.coalesce(func.max(Refund.refund_sequence), 0),
            ).where(Refund.payment_id == payment_id)
        )
    ).one()
    return int(row[0]), int(row[1]) + 1


def _render_inbox_body(
    *,
    cancel_amount: int,
    original_amount: int,
    refunded_total_after: int,
    is_fully_refunded: bool,
    is_full_single_shot: bool,
    processed_at_kst: datetime,
) -> str:
    """쪽지함 본문 HTML 렌더 — sanitize 전 raw.

    2026-05-28 정책 — 부분/전액 무관 모든 환불에서 구독이 함께 종료되므로
    세 케이스 모두 "구독 종료" 안내 문장을 포함한다.
    """
    date_label = processed_at_kst.strftime("%Y년 %m월 %d일")
    common_footer = (
        f"<p>처리일: {date_label}</p>"
        f"<p>영업일 3~4일 내 결제 카드로 입금됩니다.</p>"
        f"<p>환불 처리와 함께 구독이 종료되었습니다.</p>"
    )
    if is_full_single_shot:
        return (
            f"<p>요청하신 환불이 <strong>완료</strong>되었습니다.</p>"
            f"<p>환불 금액: {cancel_amount:,}원 (전액)</p>"
            f"{common_footer}"
        )
    if is_fully_refunded:
        return (
            f"<p>이번 회차 부분 환불이 <strong>완료</strong>되었습니다.</p>"
            f"<p>이번 환불 금액: {cancel_amount:,}원</p>"
            f"<p>누적 환불 금액: {refunded_total_after:,}원 / {original_amount:,}원 (전액 환불 완료)</p>"
            f"{common_footer}"
        )
    return (
        f"<p>요청하신 <strong>부분 환불</strong>이 완료되었습니다.</p>"
        f"<p>이번 환불 금액: {cancel_amount:,}원</p>"
        f"<p>누적 환불 금액: {refunded_total_after:,}원 / {original_amount:,}원</p>"
        f"{common_footer}"
    )


async def list_refunds(
    db: AsyncSession, payment_id: int
) -> RefundListResponse:
    """결제별 환불 이력 목록 — 시계열(created_at ASC) 정렬.

    Refund + 처리 관리자 User를 1쿼리 JOIN으로 조회한다. 페이지네이션 없음
    (단일 결제당 환불 row 수가 매우 적다는 전제).

    Raises:
        HTTPException 404 — payment_id에 해당하는 결제가 없을 때.
    """
    payment_exists = (
        await db.execute(select(Payment.id).where(Payment.id == payment_id))
    ).scalar_one_or_none()
    if payment_exists is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "PAYMENT_NOT_FOUND", "message": "결제를 찾을 수 없습니다."},
        )

    rows = (
        await db.execute(
            select(
                Refund.id,
                Refund.refund_sequence,
                Refund.cancel_amount,
                Refund.reason_category,
                Refund.memo,
                Refund.created_at,
                User.email.label("admin_email"),
            )
            .join(User, User.id == Refund.admin_id)
            .where(Refund.payment_id == payment_id)
            .order_by(Refund.created_at.asc(), Refund.id.asc())
        )
    ).all()

    items = [
        RefundListItem(
            id=r.id,
            refund_sequence=r.refund_sequence,
            cancel_amount=r.cancel_amount,
            reason_category=r.reason_category,
            memo=r.memo,
            admin_email_masked=mask_email(r.admin_email),
            created_at=r.created_at,
        )
        for r in rows
    ]
    return RefundListResponse(items=items, total=len(items))


async def notify_refund_succeeded(
    *,
    user_id: int,
    payment_id: int,
    amount_krw: int,
    refund_amount_krw: int,
    refund_reason: str,
    refunded_at: datetime,
    idempotency_key: str,
) -> None:
    """fire-and-forget 알림톡 — billing.refund_manual (UI_1758, 운영 환불 전용).

    2026-05-26 분리: 청약철회(cooling_off)는 `billing.refund_success`(UH_9832), 운영
    환불(manual_full/manual_partial)은 `billing.refund_manual`(UI_1758)로 본문 톤이
    분리되었다. 본 함수는 관리자 페이지 환불 라우터에서만 호출되므로 항상 후자를 쓴다.
    `refund_reason` 인자는 후속 로깅·시그니처 호환을 위해 유지하지만 본문에는 노출되지 않는다.

    docs/ALIMTALK_TEMPLATES.md §6 변수:
    - amount_krw: 결제 원금 (콤마 포함 텍스트)
    - refund_amount_krw: 이번 환불 금액 (콤마 포함 텍스트)
    - effective_at: 처리일 KST 표기 (YYYY년 MM월 DD일)
    """
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
            template_code="billing.refund_manual",
            variables={
                "amount_krw": f"{amount_krw:,}",
                "refund_amount_krw": f"{refund_amount_krw:,}",
                "effective_at": refunded_at.astimezone(_KST).strftime("%Y년 %m월 %d일"),
            },
            idempotency_key=idempotency_key,
        )
    except Exception:
        logger.warning(
            "admin.payments.refund.notify_failed",
            user_id=user_id,
            payment_id=payment_id,
            refund_reason=refund_reason,
        )


async def publish_admin_event(payload: dict) -> None:
    """fire-and-forget Redis admin:events 채널 publish."""
    try:
        from api.src.deps.redis import get_redis_client

        redis = get_redis_client()
        await redis.publish("admin:events", json.dumps(payload, ensure_ascii=False))
    except Exception:
        logger.warning("admin.payments.refund.sse_publish_failed", payload=payload)


__all__ = [
    "create_refund",
    "list_refunds",
    "notify_refund_succeeded",
    "publish_admin_event",
]
