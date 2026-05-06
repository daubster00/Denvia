"""콘텐츠 관리 라우터 — Story 7.2 팝업 admin CRUD.

Story 7.1(notice CRUD)이 추후 동일 모듈에 함수를 추가하도록 prefix='/admin'로
설계 — 본 스토리는 popups 6 endpoint만 mount.

엔드포인트:
- GET    /admin/popups                   목록 페이지네이션
- GET    /admin/popups/{popup_id}        단건 조회 (편집 prefill)
- POST   /admin/popups                   신규 생성
- PUT    /admin/popups/{popup_id}        전체 필드 교체 (편집 모달 저장)
- PATCH  /admin/popups/{popup_id}        is_active 즉시 토글 (목록 행)
- DELETE /admin/popups/{popup_id}        soft delete
"""

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.deps.auth import require_admin
from api.src.middleware.audit_actions import (
    AUDIT_POPUP_CREATE,
    AUDIT_POPUP_DELETE,
    AUDIT_POPUP_TOGGLE,
    AUDIT_POPUP_UPDATE,
    audit_action,
)
from api.src.models.base import get_session
from api.src.models.user import User
from api.src.schemas.admin.popup import (
    PopupCreateRequest,
    PopupDetailResponse,
    PopupListResponse,
    PopupTogglePatchRequest,
    PopupToggleResponse,
    PopupUpdateRequest,
)
from api.src.services import popup_service

router = APIRouter(prefix="/admin", tags=["admin-content"])


@router.get("/popups", response_model=PopupListResponse)
async def list_popups(
    response: Response,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> PopupListResponse:
    """팝업 목록 (GET — audit_logs INSERT 없음). AC-2: Cache-Control: no-store."""
    response.headers["Cache-Control"] = "no-store"
    return await popup_service.list_popups(page, per_page, admin, db)


@router.get("/popups/{popup_id}", response_model=PopupDetailResponse)
async def get_popup_detail(
    popup_id: int,
    response: Response,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> PopupDetailResponse:
    """팝업 단건 조회 — 편집 다이얼로그 prefill용. AC-3: Cache-Control: no-store."""
    response.headers["Cache-Control"] = "no-store"
    return await popup_service.get_popup_detail(popup_id, admin, db)


@router.post("/popups", response_model=PopupDetailResponse, status_code=201)
@audit_action(AUDIT_POPUP_CREATE)
async def create_popup(
    request: Request,
    body: PopupCreateRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> PopupDetailResponse:
    """팝업 신규 생성."""
    return await popup_service.create_popup(request, body, admin, db)


@router.put("/popups/{popup_id}", response_model=PopupDetailResponse)
@audit_action(AUDIT_POPUP_UPDATE)
async def update_popup(
    request: Request,
    popup_id: int,
    body: PopupUpdateRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> PopupDetailResponse:
    """팝업 전체 필드 교체 (편집 모달 저장)."""
    return await popup_service.update_popup(request, popup_id, body, admin, db)


@router.patch("/popups/{popup_id}", response_model=PopupToggleResponse)
@audit_action(AUDIT_POPUP_TOGGLE)
async def toggle_popup(
    request: Request,
    popup_id: int,
    body: PopupTogglePatchRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> PopupToggleResponse:
    """is_active 즉시 토글 — 목록 행 Switch 빠른 경로."""
    return await popup_service.toggle_active(
        request, popup_id, body.is_active, admin, db
    )


@router.delete("/popups/{popup_id}", status_code=204)
@audit_action(AUDIT_POPUP_DELETE)
async def delete_popup(
    request: Request,
    popup_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> None:
    """팝업 soft delete (deleted_at = NOW())."""
    await popup_service.delete_popup(request, popup_id, admin, db)
