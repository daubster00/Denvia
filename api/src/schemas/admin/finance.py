"""Story 9.1 — 관리자 결제 기록 타임라인 (A-501) Pydantic 스키마."""

from typing import Literal

from pydantic import BaseModel

PaymentEventType = Literal[
    "charge_requested",
    "charge_success",
    "charge_failed",
    "retry_scheduled",
    "refund_requested",
    "refund_success",
    "refund_denied",
]
PaymentStatus = Literal["pending", "success", "failed", "refunded", "refund_pending"]


class PaymentEventItem(BaseModel):
    event_id: int
    payment_id: int
    event_type: PaymentEventType
    charged_at: str | None  # ISO 8601 (event.created_at — KST aware ISO)
    amount_krw: int
    user_id: int
    user_email_masked: str
    card_last4: str | None
    card_company: str | None
    provider_order_id: str
    provider_error_code: str | None
    provider_error_message: str | None
    status: PaymentStatus


class ErrorCodeSummary(BaseModel):
    event_count: int
    affected_user_count: int


class PaymentEventListResponse(BaseModel):
    items: list[PaymentEventItem]
    page: int
    per_page: int
    total: int
    error_code_summary: ErrorCodeSummary | None  # AC-5: provider_error_code 미선택 시 None


class PaymentEventDetailResponse(PaymentEventItem):
    raw_response_json: dict | None
    refund_reason: str | None = None
