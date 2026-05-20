"""관리자 수정요청 게시판 Pydantic 스키마.

엔드포인트(api/src/routers/admin/board.py)와 1:1 매핑.

권한 요약:
- 글 작성/댓글 작성/이미지 업로드: 모든 admin 통과
- 글·댓글 수정/삭제: 작성자 본인 OR btmdesign 마스터 계정
- 상태(status) 변경: btmdesign 마스터 계정 전용
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# 4가지 상태 — 0040_admin_board.py board_post_status_enum 과 동기.
BoardPostStatus = Literal["review", "in_progress", "rejected", "on_hold"]

# 카테고리 8종 — 본 프로젝트 영역 기준. 추후 추가는 ALLOWED_CATEGORIES 확장 + UI 라벨만.
BoardCategory = Literal[
    "auth",
    "mypage",
    "chatbot",
    "billing",
    "admin",
    "messaging",
    "design",
    "etc",
]


# ── 요청 ──────────────────────────────────────────────────────────────────────
class BoardPostCreateRequest(BaseModel):
    category: BoardCategory
    title: str = Field(min_length=1, max_length=200)
    content_html: str = Field(min_length=1, max_length=50000)


class BoardPostUpdateRequest(BaseModel):
    """본인(또는 btmdesign) 글 수정 — title/content/category 동시 갱신."""

    category: BoardCategory
    title: str = Field(min_length=1, max_length=200)
    content_html: str = Field(min_length=1, max_length=50000)


class BoardPostStatusUpdateRequest(BaseModel):
    """상태만 변경 — btmdesign 마스터 전용."""

    status: BoardPostStatus


class BoardCommentCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class BoardCommentUpdateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


# ── 응답 ──────────────────────────────────────────────────────────────────────
class BoardImageUploadResponse(BaseModel):
    """에디터 이미지 삽입 응답 — 본문에 그대로 박을 file_url."""

    file_url: str
    file_name: str
    mime_type: str
    size_bytes: int


class BoardCommentItem(BaseModel):
    id: int
    post_id: int
    author_id: int
    author_email: str
    author_display: str  # 이메일 prefix(@ 앞)
    content: str
    created_at: datetime
    updated_at: datetime
    can_edit: bool  # 현재 로그인 사용자가 이 댓글을 수정/삭제할 수 있는지

    model_config = ConfigDict(from_attributes=True)


class BoardPostListItem(BaseModel):
    id: int
    category: BoardCategory
    status: BoardPostStatus
    title: str
    author_id: int
    author_email: str
    author_display: str
    comment_count: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BoardPostListResponse(BaseModel):
    items: list[BoardPostListItem]
    page: int
    per_page: int
    total: int


class BoardPostDetailResponse(BaseModel):
    id: int
    category: BoardCategory
    status: BoardPostStatus
    title: str
    content_html: str
    author_id: int
    author_email: str
    author_display: str
    comments: list[BoardCommentItem]
    can_edit: bool          # 본인 글 OR btmdesign — 글 수정/삭제 권한
    can_change_status: bool  # btmdesign 전용 — 상태 변경 권한
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BoardMetaResponse(BaseModel):
    """카테고리·상태 라벨 메타 — 프론트 select/표시용."""

    categories: list[dict[str, str]]  # [{"key": "auth", "label": "로그인/회원가입"}, ...]
    statuses: list[dict[str, str]]    # [{"key": "review", "label": "요청사항검토"}, ...]
