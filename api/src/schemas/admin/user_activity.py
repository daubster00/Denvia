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
    question_excerpt: str = Field(description="질문 본문 전체 (잘림 없음)")
    answer_excerpt: str = Field(default="", description="답변 본문 전체 (잘림 없음)")
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


class RetrievedDocItem(BaseModel):
    """qa_logs.retrieved_docs JSONB 항목 (top-k 단일 문서)."""

    page_content: str = Field(default="", description="문서 본문 (관리자 감사용, 최대 2000자)")
    metadata: dict = Field(default_factory=dict, description="문서 메타 (source path 등)")


class UserQALogDetail(BaseModel):
    """관리자 감사용 단건 상세 — '상세보기' 응답.

    SSE 사용자 응답에는 절대 노출되지 않는 normalized_query, retrieved_docs를
    포함한다 (ADR-0002 보강 단서).
    """

    qa_log_id: int
    question_text: str = Field(description="원본 질의 (사용자 입력 그대로)")
    normalized_query: str | None = Field(
        default=None,
        description="동의어 치환(apply_scaling_rules + normalize_query) 적용 후 쿼리",
    )
    retrieved_docs: list[RetrievedDocItem] = Field(
        default_factory=list,
        description="top-k 검색 문서들 (룰 경로면 빈 리스트, 본 마이그레이션 이전 행은 NULL)",
    )
    answer_text: str | None = Field(default=None, description="최종 답변 본문")
    rule_matched: bool = False
    status: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: Decimal | None = None
    latency_ms: int | None = None
    created_at: datetime


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
    "UserQALogDetail",
    "RetrievedDocItem",
    "UserInquiryItem",
    "UserInquiryListResponse",
    "UserAnomalyEventItem",
    "UserAnomalyEventListResponse",
]
