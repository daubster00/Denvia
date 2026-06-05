"""CS · 휴지통(쪽지) 관리 라우터.

엔드포인트:
- GET    /admin/inbox/trash                목록
- GET    /admin/inbox/trash/{message_id}   단건 상세
- POST   /admin/inbox/trash/{message_id}/restore  복구 (deleted_at=NULL)
- DELETE /admin/inbox/trash/{message_id}   영구 삭제

사용자가 본인 쪽지함에서 삭제(soft delete)한 inbox_messages 행만 다룬다.
30일 보관 후 ``retention_tasks.purge_old_inbox_messages`` 가 자동 삭제하므로
응답에는 ``permanent_purge_at = deleted_at + 30 days`` 가 항상 포함된다.
"""

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.deps.auth import require_admin
from api.src.middleware.audit_actions import (
    AUDIT_INBOX_TRASH_HARD_DELETE,
    AUDIT_INBOX_TRASH_RESTORE,
    audit_action,
)
from api.src.models.base import get_session
from api.src.models.user import User
from api.src.schemas.admin.inbox_trash import (
    TrashDetailResponse,
    TrashListResponse,
)
from api.src.services import admin_inbox_trash_service

router = APIRouter(prefix="/admin/inbox/trash", tags=["admin-inbox-trash"])


@router.get("", response_model=TrashListResponse)
async def list_trash(
    response: Response,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> TrashListResponse:
    """휴지통 목록 — 사용자가 삭제한 모든 쪽지(deleted_at IS NOT NULL)."""
    response.headers["Cache-Control"] = "no-store"
    return await admin_inbox_trash_service.list_trash(page, per_page, admin, db)


@router.get("/{message_id}", response_model=TrashDetailResponse)
async def get_trash_detail(
    message_id: int,
    response: Response,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> TrashDetailResponse:
    """휴지통 단건 상세."""
    response.headers["Cache-Control"] = "no-store"
    return await admin_inbox_trash_service.get_trash_detail(message_id, admin, db)


@router.post("/{message_id}/restore", response_model=TrashDetailResponse)
@audit_action(AUDIT_INBOX_TRASH_RESTORE)
async def restore_trash_message(
    request: Request,
    message_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> TrashDetailResponse:
    """원래 사용자 쪽지함으로 복구 (deleted_at = NULL)."""
    return await admin_inbox_trash_service.restore_message(
        request, message_id, admin, db
    )


@router.delete("/{message_id}", status_code=204)
@audit_action(AUDIT_INBOX_TRASH_HARD_DELETE)
async def hard_delete_trash_message(
    request: Request,
    message_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> None:
    """휴지통 행 즉시 영구 삭제 — 30일 retention 대기 없이 DB row DELETE."""
    await admin_inbox_trash_service.hard_delete_message(
        request, message_id, admin, db
    )
