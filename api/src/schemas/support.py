"""고객문의 Pydantic 스키마 — Story 4.5 + 0030 게시판화.

게시판형 1:1 문의로 재설계:
- 문의 작성 시 inquiry_type(6종) + 이미지 첨부(최대 5장) 가능
- 본인 문의 목록/상세 조회 + 관리자 답변(replies) 노출
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

InquiryType = Literal["billing", "account", "usage", "bug", "suggestion", "other"]
InquiryStatus = Literal["open", "in_progress", "resolved"]

MAX_ATTACHMENTS_PER_INQUIRY = 5


class InquiryAttachmentRef(BaseModel):
    """업로드된 첨부 1건. file_url은 /static/inquiry-images/<uuid>.<ext> 형식이어야 한다."""

    file_url: str = Field(min_length=1, max_length=500)
    file_name: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=1, max_length=64)
    size_bytes: int = Field(ge=1)


class InquirySubmitRequest(BaseModel):
    inquiry_type: InquiryType = "other"
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=5000)
    attachments: list[InquiryAttachmentRef] = Field(default_factory=list)

    @field_validator("attachments")
    @classmethod
    def _max_attachments(cls, v: list[InquiryAttachmentRef]) -> list[InquiryAttachmentRef]:
        if len(v) > MAX_ATTACHMENTS_PER_INQUIRY:
            raise ValueError(
                f"이미지는 최대 {MAX_ATTACHMENTS_PER_INQUIRY}장까지 첨부할 수 있습니다."
            )
        return v


class InquirySubmitResponse(BaseModel):
    inquiry_id: int


class InquiryImageUploadResponse(BaseModel):
    """multipart 업로드 응답 — 폼이 inquiry 제출 시 attachments 배열에 그대로 동봉."""

    file_url: str
    file_name: str
    mime_type: str
    size_bytes: int


class InquiryAttachmentView(BaseModel):
    """목록/상세에서 노출되는 첨부 정보."""

    id: int
    file_url: str
    file_name: str
    mime_type: str
    size_bytes: int


class InquiryReplyView(BaseModel):
    """관리자 답변 — 사용자용 노출. reply_html은 nh3 sanitize 결과."""

    reply_id: int
    reply_html_safe: str
    created_at: datetime


class InquiryListItem(BaseModel):
    """본인 1:1 문의 목록 1행."""

    id: int
    inquiry_type: InquiryType
    subject: str
    status: InquiryStatus
    created_at: datetime
    resolved_at: datetime | None = None
    has_attachments: bool = False
    reply_count: int = 0


class InquiryListResponse(BaseModel):
    items: list[InquiryListItem]
    page: int
    per_page: int
    total: int


class InquiryDetailResponse(BaseModel):
    """본인 1:1 문의 상세 — 첨부 + 답변 이력 포함."""

    id: int
    inquiry_type: InquiryType
    subject: str
    body: str = Field(description="원본은 html.escape() 적용된 plain text")
    status: InquiryStatus
    created_at: datetime
    resolved_at: datetime | None = None
    attachments: list[InquiryAttachmentView] = Field(default_factory=list)
    replies: list[InquiryReplyView] = Field(default_factory=list)


__all__ = [
    "InquiryType",
    "InquiryStatus",
    "MAX_ATTACHMENTS_PER_INQUIRY",
    "InquiryAttachmentRef",
    "InquirySubmitRequest",
    "InquirySubmitResponse",
    "InquiryImageUploadResponse",
    "InquiryAttachmentView",
    "InquiryReplyView",
    "InquiryListItem",
    "InquiryListResponse",
    "InquiryDetailResponse",
]
