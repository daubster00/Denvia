"""동의어 사전 admin 라우터 — Story 8.5 (A-405).

GET    /api/v1/admin/rag/synonyms                목록 (q/page/size)
POST   /api/v1/admin/rag/synonyms                신규 그룹
PUT    /api/v1/admin/rag/synonyms/{id}           수정
DELETE /api/v1/admin/rag/synonyms/{id}           삭제
POST   /api/v1/admin/rag/synonyms/import         CSV 일괄 가져오기 (dry_run 지원)
GET    /api/v1/admin/rag/synonyms/export         CSV 내보내기

가드: require_admin.
변경 시 미들웨어가 자동으로 audit_logs INSERT (audit_action 데코레이터로 액션 지정).
Rate limit: GET 60/min, write 30/min (admin user_id 키, IP 폴백).
"""
from __future__ import annotations

import structlog
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.deps.auth import require_admin
from api.src.middleware.audit_actions import (
    AUDIT_SYNONYM_EDIT,
    AUDIT_SYNONYM_EXPORT,
    audit_action,
)
from api.src.middleware.rate_limit import limiter
from api.src.models.base import get_session
from api.src.models.user import User
from api.src.schemas.admin.synonyms import (
    ImportPreviewResponse,
    SynonymGroupCreateRequest,
    SynonymGroupRead,
    SynonymGroupUpdateRequest,
    SynonymListResponse,
)
from api.src.services import synonym_service
from api.src.utils.jwt import (
    JWTDecodeError,
    SessionExpired,
    decode_admin_session_jwt,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin/rag", tags=["admin-rag"])


def _admin_user_id_key(request: Request) -> str:
    cookie = request.cookies.get("denvia_admin_session")
    if not cookie:
        return get_remote_address(request)
    try:
        payload = decode_admin_session_jwt(cookie)
        return f"admin:{payload['sub']}"
    except (JWTDecodeError, SessionExpired, KeyError, Exception):
        return get_remote_address(request)


@router.get("/synonyms", response_model=SynonymListResponse)
@limiter.limit("60/minute", key_func=_admin_user_id_key)
async def list_synonyms(
    request: Request,
    response: Response,
    q: str | None = Query(None, max_length=100),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> SynonymListResponse:
    result = await synonym_service.list_groups(db, q=q, page=page, size=size)
    response.headers["Cache-Control"] = "no-store"
    logger.info(
        "admin.rag.synonyms.listed",
        actor_user_id=admin.id,
        has_q=bool(q),
        page=page,
        size=size,
        total=result.total,
    )
    return result


@router.post(
    "/synonyms",
    response_model=SynonymGroupRead,
    status_code=201,
)
@limiter.limit("30/minute", key_func=_admin_user_id_key)
@audit_action(AUDIT_SYNONYM_EDIT)
async def create_synonym(
    request: Request,
    payload: SynonymGroupCreateRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> SynonymGroupRead:
    row = await synonym_service.create_group(request, db, payload, admin)
    return SynonymGroupRead.model_validate(row)


@router.put(
    "/synonyms/{group_id}",
    response_model=SynonymGroupRead,
)
@limiter.limit("30/minute", key_func=_admin_user_id_key)
@audit_action(AUDIT_SYNONYM_EDIT)
async def update_synonym(
    request: Request,
    group_id: int,
    payload: SynonymGroupUpdateRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> SynonymGroupRead:
    row = await synonym_service.update_group(request, db, group_id, payload, admin)
    return SynonymGroupRead.model_validate(row)


@router.delete(
    "/synonyms/{group_id}",
    status_code=204,
)
@limiter.limit("30/minute", key_func=_admin_user_id_key)
@audit_action(AUDIT_SYNONYM_EDIT)
async def delete_synonym(
    request: Request,
    group_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> Response:
    await synonym_service.delete_group(request, db, group_id)
    return Response(status_code=204)


@router.post(
    "/synonyms/import",
    response_model=ImportPreviewResponse,
)
@limiter.limit("30/minute", key_func=_admin_user_id_key)
@audit_action(AUDIT_SYNONYM_EDIT)
async def import_synonyms(
    request: Request,
    file: UploadFile = File(...),
    dry_run: bool = Query(True),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> ImportPreviewResponse:
    if file.content_type not in (
        "text/csv",
        "application/vnd.ms-excel",
        "application/octet-stream",
        None,
    ):
        raise HTTPException(
            status_code=415,
            detail={
                "code": "IMPORT_CONTENT_TYPE_INVALID",
                "message": "CSV 파일만 업로드 가능합니다.",
            },
        )

    file_bytes = await file.read()
    return await synonym_service.import_csv(
        request, db, file_bytes, dry_run=dry_run, admin=admin
    )


@router.get(
    "/synonyms/export",
    response_class=Response,
)
@limiter.limit("30/minute", key_func=_admin_user_id_key)
@audit_action(AUDIT_SYNONYM_EXPORT)
async def export_synonyms(
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> Response:
    body = await synonym_service.export_csv(db)
    filename = synonym_service._csv_filename_today()
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


__all__ = ["router"]
