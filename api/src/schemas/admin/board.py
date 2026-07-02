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


# 7가지 상태 — 0040 + 0041 + 0064 board_post_status_enum 동기.
# confirm_requested(컨펌요청)/confirmed(컨펌)은 추가개발 컨펌 플로우 전용.
BoardPostStatus = Literal[
    "review",
    "in_progress",
    "completed",
    "rejected",
    "on_hold",
    "confirm_requested",
    "confirmed",
]

# 카테고리 4종 — error(에러) / feature(추가개발) / inquiry(문의) / etc(기타).
# 신규 글 작성/수정 요청에만 강제. 과거 글(auth/mypage 등 레거시 키)은
# DB(String) 에 그대로 남아 응답에서는 str 로 관대하게 받는다(라벨 fallback).
BoardCategory = Literal["error", "feature", "inquiry", "etc"]

# 첨부 정책 — 문서/압축/이미지, 파일당 20MB, 글당 최대 10개.
MAX_ATTACHMENTS_PER_POST = 10


# ── 요청 ──────────────────────────────────────────────────────────────────────
class BoardAttachmentRef(BaseModel):
    """업로드된 첨부 1건. file_url 은 /static/admin-board-attachments/<uuid>.<ext> 형식."""

    file_url: str = Field(min_length=1, max_length=500)
    file_name: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=1, max_length=128)
    size_bytes: int = Field(ge=1)


class BoardPostCreateRequest(BaseModel):
    category: BoardCategory
    title: str = Field(min_length=1, max_length=200)
    content_html: str = Field(min_length=1, max_length=50000)
    attachments: list[BoardAttachmentRef] = Field(default_factory=list)


class BoardPostUpdateRequest(BaseModel):
    """본인(또는 마스터) 글 수정 — title/content/category/첨부 동시 갱신."""

    category: BoardCategory
    title: str = Field(min_length=1, max_length=200)
    content_html: str = Field(min_length=1, max_length=50000)
    attachments: list[BoardAttachmentRef] = Field(default_factory=list)


class BoardPostStatusUpdateRequest(BaseModel):
    """상태만 변경 — 마스터 전용."""

    status: BoardPostStatus


class BoardDevCostUpdateRequest(BaseModel):
    """추가개발비 입력 — 마스터 전용. 저장 시 status→confirm_requested."""

    dev_cost: int = Field(ge=0, le=1_000_000_000)


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


class BoardAttachmentUploadResponse(BaseModel):
    """첨부 파일 업로드 응답 — 폼이 글 저장 시 attachments 배열에 그대로 동봉."""

    file_url: str
    file_name: str
    mime_type: str
    size_bytes: int


class BoardAttachmentView(BaseModel):
    """상세에서 노출되는 첨부 정보(다운로드 링크)."""

    id: int
    file_url: str
    file_name: str
    mime_type: str
    size_bytes: int

    model_config = ConfigDict(from_attributes=True)


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
    category: str  # 신규 4종 + 레거시 키 관대 수용(라벨 fallback)
    status: BoardPostStatus
    title: str
    author_id: int
    author_email: str
    author_display: str
    comment_count: int
    has_attachments: bool = False
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
    category: str  # 신규 4종 + 레거시 키 관대 수용(라벨 fallback)
    status: BoardPostStatus
    title: str
    content_html: str
    author_id: int
    author_email: str
    author_display: str
    comments: list[BoardCommentItem]
    attachments: list[BoardAttachmentView]
    dev_cost: int | None  # 추가개발비(원) — 미입력이면 None
    can_edit: bool           # 본인 글 OR 마스터 — 글 수정/삭제 권한
    can_change_status: bool   # 마스터 전용 — 상태 변경 권한
    can_set_dev_cost: bool    # 마스터 & category='feature' — 개발비 입력 권한
    can_confirm: bool         # 운영자 & category='feature' & 컨펌요청 상태 — 컨펌 권한
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BoardMetaResponse(BaseModel):
    """카테고리·상태 라벨 메타 — 프론트 select/표시용."""

    categories: list[dict[str, str]]  # [{"key": "auth", "label": "로그인/회원가입"}, ...]
    statuses: list[dict[str, str]]    # [{"key": "review", "label": "요청사항검토"}, ...]
