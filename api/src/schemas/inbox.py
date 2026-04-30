"""받은 쪽지함·팝업 Pydantic 스키마 — Story 4.5 (F-503)."""

from typing import Literal

from pydantic import BaseModel


class InboxItem(BaseModel):
    """GET /api/v1/me/inbox items[i]."""

    message_id: int
    type: Literal["notice", "system", "billing"]
    title: str
    body_html_safe: str  # nh3 sanitize 적용 후 응답
    is_read: bool
    created_at: str  # ISO 8601 (UTC)
    notice_id: int | None
    popup_id: int | None


class InboxListResponse(BaseModel):
    """GET /api/v1/me/inbox 응답 (AR27 flat 페이지네이션)."""

    items: list[InboxItem]
    page: int
    per_page: int
    total: int
    unread_count: int


class UnreadCountResponse(BaseModel):
    """GET /api/v1/me/inbox/unread-count 응답."""

    unread_count: int


class ActivePopupResponse(BaseModel):
    """GET /api/v1/me/popups/active 200 응답 (204면 빈 body)."""

    popup_id: int
    title: str
    body_html_safe: str
    link_url: str | None
    display_end: str  # ISO 8601
