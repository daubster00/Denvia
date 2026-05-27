"""이상탐지 "주의 계정" (watch list) 응답/요청 schema."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class WatchedAnomalyItem(BaseModel):
    """주의 계정에 걸린 개별 이상탐지 항목 — type별 최신 1건."""

    anomaly_id: int
    type: str
    created_at: datetime


class WatchedAccountItem(BaseModel):
    """GET /api/v1/admin/anomaly/watched — 주의 계정 리스트 row."""

    user_id: int
    email_masked: str | None = None
    # 해당 사용자에게 걸린 모든 이상탐지(type 별 최신 1건). 최근 발생 순.
    anomalies: list[WatchedAnomalyItem] = Field(default_factory=list)
    # 현재 사용자 상태 — 리스트 "현재 상태" 컬럼에 노출.
    user_subscription_status: Literal["free", "pro", "blocked"] | None = None
    user_blocked_now: bool = False
    user_auto_throttled_now: bool = False
    flagged_by_admin_id: int | None = None
    flagged_at: datetime


class WatchedAccountListResponse(BaseModel):
    items: list[WatchedAccountItem]
    page: int
    per_page: int
    total: int


class WatchToggleResponse(BaseModel):
    """POST /admin/anomaly/{id}/watch · DELETE /admin/anomaly/users/{user_id}/watch."""

    user_id: int
    is_watched: bool


__all__ = [
    "WatchedAnomalyItem",
    "WatchedAccountItem",
    "WatchedAccountListResponse",
    "WatchToggleResponse",
]
