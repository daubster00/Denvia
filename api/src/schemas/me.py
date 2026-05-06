"""Me 관련 Pydantic 스키마 — Story 2.3 / 4.3 / 4.4."""

from typing import Literal

from pydantic import BaseModel


class QuotaResponse(BaseModel):
    subscription_status: str
    daily_limit: int
    used_today: int
    remaining: int
    reset_at: str
    show_upgrade_prompt: bool
    show_subscribe_button: bool
    delay_seconds: float


class UsageSummaryResponse(BaseModel):
    """GET /api/v1/me/usage-summary 응답 — Story 4.3 마이페이지."""

    month_question_count: int
    daily_used: int
    daily_limit: int
    daily_remaining: int
    daily_reset_at: str  # ISO-8601 KST (+09:00)
    subscription_status: str  # free | pro | admin
    segment: str | None
    years_of_experience: int | None
    show_subscribe_button: bool


PaymentStatusLiteral = Literal[
    "pending", "success", "failed", "refunded", "refund_pending"
]


class PaymentHistoryItem(BaseModel):
    """GET /api/v1/me/payments items[i] — Story 4.4 (FR27 / F-402)."""

    payment_id: int
    charged_at: str | None  # ISO 8601 (NULL은 status='pending')
    subscription_period_start: str | None
    subscription_period_end: str | None
    buyer_email: str
    card_last4: str | None
    card_company: str | None
    amount_krw: int
    provider_order_id: str
    status: PaymentStatusLiteral


class PaymentHistoryResponse(BaseModel):
    """GET /api/v1/me/payments 응답 (AR27 flat 페이지네이션) — Story 4.4."""

    items: list[PaymentHistoryItem]
    page: int
    per_page: int
    total: int


# ── Story 1.7: 회원 탈퇴 ─────────────────────────────────────────────────────


class WithdrawOtpSendResponse(BaseModel):
    """POST /api/v1/me/withdraw/send-otp 응답 — 마스킹된 휴대폰만 노출."""

    masked_phone: str


class WithdrawOtpVerifyRequest(BaseModel):
    code: str


class WithdrawOtpVerifyResponse(BaseModel):
    phone_verification_token: str


class WithdrawRequest(BaseModel):
    """DELETE /api/v1/me 요청 — 자체 가입자는 password, 소셜 가입자는 token."""

    password: str | None = None
    phone_verification_token: str | None = None
