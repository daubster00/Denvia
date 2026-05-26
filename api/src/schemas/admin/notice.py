"""쪽지(공지) 관리 Pydantic 스키마 — Story 7.1.

작성·삭제 흐름만 노출(편집은 미지원). 작성 시 즉시 발행 + 매칭 user들의
inbox_messages에 fan-out하므로, 이후 본문 편집은 inbox_messages 스냅샷과
어긋나 사용자 혼동을 유발한다. 잘못 발행했다면 DELETE 후 재작성한다.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


TargetSegment = Literal["all", "doctor", "hygienist", "student_other"]


class NoticeCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body_html: str = Field(min_length=1, max_length=20000)
    target_segment: TargetSegment = "all"


ItemType = Literal["notice", "admin_dm"]


class NoticeListItem(BaseModel):
    """통합 쪽지 목록 항목. item_type='notice'면 전체/세그먼트 broadcast,
    'admin_dm'이면 관리자 → 특정 사용자 1:1 쪽지.

    - notice 행: id=notices.id, target_segment 채움, target_user_* 는 None
    - admin_dm 행: id=inbox_messages.id, target_segment=None,
      target_user_id/target_user_email 채움, delivered_user_count=1
    """

    item_type: ItemType
    id: int
    title: str
    target_segment: TargetSegment | None
    target_user_id: int | None = None
    target_user_email: str | None = None
    published_at: datetime | None
    created_by_admin_id: int | None
    created_at: datetime
    delivered_user_count: int

    model_config = ConfigDict(from_attributes=True)


class NoticeListResponse(BaseModel):
    items: list[NoticeListItem]
    page: int
    per_page: int
    total: int


class NoticeDetailResponse(BaseModel):
    id: int
    title: str
    body_html: str
    target_segment: TargetSegment
    published_at: datetime | None
    created_by_admin_id: int
    created_at: datetime
    delivered_user_count: int

    model_config = ConfigDict(from_attributes=True)


class AdminDMDetailResponse(BaseModel):
    """관리자 1:1 쪽지 단건 상세 — inbox_messages 1행 + 받는 사용자 이메일."""

    item_type: Literal["admin_dm"] = "admin_dm"
    id: int
    title: str
    body_html: str
    target_user_id: int
    target_user_email: str
    target_user_name: str | None
    is_read: bool
    created_by_admin_id: int | None
    created_at: datetime
    deleted_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class InboxPreviewConfigResponse(BaseModel):
    max_count: int


class InboxPreviewConfigUpdateRequest(BaseModel):
    max_count: int = Field(ge=1, le=5)


class NoticeRecipientItem(BaseModel):
    user_id: int
    email: str
    name: str | None
    segment: str | None
    is_read: bool
    delivered_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NoticeRecipientsResponse(BaseModel):
    items: list[NoticeRecipientItem]
    page: int
    per_page: int
    total: int
    read_count: int
    unread_count: int
    status: Literal["read", "unread"]
