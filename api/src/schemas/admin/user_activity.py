"""Admin 사용자 활동 로그 — Pydantic 스키마 (Story 6.1 확장).

GET /api/v1/admin/users/{user_id}/qa-logs        — 사용자 질의 로그 페이지네이션
GET /api/v1/admin/users/{user_id}/inquiries      — 사용자 문의 페이지네이션
GET /api/v1/admin/users/{user_id}/anomaly-events — 사용자 이상 이벤트 페이지네이션

응답은 admin/users 와 동일한 flat 페이지네이션(items/page/per_page/total).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class UserQALogItem(BaseModel):
    qa_log_id: int
    question_excerpt: str = Field(description="question_text[:120]")
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: Decimal | None = None
    latency_ms: int | None = None
    status: str | None = None
    rule_matched: bool = False
    created_at: datetime


class UserQALogListResponse(BaseModel):
    items: list[UserQALogItem]
    page: int
    per_page: int
    total: int


class UserInquiryItem(BaseModel):
    id: int
    subject: str
    body_preview: str = Field(description="body[:120]")
    status: str
    created_at: datetime
    resolved_at: datetime | None = None


class UserInquiryListResponse(BaseModel):
    items: list[UserInquiryItem]
    page: int
    per_page: int
    total: int


class UserAnomalyEventItem(BaseModel):
    id: int
    type: str
    ip: str | None = None
    ua: str | None = None
    status: str
    created_at: datetime


class UserAnomalyEventListResponse(BaseModel):
    items: list[UserAnomalyEventItem]
    page: int
    per_page: int
    total: int


__all__ = [
    "UserQALogItem",
    "UserQALogListResponse",
    "UserInquiryItem",
    "UserInquiryListResponse",
    "UserAnomalyEventItem",
    "UserAnomalyEventListResponse",
]
