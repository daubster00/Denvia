"""Admin 운영 환불 v1.1 — 환불 입력 화면 참고 계산값 서비스 (T7, Story 9.3 v1.1).

ADR-0001 편차 #5 환불 정책 v1.1. `GET /api/v1/admin/payments/{payment_id}/refund-quote`
응답을 단일 함수 `get_refund_quote(db, payment_id)`로 조립한다.

본 서비스는 **read-only**다. 관리자가 결제별 환불 금액을 자유 입력하기 직전, 화면이 필요한
가드(상한)·권장값(전액/일할)·청약철회 표기·다음 sequence를 한 번에 묶어 반환한다.
실제 환불 INSERT/PG 호출은 후속 단계의 admin_payment_service가 담당한다.

설계 노트:
- KST(Asia/Seoul) 기준 일/날짜 계산. 사용자/관리자에게 노출되는 모든 일자는 KST.
- 청약철회 판정은 billing_service._evaluate_cooling_off_eligibility와 같은 공식
  (7일 이내 AND 질문 0건)을 쓰지만, _대상 payment_의 `subscription_period_start/end`
  스냅샷을 우선 사용한다. billing_service는 "현재 활성 구독의 최신 결제" 컨텍스트라
  `subscription.current_period_end`(미래로 갱신됨)를 쓰지만, 본 함수는 admin이 임의의
  과거 payment를 지목할 수 있어 결제 시점 박제값이 정확하다 (Story 4.4 코드리뷰 후속에서
  payments.subscription_period_* 컬럼이 추가된 동일한 이유).
- 본 응답은 `is_within_cooling_off` 불리언과 두 근거값(결제일·환불 사유 누락 여부 등)만
  반환하므로 reason_code 매핑은 불필요 — 프론트가 두 값으로 라벨링한다.
- 동일 결제 내 환불 충돌은 DB UNIQUE(payment_id, refund_sequence) + CHECK가 차단한다.
  본 서비스는 표시용 계산만 제공하며 입력 검증은 책임지지 않는다.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import structlog
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.payment import Payment
from api.src.models.qa_log import QALog
from api.src.models.refund import Refund
from api.src.models.subscription import Subscription
from api.src.schemas.admin.payment_refunds import RefundQuoteResponse

logger = structlog.get_logger(__name__)

_KST = ZoneInfo("Asia/Seoul")
# 전자상거래법 청약철회 7일 — billing_service._COOLING_OFF_DAYS_LIMIT와 동일.
# 두 곳에 값을 두는 것은 의도적: 본 서비스는 billing_service의 사적 헬퍼에 의존하지 않는다.
_COOLING_OFF_DAYS_LIMIT = 7


async def get_refund_quote(db: AsyncSession, payment_id: int) -> RefundQuoteResponse:
    """관리자 환불 입력 화면 진입 시 노출되는 참고 계산값 묶음을 반환한다.

    Raises:
        HTTPException 404 — payment_id에 해당하는 결제가 없을 때.
    """
    payment = (
        await db.execute(select(Payment).where(Payment.id == payment_id))
    ).scalar_one_or_none()
    if payment is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "PAYMENT_NOT_FOUND", "message": "결제를 찾을 수 없습니다."},
        )

    refunded_total, next_refund_sequence, existing_refunds_count = (
        await _aggregate_existing_refunds(db, payment_id)
    )

    refundable_balance = max(0, payment.amount_krw - refunded_total)
    full_refund_amount = refundable_balance

    prorated_total_days, prorated_days_remaining, prorated_amount = _compute_prorated(
        amount_krw=payment.amount_krw,
        refundable_balance=refundable_balance,
        period_start=payment.subscription_period_start,
        period_end=payment.subscription_period_end,
    )

    cooling_off_days_since_charge = _days_since_charge(payment.charged_at)
    cooling_off_qa_count = await _count_questions_in_period(
        db,
        user_id=payment.user_id,
        period_start=payment.subscription_period_start,
        period_end=payment.subscription_period_end,
        subscription_id=payment.subscription_id,
    )
    is_within_cooling_off = (
        payment.charged_at is not None
        and cooling_off_days_since_charge <= _COOLING_OFF_DAYS_LIMIT
        and cooling_off_qa_count == 0
    )

    logger.info(
        "admin.refund_quote.computed",
        payment_id=payment_id,
        refundable_balance=refundable_balance,
        next_refund_sequence=next_refund_sequence,
        is_within_cooling_off=is_within_cooling_off,
    )

    return RefundQuoteResponse(
        payment_id=payment.id,
        user_id=payment.user_id,
        payment_amount=payment.amount_krw,
        refunded_total=refunded_total,
        refundable_balance=refundable_balance,
        full_refund_amount=full_refund_amount,
        prorated_amount=prorated_amount,
        prorated_days_remaining=prorated_days_remaining,
        prorated_total_days=prorated_total_days,
        is_within_cooling_off=is_within_cooling_off,
        cooling_off_days_since_charge=cooling_off_days_since_charge,
        cooling_off_qa_count=cooling_off_qa_count,
        next_refund_sequence=next_refund_sequence,
        existing_refunds_count=existing_refunds_count,
        subscription_period_start=payment.subscription_period_start,
        subscription_period_end=payment.subscription_period_end,
    )


async def _aggregate_existing_refunds(
    db: AsyncSession, payment_id: int
) -> tuple[int, int, int]:
    """기존 환불 누적 합계 + 다음 sequence + row 수를 1쿼리로 조회한다.

    Returns:
        (refunded_total, next_refund_sequence, existing_refunds_count)
    """
    row = (
        await db.execute(
            select(
                func.coalesce(func.sum(Refund.cancel_amount), 0),
                func.coalesce(func.max(Refund.refund_sequence), 0),
                func.count(Refund.id),
            ).where(Refund.payment_id == payment_id)
        )
    ).one()
    return int(row[0]), int(row[1]) + 1, int(row[2])


def _compute_prorated(
    *,
    amount_krw: int,
    refundable_balance: int,
    period_start: datetime | None,
    period_end: datetime | None,
) -> tuple[int, int, int]:
    """일할 환불 권장값을 KST 캘린더 일 기준으로 계산한다.

    공식: amount_krw × (남은일수 ÷ 총일수), 원 단위 내림 (소비자 불리 방지).
    refundable_balance를 넘지 않도록 상한 적용 — 다회 부분환불 누적 후 일할이 잔액을
    초과하는 표시 오류 방지.

    Returns:
        (prorated_total_days, prorated_days_remaining, prorated_amount).
        스냅샷이 없거나 total_days < 1이면 (1, 0, 0) 폴백 — 스키마의 ge=1 제약 충족.
    """
    if period_start is None or period_end is None:
        return 1, 0, 0
    start_date = period_start.astimezone(_KST).date()
    end_date = period_end.astimezone(_KST).date()
    total = (end_date - start_date).days
    if total < 1:
        return 1, 0, 0
    today = datetime.now(_KST).date()
    remaining = max(0, min(total, (end_date - today).days))
    raw = (amount_krw * remaining) // total
    return total, remaining, min(raw, refundable_balance)


def _days_since_charge(charged_at: datetime | None) -> int:
    """결제 후 경과 일수 (음수 방지)."""
    if charged_at is None:
        return 0
    delta = datetime.now(UTC) - charged_at
    return max(0, delta.days)


async def _count_questions_in_period(
    db: AsyncSession,
    *,
    user_id: int,
    period_start: datetime | None,
    period_end: datetime | None,
    subscription_id: int | None,
) -> int:
    """해당 구독 기간 동안 사용자 질문 건수 (청약철회 0건 판정 근거).

    우선순위: payment 스냅샷 → subscription.started_at/current_period_end → 둘 다 없으면 0.
    스냅샷이 없는 레거시 결제(0019 마이그레이션 이전)에서도 구독이 살아 있으면 fallback이
    작동하도록 한다.
    """
    start, end = period_start, period_end
    if (start is None or end is None) and subscription_id is not None:
        sub = (
            await db.execute(
                select(Subscription).where(Subscription.id == subscription_id)
            )
        ).scalar_one_or_none()
        if sub is not None:
            start = start or sub.started_at
            end = end or sub.current_period_end
    if start is None or end is None:
        return 0
    result = await db.execute(
        select(func.count(QALog.id)).where(
            QALog.user_id == user_id,
            QALog.created_at >= start,
            QALog.created_at <= end,
        )
    )
    return int(result.scalar() or 0)


__all__ = ["get_refund_quote"]
