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


class InboxPreviewItem(BaseModel):
    """쪽지함 미리보기 카드 1건 — Story 7.1.

    body_html은 의도적으로 제외 (드롭다운은 제목만 노출, 본문은 /inbox 상세에서).
    """

    message_id: int
    type: Literal["notice", "system", "billing"]
    title: str
    is_read: bool
    created_at: str  # ISO 8601


class InboxPreviewResponse(BaseModel):
    """GET /api/v1/me/inbox/preview 응답.

    `max_count`는 관리자가 설정한 동시 노출 최대 개수(items.length <= max_count).
    """

    items: list[InboxPreviewItem]
    max_count: int
