"""관리자 수정요청 게시판 라우터.

prefix: /admin/board   (main.py 에서 /api/v1 prefix 가 추가됨 → /api/v1/admin/board/...)

엔드포인트:
  GET    /admin/board/meta                    카테고리·상태 라벨 메타
  GET    /admin/board/posts                   목록 (filter: category, status, page, per_page)
  POST   /admin/board/posts                   신규 글 (기본 status='review')
  GET    /admin/board/posts/{post_id}         상세 + 댓글 + 권한 플래그
  PUT    /admin/board/posts/{post_id}         본인/마스터 글 본문·첨부 수정
  PATCH  /admin/board/posts/{post_id}/status  상태 변경 — 마스터 전용
  PATCH  /admin/board/posts/{post_id}/dev-cost 추가개발비 입력 — 마스터 전용(→컨펌요청)
  POST   /admin/board/posts/{post_id}/confirm 추가개발비 컨펌 — 운영자 전용(→컨펌)
  DELETE /admin/board/posts/{post_id}         글 삭제 (CASCADE 로 댓글·첨부도 삭제)
  POST   /admin/board/posts/{post_id}/comments  댓글 작성
  PUT    /admin/board/comments/{comment_id}   댓글 수정
  DELETE /admin/board/comments/{comment_id}   댓글 삭제
  POST   /admin/board/image-upload            본문 에디터 이미지 업로드
  POST   /admin/board/attachment-upload       글 첨부 파일 업로드(문서/압축/이미지)

가드: require_admin (denvia_admin_session 쿠키).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.deps.auth import require_admin, require_admin_page
from api.src.models.base import get_session
from api.src.models.user import User
from api.src.schemas.admin.board import (
    BoardAttachmentUploadResponse,
    BoardCommentCreateRequest,
    BoardCommentUpdateRequest,
    BoardDevCostUpdateRequest,
    BoardImageUploadResponse,
    BoardMetaResponse,
    BoardPostCreateRequest,
    BoardPostDetailResponse,
    BoardPostListResponse,
    BoardPostStatusUpdateRequest,
    BoardPostUpdateRequest,
)
from api.src.services import admin_board_service

router = APIRouter(
    prefix="/admin/board",
    tags=["admin-board"],
    dependencies=[Depends(require_admin_page("/admin/board"))],
)


# ── 메타 ──────────────────────────────────────────────────────────────────────
@router.get("/meta", response_model=BoardMetaResponse)
async def get_board_meta(
    admin: User = Depends(require_admin),
) -> BoardMetaResponse:
    """카테고리·상태 라벨 정적 메타."""
    return admin_board_service.get_meta()


# ── 글 ────────────────────────────────────────────────────────────────────────
@router.get("/posts", response_model=BoardPostListResponse)
async def list_board_posts(
    category: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> BoardPostListResponse:
    return await admin_board_service.list_posts(
        db,
        category=category,
        status=status,
        page=page,
        per_page=per_page,
    )


@router.post("/posts", response_model=BoardPostDetailResponse, status_code=201)
async def create_board_post(
    payload: BoardPostCreateRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> BoardPostDetailResponse:
    post_id = await admin_board_service.create_post(
        db,
        current_user=admin,
        category=payload.category,
        title=payload.title,
        content_html=payload.content_html,
        attachments=payload.attachments,
    )
    return await admin_board_service.get_post(
        db, post_id=post_id, current_user=admin
    )


@router.get("/posts/{post_id}", response_model=BoardPostDetailResponse)
async def get_board_post(
    post_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> BoardPostDetailResponse:
    return await admin_board_service.get_post(
        db, post_id=post_id, current_user=admin
    )


@router.put("/posts/{post_id}", response_model=BoardPostDetailResponse)
async def update_board_post(
    post_id: int,
    payload: BoardPostUpdateRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> BoardPostDetailResponse:
    await admin_board_service.update_post(
        db,
        post_id=post_id,
        current_user=admin,
        category=payload.category,
        title=payload.title,
        content_html=payload.content_html,
        attachments=payload.attachments,
    )
    return await admin_board_service.get_post(
        db, post_id=post_id, current_user=admin
    )


@router.patch("/posts/{post_id}/status", response_model=BoardPostDetailResponse)
async def change_board_post_status(
    post_id: int,
    payload: BoardPostStatusUpdateRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> BoardPostDetailResponse:
    await admin_board_service.update_post_status(
        db,
        post_id=post_id,
        current_user=admin,
        status=payload.status,
    )
    return await admin_board_service.get_post(
        db, post_id=post_id, current_user=admin
    )


@router.patch("/posts/{post_id}/dev-cost", response_model=BoardPostDetailResponse)
async def set_board_post_dev_cost(
    post_id: int,
    payload: BoardDevCostUpdateRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> BoardPostDetailResponse:
    """추가개발비 입력 — 마스터 전용. 저장 시 상태 → 컨펌요청."""
    await admin_board_service.set_dev_cost(
        db,
        post_id=post_id,
        current_user=admin,
        dev_cost=payload.dev_cost,
    )
    return await admin_board_service.get_post(
        db, post_id=post_id, current_user=admin
    )


@router.post("/posts/{post_id}/confirm", response_model=BoardPostDetailResponse)
async def confirm_board_post(
    post_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> BoardPostDetailResponse:
    """추가개발비 컨펌 — 운영자 전용. 상태 컨펌요청 → 컨펌."""
    await admin_board_service.confirm_dev_cost(
        db,
        post_id=post_id,
        current_user=admin,
    )
    return await admin_board_service.get_post(
        db, post_id=post_id, current_user=admin
    )


@router.delete("/posts/{post_id}", status_code=204)
async def delete_board_post(
    post_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> Response:
    await admin_board_service.delete_post(
        db, post_id=post_id, current_user=admin
    )
    return Response(status_code=204)


# ── 댓글 ─────────────────────────────────────────────────────────────────────
@router.post(
    "/posts/{post_id}/comments",
    response_model=BoardPostDetailResponse,
    status_code=201,
)
async def create_board_comment(
    post_id: int,
    payload: BoardCommentCreateRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> BoardPostDetailResponse:
    await admin_board_service.create_comment(
        db,
        post_id=post_id,
        current_user=admin,
        content=payload.content,
    )
    return await admin_board_service.get_post(
        db, post_id=post_id, current_user=admin
    )


@router.put("/comments/{comment_id}", status_code=204)
async def update_board_comment(
    comment_id: int,
    payload: BoardCommentUpdateRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> Response:
    await admin_board_service.update_comment(
        db,
        comment_id=comment_id,
        current_user=admin,
        content=payload.content,
    )
    return Response(status_code=204)


@router.delete("/comments/{comment_id}", status_code=204)
async def delete_board_comment(
    comment_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> Response:
    await admin_board_service.delete_comment(
        db, comment_id=comment_id, current_user=admin
    )
    return Response(status_code=204)


# ── 이미지 업로드 ─────────────────────────────────────────────────────────────
@router.post("/image-upload", response_model=BoardImageUploadResponse)
async def upload_board_image(
    file: UploadFile = File(...),
    admin: User = Depends(require_admin),
) -> BoardImageUploadResponse:
    return await admin_board_service.upload_board_image(file)


# ── 첨부 파일 업로드 ──────────────────────────────────────────────────────────
@router.post("/attachment-upload", response_model=BoardAttachmentUploadResponse)
async def upload_board_attachment(
    file: UploadFile = File(...),
    admin: User = Depends(require_admin),
) -> BoardAttachmentUploadResponse:
    """글 첨부 파일 업로드 — 문서/압축/이미지, 20MB 이하."""
    return await admin_board_service.upload_board_attachment(file)
