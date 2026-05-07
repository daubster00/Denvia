"""Admin 수동 환불 검토 — Pydantic 스키마 (Story 9.3 A-503).

GET   /api/v1/admin/refunds                       manual_refund_queue 목록 (status/from/to/q + 페이지네이션)
POST  /api/v1/admin/refunds/{queue_id}/approve    PG refund 호출 + payment.status='refunded' + 알림톡 + 쪽지함
POST  /api/v1/admin/refunds/{queue_id}/deny       payment.status 원복 + 알림톡(거부) + 쪽지함

설계 원칙:
- 응답은 admin/users/finance 와 동일한 flat 페이지네이션(items/page/per_page/total).
- approve/deny 모두 reviewer_note 필수 (감사 추적).
- 알림톡 발송은 fire-and-forget — 응답 성공 여부에 영향 없음 (3.6 _execute_auto_refund 패턴 답습).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

RefundQueueStatus = Literal["pending", "approved", "denied"]
RefundReasonCode = Literal[
    "period_exceeded",
    "qa_count_exceeded",
    "both",
    "no_subscription",
]


class RefundQueueItem(BaseModel):
    """환불 큐 1행."""

    queue_id: int
    payment_id: int
    user_id: int
    user_email_masked: str
    amount_krw: int
    card_last4: str | None = None
    card_company: str | None = None
    days_since_charge: int
    qa_count_during_period: int
    reason_code: RefundReasonCode | None = None
    reason_text: str | None = Field(
        default=None,
        description="manual_refund_queue.reason — 사용자 입력 사유 (null 가능)",
    )
    requested_at: datetime
    status: RefundQueueStatus
    reviewer_user_email_masked: str | None = None
    reviewer_note: str | None = None
    reviewed_at: datetime | None = None


class RefundQueueListResponse(BaseModel):
    """GET /api/v1/admin/refunds — flat 페이지네이션."""

    items: list[RefundQueueItem]
    page: int
    per_page: int
    total: int


class RefundActionRequest(BaseModel):
    """POST /api/v1/admin/refunds/{queue_id}/approve|deny — 검토자 메모 필수."""

    note: str = Field(
        min_length=1,
        max_length=1000,
        description="검토자 메모. 거부 시 사용자에게 일부(80자)가 알림톡으로 노출됨.",
    )


class RefundActionResponse(BaseModel):
    """approve/deny 응답."""

    queue_id: int
    payment_id: int
    status: RefundQueueStatus
    amount_krw: int
    refunded_at: datetime | None = Field(
        default=None,
        description="approve 시점 refund 완료 시각. deny 시 None.",
    )


__all__ = [
    "RefundQueueStatus",
    "RefundReasonCode",
    "RefundQueueItem",
    "RefundQueueListResponse",
    "RefundActionRequest",
    "RefundActionResponse",
]
