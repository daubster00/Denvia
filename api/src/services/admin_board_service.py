"""관리자 수정요청 게시판 서비스 — CRUD + 댓글 + 이미지 업로드.

권한 모델 (Story 10.3 — admin_grade='master' DB 컬럼 기준):
- master 등급(`users.admin_grade='master'`):
  · 모든 글/댓글 수정·삭제 가능
  · 상태(status) 변경 가능 (다른 admin은 불가)
- 일반 admin: 본인이 작성한 글/댓글만 수정·삭제 가능

content_html 은 Tiptap → sanitize_body_html() 적용 후 저장(XSS 방어).
댓글 content 는 plain text — html.escape() 적용 후 저장 (목록/상세 응답 시 그대로 노출).

이미지 저장 경로 : api/data/uploads/admin_board_images/<uuid>.<ext>
공개 URL prefix  : /static/admin-board-images
허용 확장자/MIME: png/jpg/jpeg/webp, 5MB
"""

from __future__ import annotations

import html as _html
import uuid
from datetime import datetime, timezone
from pathlib import Path

import structlog
from fastapi import HTTPException, UploadFile
from sqlalchemy import String, case, cast, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.admin_board_comment import AdminBoardComment
from api.src.models.admin_board_post import AdminBoardPost
from api.src.models.user import User
from api.src.schemas.admin.board import (
    BoardCategory,
    BoardCommentItem,
    BoardImageUploadResponse,
    BoardMetaResponse,
    BoardPostDetailResponse,
    BoardPostListItem,
    BoardPostListResponse,
    BoardPostStatus,
)
from api.src.utils.html_sanitize import sanitize_body_html

logger = structlog.get_logger(__name__)


# ── 상수 ──────────────────────────────────────────────────────────────────────
# DEPRECATED alias — Story 10.3에서 admin_grade='master' DB 컬럼 기준으로 일괄 교체됨.
# 외부에서 직접 import 하던 호출 경로 보호를 위해 1 사이클 유지(후속 클린업 마이그에서 제거 검토).
# 신규 코드는 사용하지 말 것. 마스터 식별은 `is_btmdesign(user)` 또는 직접 `user.admin_grade == 'master'`.
BTMDESIGN_EMAIL = "btmdesign@naver.com"

# 카테고리 라벨 — 응답 메타로 노출. key 는 BoardCategory Literal 과 일치해야 한다.
CATEGORY_LABELS: list[dict[str, str]] = [
    {"key": "auth", "label": "로그인/회원가입"},
    {"key": "mypage", "label": "마이페이지"},
    {"key": "chatbot", "label": "챗봇/RAG"},
    {"key": "billing", "label": "결제·구독"},
    {"key": "admin", "label": "관리자"},
    {"key": "messaging", "label": "알림톡/SMS"},
    {"key": "design", "label": "디자인/UI"},
    {"key": "etc", "label": "기타"},
]
ALLOWED_CATEGORIES = {c["key"] for c in CATEGORY_LABELS}

# 상태 라벨 — 0040 + 0041_board_status_completed board_post_status_enum 과 동기.
STATUS_LABELS: list[dict[str, str]] = [
    {"key": "review", "label": "요청사항검토"},
    {"key": "in_progress", "label": "수정중"},
    {"key": "completed", "label": "수정완료"},
    {"key": "rejected", "label": "수정불가"},
    {"key": "on_hold", "label": "보류"},
]
ALLOWED_STATUSES = {s["key"] for s in STATUS_LABELS}

# 목록 정렬 우선순위 — 위에서부터 노출되는 순서. 값이 작을수록 상단.
# 같은 상태 내에서는 created_at DESC (최신 글이 위).
STATUS_SORT_ORDER: dict[str, int] = {
    "review": 1,        # 요청사항검토
    "in_progress": 2,   # 수정중
    "on_hold": 3,       # 보류
    "rejected": 4,      # 수정불가
    "completed": 5,     # 수정완료
}

# 이미지 업로드
BOARD_IMAGE_DIR = (
    Path(__file__).parent.parent.parent / "data" / "uploads" / "admin_board_images"
)
BOARD_IMAGE_URL_PREFIX = "/static/admin-board-images"
_ALLOWED_IMAGE_MIMES = {"image/png", "image/jpeg", "image/webp"}
_ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
_MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


# ── 권한 헬퍼 ────────────────────────────────────────────────────────────────
def is_btmdesign(user: User) -> bool:
    """마스터 등급 여부 — Story 10.3 이후 admin_grade='master' 기준.

    함수명은 호출 측 호환을 위해 유지하지만 내부 판정은 DB 컬럼 기반으로 전환됨.
    추후 함수명을 `is_master_admin(user)` 로 정리할 수 있음(클린업 마이그).
    """
    return getattr(user, "admin_grade", None) == "master"


def _display_name(email: str) -> str:
    """이메일의 @ 앞 부분을 표시명으로 사용. 길면 잘라낸다."""
    if not email:
        return "익명"
    local = email.split("@", 1)[0]
    return local[:40]


def _ensure_category(category: str) -> None:
    if category not in ALLOWED_CATEGORIES:
        raise HTTPException(
            422,
            detail={
                "code": "BOARD_CATEGORY_INVALID",
                "message": "올바르지 않은 카테고리입니다.",
            },
        )


def _ensure_status(status: str) -> None:
    if status not in ALLOWED_STATUSES:
        raise HTTPException(
            422,
            detail={
                "code": "BOARD_STATUS_INVALID",
                "message": "올바르지 않은 상태값입니다.",
            },
        )


def _require_post_edit_permission(post: AdminBoardPost, user: User) -> None:
    if post.author_id != user.id and not is_btmdesign(user):
        raise HTTPException(
            403,
            detail={
                "code": "BOARD_POST_FORBIDDEN",
                "message": "본인이 작성한 글만 수정/삭제할 수 있습니다.",
            },
        )


def _require_comment_edit_permission(
    comment: AdminBoardComment, user: User
) -> None:
    if comment.author_id != user.id and not is_btmdesign(user):
        raise HTTPException(
            403,
            detail={
                "code": "BOARD_COMMENT_FORBIDDEN",
                "message": "본인이 작성한 댓글만 수정/삭제할 수 있습니다.",
            },
        )


def _require_btmdesign(user: User) -> None:
    if not is_btmdesign(user):
        raise HTTPException(
            403,
            detail={
                "code": "BOARD_STATUS_FORBIDDEN",
                "message": "상태 변경은 btmdesign 마스터 계정만 가능합니다.",
            },
        )


# ── 조회 ──────────────────────────────────────────────────────────────────────
async def list_posts(
    db: AsyncSession,
    *,
    category: str | None = None,
    status: str | None = None,
    page: int = 1,
    per_page: int = 20,
) -> BoardPostListResponse:
    """글 목록 — 상태 우선순위(검토→수정중→보류→수정불가→수정완료) 후 created_at DESC."""
    base = (
        select(
            AdminBoardPost.id,
            AdminBoardPost.category,
            AdminBoardPost.status,
            AdminBoardPost.title,
            AdminBoardPost.author_id,
            AdminBoardPost.created_at,
            AdminBoardPost.updated_at,
            User.email,
        )
        .join(User, User.id == AdminBoardPost.author_id)
    )
    count_q = (
        select(func.count())
        .select_from(AdminBoardPost)
        .join(User, User.id == AdminBoardPost.author_id)
    )

    if category:
        _ensure_category(category)
        base = base.where(AdminBoardPost.category == category)
        count_q = count_q.where(AdminBoardPost.category == category)
    if status:
        _ensure_status(status)
        base = base.where(AdminBoardPost.status == status)
        count_q = count_q.where(AdminBoardPost.status == status)

    total = (await db.execute(count_q)).scalar_one()

    # status 컬럼이 PG enum(board_post_status_enum)이라
    # SQLAlchemy case(dict, value=...)가 만드는 VARCHAR 바인딩과 직접 비교가 안 된다
    # ("operator does not exist: board_post_status_enum = character varying").
    # 양쪽을 text로 맞추기 위해 컬럼을 String으로 캐스팅.
    status_order = case(
        STATUS_SORT_ORDER,
        value=cast(AdminBoardPost.status, String),
        else_=99,
    )

    rows = (
        await db.execute(
            base.order_by(
                status_order.asc(),
                desc(AdminBoardPost.created_at),
                desc(AdminBoardPost.id),
            )
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
    ).all()

    post_ids = [r.id for r in rows]
    comment_counts: dict[int, int] = {}
    if post_ids:
        cc_rows = (
            await db.execute(
                select(
                    AdminBoardComment.post_id, func.count(AdminBoardComment.id)
                )
                .where(AdminBoardComment.post_id.in_(post_ids))
                .group_by(AdminBoardComment.post_id)
            )
        ).all()
        comment_counts = {pid: cnt for pid, cnt in cc_rows}

    items = [
        BoardPostListItem(
            id=r.id,
            category=r.category,
            status=r.status,
            title=r.title,
            author_id=r.author_id,
            author_email=r.email,
            author_display=_display_name(r.email),
            comment_count=int(comment_counts.get(r.id, 0)),
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]
    return BoardPostListResponse(
        items=items, page=page, per_page=per_page, total=int(total)
    )


async def get_post(
    db: AsyncSession,
    *,
    post_id: int,
    current_user: User,
) -> BoardPostDetailResponse:
    """글 상세 — 댓글 + 작성자 이메일 join."""
    row = (
        await db.execute(
            select(AdminBoardPost, User.email)
            .join(User, User.id == AdminBoardPost.author_id)
            .where(AdminBoardPost.id == post_id)
        )
    ).first()
    if row is None:
        raise HTTPException(
            404,
            detail={"code": "BOARD_POST_NOT_FOUND", "message": "글을 찾을 수 없습니다."},
        )
    post, author_email = row

    comment_rows = (
        await db.execute(
            select(AdminBoardComment, User.email)
            .join(User, User.id == AdminBoardComment.author_id)
            .where(AdminBoardComment.post_id == post_id)
            .order_by(AdminBoardComment.created_at.asc(), AdminBoardComment.id.asc())
        )
    ).all()

    is_master = is_btmdesign(current_user)
    comments = [
        BoardCommentItem(
            id=c.id,
            post_id=c.post_id,
            author_id=c.author_id,
            author_email=email,
            author_display=_display_name(email),
            content=c.content,
            created_at=c.created_at,
            updated_at=c.updated_at,
            can_edit=is_master or c.author_id == current_user.id,
        )
        for c, email in comment_rows
    ]

    return BoardPostDetailResponse(
        id=post.id,
        category=post.category,
        status=post.status,
        title=post.title,
        content_html=post.content_html,
        author_id=post.author_id,
        author_email=author_email,
        author_display=_display_name(author_email),
        comments=comments,
        can_edit=is_master or post.author_id == current_user.id,
        can_change_status=is_master,
        created_at=post.created_at,
        updated_at=post.updated_at,
    )


# ── 글 CRUD ──────────────────────────────────────────────────────────────────
async def create_post(
    db: AsyncSession,
    *,
    current_user: User,
    category: str,
    title: str,
    content_html: str,
) -> int:
    _ensure_category(category)
    safe_html = sanitize_body_html(content_html)
    post = AdminBoardPost(
        author_id=current_user.id,
        category=category,
        status="review",  # 기본 상태 — 요청사항검토
        title=title,
        content_html=safe_html,
    )
    db.add(post)
    await db.flush()
    await db.commit()
    logger.info(
        "admin_board.post.created",
        post_id=post.id,
        author_id=current_user.id,
        category=category,
    )
    return post.id


async def update_post(
    db: AsyncSession,
    *,
    post_id: int,
    current_user: User,
    category: str,
    title: str,
    content_html: str,
) -> None:
    post = await _get_post_or_404(db, post_id)
    _require_post_edit_permission(post, current_user)
    _ensure_category(category)

    post.category = category
    post.title = title
    post.content_html = sanitize_body_html(content_html)
    post.updated_at = datetime.now(timezone.utc)
    await db.commit()
    logger.info(
        "admin_board.post.updated",
        post_id=post.id,
        editor_id=current_user.id,
    )


async def update_post_status(
    db: AsyncSession,
    *,
    post_id: int,
    current_user: User,
    status: str,
) -> None:
    _require_btmdesign(current_user)
    _ensure_status(status)
    post = await _get_post_or_404(db, post_id)
    post.status = status
    post.updated_at = datetime.now(timezone.utc)
    await db.commit()
    logger.info(
        "admin_board.post.status_changed",
        post_id=post.id,
        new_status=status,
        editor_id=current_user.id,
    )


async def delete_post(
    db: AsyncSession,
    *,
    post_id: int,
    current_user: User,
) -> None:
    post = await _get_post_or_404(db, post_id)
    _require_post_edit_permission(post, current_user)
    await db.delete(post)
    await db.commit()
    logger.info(
        "admin_board.post.deleted",
        post_id=post_id,
        deleter_id=current_user.id,
    )


async def _get_post_or_404(db: AsyncSession, post_id: int) -> AdminBoardPost:
    post = (
        await db.execute(
            select(AdminBoardPost).where(AdminBoardPost.id == post_id)
        )
    ).scalar_one_or_none()
    if post is None:
        raise HTTPException(
            404,
            detail={
                "code": "BOARD_POST_NOT_FOUND",
                "message": "글을 찾을 수 없습니다.",
            },
        )
    return post


# ── 댓글 CRUD ────────────────────────────────────────────────────────────────
async def create_comment(
    db: AsyncSession,
    *,
    post_id: int,
    current_user: User,
    content: str,
) -> int:
    # 글 존재 여부 확인 — FK CASCADE 가 막아주지만 명시적 404 가 더 친절.
    await _get_post_or_404(db, post_id)
    safe = _html.escape(content.strip())
    if not safe:
        raise HTTPException(
            422,
            detail={
                "code": "BOARD_COMMENT_EMPTY",
                "message": "댓글 내용을 입력해주세요.",
            },
        )
    comment = AdminBoardComment(
        post_id=post_id,
        author_id=current_user.id,
        content=safe,
    )
    db.add(comment)
    await db.flush()
    await db.commit()
    logger.info(
        "admin_board.comment.created",
        comment_id=comment.id,
        post_id=post_id,
        author_id=current_user.id,
    )
    return comment.id


async def update_comment(
    db: AsyncSession,
    *,
    comment_id: int,
    current_user: User,
    content: str,
) -> None:
    comment = await _get_comment_or_404(db, comment_id)
    _require_comment_edit_permission(comment, current_user)
    safe = _html.escape(content.strip())
    if not safe:
        raise HTTPException(
            422,
            detail={
                "code": "BOARD_COMMENT_EMPTY",
                "message": "댓글 내용을 입력해주세요.",
            },
        )
    comment.content = safe
    comment.updated_at = datetime.now(timezone.utc)
    await db.commit()


async def delete_comment(
    db: AsyncSession,
    *,
    comment_id: int,
    current_user: User,
) -> None:
    comment = await _get_comment_or_404(db, comment_id)
    _require_comment_edit_permission(comment, current_user)
    await db.delete(comment)
    await db.commit()


async def _get_comment_or_404(
    db: AsyncSession, comment_id: int
) -> AdminBoardComment:
    comment = (
        await db.execute(
            select(AdminBoardComment).where(AdminBoardComment.id == comment_id)
        )
    ).scalar_one_or_none()
    if comment is None:
        raise HTTPException(
            404,
            detail={
                "code": "BOARD_COMMENT_NOT_FOUND",
                "message": "댓글을 찾을 수 없습니다.",
            },
        )
    return comment


# ── 이미지 업로드 ────────────────────────────────────────────────────────────
async def upload_board_image(file: UploadFile) -> BoardImageUploadResponse:
    """본문 에디터에서 호출되는 이미지 업로드 — 5MB / jpg·png·webp 제한."""
    if file.content_type not in _ALLOWED_IMAGE_MIMES:
        raise HTTPException(
            422,
            detail={
                "code": "BOARD_IMAGE_MIME_INVALID",
                "message": "PNG·JPG·WEBP 이미지만 첨부할 수 있습니다.",
            },
        )

    raw_name = file.filename or ""
    ext = Path(raw_name).suffix.lower()
    if ext not in _ALLOWED_IMAGE_EXTS:
        raise HTTPException(
            422,
            detail={
                "code": "BOARD_IMAGE_EXT_INVALID",
                "message": "PNG·JPG·WEBP 확장자만 허용됩니다.",
            },
        )

    contents = await file.read()
    size = len(contents)
    if size > _MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(
            422,
            detail={
                "code": "BOARD_IMAGE_TOO_LARGE",
                "message": "이미지 크기는 5MB 이하여야 합니다.",
            },
        )

    BOARD_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    safe_filename = f"{uuid.uuid4().hex}{ext}"
    dest = BOARD_IMAGE_DIR / safe_filename
    dest.write_bytes(contents)

    return BoardImageUploadResponse(
        file_url=f"{BOARD_IMAGE_URL_PREFIX}/{safe_filename}",
        file_name=raw_name[:255] or safe_filename,
        mime_type=file.content_type,
        size_bytes=size,
    )


# ── 메타 ──────────────────────────────────────────────────────────────────────
def get_meta() -> BoardMetaResponse:
    """프론트 select/표시 라벨 — DB hit 없음."""
    return BoardMetaResponse(
        categories=CATEGORY_LABELS,
        statuses=STATUS_LABELS,
    )


__all__ = [
    "BTMDESIGN_EMAIL",
    "BOARD_IMAGE_DIR",
    "BOARD_IMAGE_URL_PREFIX",
    "is_btmdesign",
    "list_posts",
    "get_post",
    "create_post",
    "update_post",
    "update_post_status",
    "delete_post",
    "create_comment",
    "update_comment",
    "delete_comment",
    "upload_board_image",
    "get_meta",
]
