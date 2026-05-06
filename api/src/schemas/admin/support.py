"""Admin 고객문의 관리 — Pydantic 스키마.

GET  /api/v1/admin/support/inquiries           목록 (status 필터 + 페이지네이션)
GET  /api/v1/admin/support/inquiries/{id}      상세
PATCH /api/v1/admin/support/inquiries/{id}     상태 변경 / 답변 등록

설계 원칙:
- 목록 응답은 admin/users 와 동일한 flat 페이지네이션(items/page/per_page/total).
- 답변 등록 시 사용자 inbox_messages.type='system' 행 1건이 자동 INSERT 된다
  (이메일 0건 정책 — 알림은 inbox/알림톡 only).
- audit_logs INSERT 는 PATCH 응답 직후 미들웨어가 자동 수행.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

InquiryStatus = Literal["open", "in_progress", "resolved"]


class InquiryListItem(BaseModel):
    """목록 1행 — 본문(body)은 제외하여 응답 크기를 줄인다."""

    id: int
    user_id: int
    user_email: str
    subject: str
    status: InquiryStatus
    created_at: datetime
    resolved_at: datetime | None = None


class InquiryListResponse(BaseModel):
    """GET /api/v1/admin/support/inquiries — flat 페이지네이션."""

    items: list[InquiryListItem]
    page: int
    per_page: int
    total: int


class InquiryDetailResponse(BaseModel):
    """GET /api/v1/admin/support/inquiries/{id} — 본문 + 사용자 연락처 포함."""

    id: int
    user_id: int
    user_email: str
    user_phone: str | None = None
    subject: str
    body: str = Field(description="원본은 html.escape() 적용된 plain text")
    status: InquiryStatus
    created_at: datetime
    resolved_at: datetime | None = None


class InquiryUpdateRequest(BaseModel):
    """PATCH /api/v1/admin/support/inquiries/{id}.

    - status: 단순 상태 변경(예: open → in_progress).
    - reply_message: 본문이 주어지면 사용자 inbox 에 답변 메시지를 INSERT 하고
      자동으로 status='resolved' + resolved_at=now 로 마감한다.
    """

    status: InquiryStatus | None = None
    reply_message: str | None = Field(
        default=None,
        min_length=1,
        max_length=5000,
        description="답변 본문(plain text). 지정 시 사용자 inbox 로 알림이 발송되고 status='resolved' 로 자동 마감.",
    )

    @model_validator(mode="after")
    def _check_no_op(self) -> "InquiryUpdateRequest":
        if self.status is None and self.reply_message is None:
            raise ValueError("status 또는 reply_message 중 하나는 반드시 지정해야 합니다.")
        return self


__all__ = [
    "InquiryStatus",
    "InquiryListItem",
    "InquiryListResponse",
    "InquiryDetailResponse",
    "InquiryUpdateRequest",
]
