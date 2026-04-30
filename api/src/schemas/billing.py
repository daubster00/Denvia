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


# ── Story 3.6 ────────────────────────────────────────────────────────────────


class RefundRequest(BaseModel):
    """POST /api/v1/billing/payments/{payment_id}/refund 요청."""

    reason: str | None = None

    @field_validator("reason")
    @classmethod
    def _strip_and_validate(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if len(v) == 0:
            return None
        if len(v) > 500:
            raise ValueError("환불 사유는 500자 이내로 입력해주세요")
        return v


class RefundResponse(BaseModel):
    """POST /api/v1/billing/payments/{payment_id}/refund 응답.

    status='refunded' 시 amount_krw + refunded_at 채움.
    status='queued_for_review' 시 queue_id + reason_code 채움.
    """

    status: Literal["refunded", "queued_for_review"]
    amount_krw: int | None = None
    refunded_at: str | None = None
    queue_id: int | None = None
    reason_code: Literal["qa_count_exceeded", "period_exceeded", "both", "no_subscription"] | None = None
