"""Admin 고객문의 관리 — Pydantic 스키마.

GET   /api/v1/admin/support/inquiries           목록 (status_in/q/from/to + 페이지네이션)
GET   /api/v1/admin/support/inquiries/{id}      상세 (recent_qa + replies 포함)
PATCH /api/v1/admin/support/inquiries/{id}      상태 변경 (force 분기) / plain text reply 호환 (4.5)
POST  /api/v1/admin/support/inquiries/{id}/reply  Tiptap reply_html 답변 (Story 9.3 신규)
GET   /api/v1/admin/support/counts              열린 문의 + pending 환불 카운트

설계 원칙 (Story 9.3 갱신):
- 목록 응답은 admin/users 와 동일한 flat 페이지네이션(items/page/per_page/total).
- POST /reply 경로는 inquiry_replies 테이블에 row INSERT, sanitize 후 inbox_messages 동기 INSERT,
  알림톡(support.reply_received) fire-and-forget.
- audit_logs INSERT 는 PATCH/POST 응답 직후 미들웨어가 자동 수행.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

InquiryStatus = Literal["open", "in_progress", "resolved"]
InquiryType = Literal["billing", "account", "usage", "bug", "suggestion", "other"]
UserSegment = Literal["doctor", "hygienist", "student_other"]
UserSubscriptionStatus = Literal["free", "pro", "blocked"]


class InquiryAttachmentItem(BaseModel):
    """관리자 상세에서 노출되는 첨부 이미지."""

    id: int
    file_url: str
    file_name: str
    mime_type: str
    size_bytes: int


class InquiryListItem(BaseModel):
    """목록 1행 — 본문(body)은 제외하고 body_preview만 노출 (Story 9.3 확장)."""

    id: int
    user_id: int
    user_email: str
    subject: str
    body_preview: str = Field(default="", description="body[:80] 한글 안전 truncation")
    inquiry_type: InquiryType = "other"
    segment: UserSegment | None = None
    status: InquiryStatus
    created_at: datetime
    resolved_at: datetime | None = None


class InquiryListResponse(BaseModel):
    """GET /api/v1/admin/support/inquiries — flat 페이지네이션."""

    items: list[InquiryListItem]
    page: int
    per_page: int
    total: int


class RecentQAExcerpt(BaseModel):
    """문의 답변 시 컨텍스트 참조용 — 사용자의 직전 질의 3건 발췌."""

    qa_log_id: int
    question_excerpt: str = Field(description="question_text[:60]")
    created_at: datetime


class InquiryReplyItem(BaseModel):
    """답변 이력 1행 — Tiptap RichTextEditor가 등록한 sanitize된 HTML."""

    reply_id: int
    admin_id: int
    admin_email_masked: str
    reply_html_safe: str = Field(description="nh3 sanitize 결과 (응답 직전 이중 sanitize)")
    created_at: datetime


class InquiryDetailResponse(BaseModel):
    """GET /api/v1/admin/support/inquiries/{id} — 사용자 메타 + recent_qa + replies."""

    id: int
    user_id: int
    user_email: str
    user_phone: str | None = None
    subject: str
    body: str = Field(description="원본은 html.escape() 적용된 plain text")
    inquiry_type: InquiryType = "other"
    status: InquiryStatus
    created_at: datetime
    resolved_at: datetime | None = None
    # Story 9.3 확장
    user_segment: UserSegment | None = None
    user_subscription_status: UserSubscriptionStatus
    user_created_at: datetime
    recent_qa: list[RecentQAExcerpt] = Field(default_factory=list)
    replies: list[InquiryReplyItem] = Field(default_factory=list)
    # 0030 확장 — 사용자가 작성 시 첨부한 이미지
    attachments: list[InquiryAttachmentItem] = Field(default_factory=list)


class InquiryUpdateRequest(BaseModel):
    """PATCH /api/v1/admin/support/inquiries/{id}.

    Story 4.5 호환:
    - status 단순 상태 변경 (Story 9.3에서 force 분기 추가)
    - reply_message plain text — 사용자 inbox 에 답변 INSERT + status='resolved' 자동 마감

    Story 9.3 신규:
    - force=True 시 역행 전이(resolved → open 등) 허용. False 시 409.
    """

    status: InquiryStatus | None = None
    reply_message: str | None = Field(
        default=None,
        min_length=1,
        max_length=5000,
        description="답변 본문(plain text). 지정 시 사용자 inbox 로 알림이 발송되고 status='resolved' 로 자동 마감.",
    )
    force: bool = Field(
        default=False,
        description="True면 역행 상태 전이(예: resolved → open) 허용. False면 409.",
    )

    @model_validator(mode="after")
    def _check_no_op(self) -> "InquiryUpdateRequest":
        if self.status is None and self.reply_message is None:
            raise ValueError("status 또는 reply_message 중 하나는 반드시 지정해야 합니다.")
        return self


class InquiryReplyRequest(BaseModel):
    """POST /api/v1/admin/support/inquiries/{id}/reply — Tiptap RichTextEditor 답변."""

    reply_html: str = Field(min_length=1, max_length=20_000)
    new_status: Literal["in_progress", "resolved"] | None = Field(
        default=None,
        description="None이면 기본 'resolved'로 자동 마감",
    )


class InquiryReplyResponse(BaseModel):
    """POST /api/v1/admin/support/inquiries/{id}/reply 응답."""

    inquiry: InquiryDetailResponse


class SupportCountsResponse(BaseModel):
    """GET /api/v1/admin/support/counts — 탭 카운트 1회 fetch."""

    open_inquiries: int
    pending_refunds: int


__all__ = [
    "InquiryStatus",
    "InquiryType",
    "UserSegment",
    "UserSubscriptionStatus",
    "InquiryAttachmentItem",
    "InquiryListItem",
    "InquiryListResponse",
    "RecentQAExcerpt",
    "InquiryReplyItem",
    "InquiryDetailResponse",
    "InquiryUpdateRequest",
    "InquiryReplyRequest",
    "InquiryReplyResponse",
    "SupportCountsResponse",
]
