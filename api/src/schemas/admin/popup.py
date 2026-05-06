"""팝업 관리 Pydantic I/O 스키마 — Story 7.2.

요청·응답 모델은 라우터(`routers/admin/content.py`)와 서비스(`services/popup_service.py`)
양쪽에서 공유한다. AC-13 검증 표를 기준으로 zod ↔ Pydantic 1:1 일치.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PopupBase(BaseModel):
    """팝업 작성·편집 공통 입력.

    NOTE: display_end > display_start 검증은 서비스 레이어에서 수행 — Pydantic
    `model_validator`로 raise하면 FastAPI 표준 422 본문에 묻혀 명시 code
    (POPUP_DISPLAY_RANGE_INVALID)를 프론트가 인라인 매핑하기 어렵다.
    """

    title: str = Field(min_length=1, max_length=200)
    body_html: str = Field(min_length=1, max_length=20000)
    link_url: str | None = Field(default=None, max_length=500)
    display_start: datetime
    display_end: datetime
    target_segment: Literal["all", "doctor", "hygienist", "student_other"] = "all"
    is_active: bool = True

    @field_validator("link_url", mode="before")
    @classmethod
    def _coerce_empty_link_url(cls, v):
        # 빈 문자열은 None과 동치로 취급 — 서비스 검증을 단일 경로로 만든다.
        if v == "":
            return None
        return v


class PopupCreateRequest(PopupBase):
    pass


class PopupUpdateRequest(PopupBase):
    pass


class PopupTogglePatchRequest(BaseModel):
    """목록 행에서 활성 Switch 클릭 시 빠른 경로 — 다른 필드 거부."""

    model_config = ConfigDict(extra="forbid")
    is_active: bool


class PopupListItem(BaseModel):
    id: int
    title: str
    display_start: datetime
    display_end: datetime
    target_segment: str
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
    """편집 다이얼로그 prefill용 — body_html은 DB raw 그대로 반환(이미 sanitize됨)."""

    body_html: str


class PopupToggleResponse(BaseModel):
    id: int
    is_active: bool
    updated_at: datetime
