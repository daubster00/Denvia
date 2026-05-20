"""팝업 관리 Pydantic I/O 스키마 — Story 7.2 v2 재설계.

타입별 페이로드 일관성은 서비스 레이어에서 검증한다(인라인 422 코드 보존 목적).
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


PopupTargetDevice = Literal["pc", "mobile", "both"]
PopupType = Literal["image", "editor"]
PopupDisplayPosition = Literal[
    "center", "top", "bottom", "bottom_left", "bottom_right"
]


class PopupBase(BaseModel):
    """팝업 작성·편집 공통 입력."""

    title: str = Field(min_length=1, max_length=200)
    body_html: str | None = Field(default=None, max_length=20000)
    image_url: str | None = Field(default=None, max_length=500)
    link_url: str | None = Field(default=None, max_length=500)
    display_start: datetime
    display_end: datetime
    target_segment: Literal["all", "doctor", "hygienist", "student_other"] = "all"
    target_device: PopupTargetDevice = "both"
    popup_type: PopupType = "editor"
    display_position: PopupDisplayPosition = "center"
    sort_order: int = Field(default=0, ge=0, le=999)
    is_active: bool = True

    @field_validator("link_url", "image_url", "body_html", mode="before")
    @classmethod
    def _coerce_empty_to_none(cls, v):
        if v == "":
            return None
        return v


class PopupCreateRequest(PopupBase):
    pass


class PopupUpdateRequest(PopupBase):
    pass


class PopupTogglePatchRequest(BaseModel):
    """목록 행 활성 Switch — 다른 필드 거부."""

    model_config = ConfigDict(extra="forbid")
    is_active: bool


class PopupListItem(BaseModel):
    id: int
    title: str
    display_start: datetime
    display_end: datetime
    target_segment: str
    target_device: PopupTargetDevice
    popup_type: PopupType
    display_position: PopupDisplayPosition
    image_url: str | None
    sort_order: int
    is_active: bool
    link_url: str | None
    created_by_admin_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PopupListResponse(BaseModel):
    items: list[PopupListItem]
    page: int
    per_page: int
    total: int


class PopupDetailResponse(PopupListItem):
    """편집 다이얼로그 prefill용 — body_html 포함."""

    body_html: str | None


class PopupToggleResponse(BaseModel):
    id: int
    is_active: bool
    updated_at: datetime


class PopupImageUploadResponse(BaseModel):
    """POST /admin/popups/image-upload 응답."""

    image_url: str  # /static/popup-images/{filename}
    size_bytes: int
    mime_type: str
