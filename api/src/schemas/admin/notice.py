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


class NoticeListItem(BaseModel):
    id: int
    title: str
    target_segment: TargetSegment
    published_at: datetime | None
    created_by_admin_id: int
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


class InboxPreviewConfigResponse(BaseModel):
    max_count: int


class InboxPreviewConfigUpdateRequest(BaseModel):
    max_count: int = Field(ge=1, le=5)
