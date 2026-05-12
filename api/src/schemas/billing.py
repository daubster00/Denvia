"""빌링 관련 Pydantic 스키마 — Story 3.1/3.2/3.5."""

import re
from typing import Literal

from pydantic import BaseModel, field_validator


class PlanResponse(BaseModel):
    """단일 구독 플랜 응답 스키마."""

    tier: str
    name: str
    price_krw: int
    period: str | None
    features: list[str]
    cta_label: str
    is_recommended: bool


class BillingPlansResponse(BaseModel):
    """GET /api/v1/billing/plans 응답 스키마."""

    plans: list[PlanResponse]


# ── Story 3.2 ────────────────────────────────────────────────────────────────

_CUSTOMER_KEY_RE = re.compile(r"^[A-Za-z0-9\-_=.@]{2,300}$")
# 추측 가능한 패턴 — 토스 정책상 user ID/email/phone을 customerKey로 쓰는 것은 금지
_FORBIDDEN_PREFIX_RE = re.compile(r"^denvia-user-\d+", re.IGNORECASE)


class IssueBillingKeyRequest(BaseModel):
    """POST /api/v1/billing/billing-key 요청."""

    pg_token: str           # 토스 authKey
    customer_key: str       # successUrl로 돌아온 customerKey (UUID/crypto random 기반)

    @field_validator("customer_key")
    @classmethod
    def validate_customer_key(cls, v: str) -> str:
        if not _CUSTOMER_KEY_RE.match(v):
            raise ValueError(
                "customer_key는 2~300자의 영문/숫자/- _ = . @ 만 허용합니다"
            )
        if _FORBIDDEN_PREFIX_RE.match(v):
            raise ValueError(
                "customer_key에 사용자 ID를 직접 노출하는 패턴은 허용하지 않습니다"
            )
        return v


class IssueBillingKeyResponse(BaseModel):
    """POST /api/v1/billing/billing-key 응답."""

    billing_key_id: int
    card_last4: str | None
    card_company: str | None
    masked_number: str | None   # "**** **** **** 1234", card_last4 없으면 None


class StartSubscriptionResponse(BaseModel):
    """POST /api/v1/billing/subscriptions 응답."""

    subscription_id: int
    started_at: str             # ISO 8601
    current_period_end: str     # ISO 8601
    amount_krw: int


# ── Story 3.5 ────────────────────────────────────────────────────────────────


class CancelSubscriptionRequest(BaseModel):
    """POST /api/v1/billing/subscriptions/cancel 요청."""

    reason: str

    @field_validator("reason")
    @classmethod
    def _strip_and_validate(cls, v: str) -> str:
        v = (v or "").strip()
        if len(v) == 0:
            raise ValueError("해지 사유를 입력해주세요")
        if len(v) > 500:
            raise ValueError("해지 사유는 500자 이내로 입력해주세요")
        return v


class CancelSubscriptionResponse(BaseModel):
    """POST /api/v1/billing/subscriptions/cancel 응답."""

    status: Literal["cancel_pending"]
    effective_at: str  # ISO 8601


class ResumeSubscriptionResponse(BaseModel):
    """POST /api/v1/billing/subscriptions/resume 응답."""

    status: Literal["active"]
    next_charge_at: str | None  # ISO 8601


class CurrentSubscriptionResponse(BaseModel):
    """GET /api/v1/billing/subscriptions/current 응답."""

    status: Literal["active", "cancel_pending", "none"]
    started_at: str | None
    current_period_end: str | None
    next_charge_at: str | None
    canceled_at: str | None
    cancel_reason: str | None


# ── Story 3.6 v1.1 — 청약철회 (Cooling-off Refund) ─────────────────────────────
# v1.1 정책 변경(2026-05-12, ADR-0001 편차 #5)으로 자가 환불 요청 폼·수동 검토 큐 폐기.
# 청약철회 = 7일 이내 + 질문 0건 충족 시 즉시 해지 + 전액 환불.


RefundEligibilityReasonCode = Literal[
    "ok",
    "period_exceeded",
    "qa_count_exceeded",
    "both",
    "no_active_payment",
]


class RefundEligibilityResponse(BaseModel):
    """GET /api/v1/billing/subscriptions/me/refund-eligibility 응답.

    마이페이지 구독 취소 다이얼로그가 "즉시 해지 + 전액 환불" 옵션 노출 여부를
    결정하기 위한 read-only 조회 결과.
    """

    eligible: bool
    payment_id: int | None = None
    amount_krw: int | None = None
    charged_at: str | None = None  # ISO 8601
    days_since_charge: int | None = None
    qa_count_during_period: int | None = None
    reason_code: RefundEligibilityReasonCode


class CancelWithRefundRequest(BaseModel):
    """POST /api/v1/billing/subscriptions/me/cancel-with-refund 요청.

    body는 확인 토큰만. 사유는 받지 않으며(청약철회는 사유 불요), confirmation=False는
    422로 거부한다.
    """

    confirmation: bool

    @field_validator("confirmation")
    @classmethod
    def _require_confirmation(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("청약철회를 진행하려면 confirmation=true 가 필요합니다")
        return v


class CancelWithRefundResponse(BaseModel):
    """POST /api/v1/billing/subscriptions/me/cancel-with-refund 응답."""

    status: Literal["refunded"]
    refund_kind: Literal["cooling_off"]
    amount_krw: int
    refunded_at: str  # ISO 8601
    subscription_status: Literal["canceled"]
