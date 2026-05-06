"""Story 6.5 — Admin 이상 이벤트 응답 schema."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class AnomalyEventItem(BaseModel):
    """list/단건 응답 공통 row.

    target_user_email_masked는 list 응답에서만 채워짐 (상세 권한은 6.1 진입점 경유).
    """

    id: int
    type: Literal[
        "login_brute_force",
        "rapid_questions",
        "concurrent_ip_login",
        "repeated_question",
        "recovery_abuse",
    ]
    target_user_id: int | None = None
    target_user_email_masked: str | None = Field(
        default=None,
        description="target_user_id가 있는 경우만 마스킹된 이메일 (예: k**@example.com).",
    )
    ip: str | None = None
    ua: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    status: Literal["new", "reviewed", "actioned"]
    reviewed_by_admin_id: int | None = None
    reviewed_at: datetime | None = None
    created_at: datetime


class AnomalyListResponse(BaseModel):
    """GET /api/v1/admin/anomaly — flat 페이지네이션 (AR27)."""

    items: list[AnomalyEventItem]
    page: int
    per_page: int
    total: int


class AnomalyMarkReviewedRequest(BaseModel):
    """PATCH /api/v1/admin/anomaly/{id} body.

    `status` 필드는 'reviewed' 단일 값만 허용 — 'actioned' 직접 전이는 차단 endpoint 경유 only.
    실제 값 검증은 라우터에서 수행해 spec AC-7의 `ANOMALY_STATUS_INVALID` 코드 보장.
    """

    status: str


class AnomalyMarkReviewedResponse(AnomalyEventItem):
    """PATCH /api/v1/admin/anomaly/{id} 응답 — 단건 row."""


__all__ = [
    "AnomalyEventItem",
    "AnomalyListResponse",
    "AnomalyMarkReviewedRequest",
    "AnomalyMarkReviewedResponse",
]
