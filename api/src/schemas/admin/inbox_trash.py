"""CS · 휴지통(쪽지) 관리 Pydantic 스키마.

사용자가 본인 쪽지함에서 삭제한 inbox_messages 행(deleted_at IS NOT NULL)을
관리자가 확인·복구·영구삭제할 수 있도록 한다. 30일 후 retention 배치
(``retention_tasks.purge_old_inbox_messages``)가 영구 삭제하므로,
``permanent_purge_at = deleted_at + 30 days`` 로 계산해 응답에 동봉한다.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


InboxMessageType = Literal["notice", "system", "billing", "admin_dm"]


class TrashListItem(BaseModel):
    """휴지통 목록 항목 — 사용자 정보와 자동 영구삭제 예정일 동봉."""

    message_id: int
    type: InboxMessageType
    title: str
    user_id: int
    user_email: str
    user_name: str | None
    created_at: datetime
    deleted_at: datetime
    permanent_purge_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TrashListResponse(BaseModel):
    items: list[TrashListItem]
    page: int
    per_page: int
    total: int


class TrashDetailResponse(BaseModel):
    """휴지통 단건 상세 — sanitize 적용된 body_html_safe 포함."""

    message_id: int
    type: InboxMessageType
    title: str
    body_html_safe: str
    user_id: int
    user_email: str
    user_name: str | None
    is_read: bool
    created_at: datetime
    deleted_at: datetime
    permanent_purge_at: datetime
    created_by_admin_id: int | None

    model_config = ConfigDict(from_attributes=True)
