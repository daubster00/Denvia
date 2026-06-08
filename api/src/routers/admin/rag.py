"""RAG 관리 라우터 — Story 8.1/8.2/8.3 TXT 지식 업로드/편집/삭제 + 재빌드."""

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.deps.auth import require_admin, require_admin_page
from api.src.middleware.audit_actions import (
    AUDIT_RAG_KNOWLEDGE_DELETE,
    AUDIT_RAG_KNOWLEDGE_EDIT,
    AUDIT_RAG_REBUILD,
    AUDIT_RAG_UPLOAD,
    audit_action,
)
from api.src.middleware.rate_limit import limiter
from api.src.models.base import get_session
from api.src.models.user import User
from api.src.schemas.admin.rag import (
    KnowledgeDetailResponse,
    KnowledgeEditRequest,
    KnowledgeEditResponse,
    KnowledgeListResponse,
    KnowledgeUploadResponse,
    RagStatusResponse,
    RebuildJobStatusResponse,
    RebuildTriggerResponse,
)
from api.src.services import rag_admin_service
from api.src.utils.jwt import JWTDecodeError, SessionExpired, decode_admin_session_jwt

router = APIRouter(
    prefix="/admin/rag",
    tags=["admin-rag"],
    dependencies=[Depends(require_admin_page("/admin/rag"))],
)


def _admin_user_id_key(request: Request) -> str:
    """레이트 리밋 키: IP 대신 관리자 user_id 기반 (AC-8).

    다른 admin 라우터(anomaly·killswitch·payments 등)와 동일하게
    `denvia_admin_session` + `decode_admin_session_jwt` 를 사용한다.
    """
    cookie = request.cookies.get("denvia_admin_session")
    if not cookie:
        return get_remote_address(request)
    try:
        payload = decode_admin_session_jwt(cookie)
        return f"admin:{payload['sub']}"
    except (JWTDecodeError, SessionExpired, KeyError):
        return get_remote_address(request)


@router.post("/knowledge/upload", response_model=KnowledgeUploadResponse, status_code=201)
@limiter.limit("5/minute", key_func=_admin_user_id_key)
@audit_action(AUDIT_RAG_UPLOAD)
async def upload_knowledge(
    request: Request,
    file: UploadFile = File(...),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> KnowledgeUploadResponse:
    """A-401 TXT 지식 파일 업로드 + 1차 검증 + dry-run 파싱."""
    return await rag_admin_service.upload_and_validate(request, file, admin, db)


@router.get("/knowledge", response_model=KnowledgeListResponse)
async def list_knowledge(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> KnowledgeListResponse:
    """업로드된 지식 파일 목록 조회 (GET이므로 audit_logs INSERT 없음)."""
    return await rag_admin_service.list_uploads(page, per_page, db)


@router.get("/knowledge/{upload_id}", response_model=KnowledgeDetailResponse)
async def get_knowledge_detail(
    upload_id: int,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> KnowledgeDetailResponse:
    """단건 조회 + 파일 내용 반환 (편집 다이얼로그용, GET이므로 audit_logs INSERT 없음)."""
    upload = await rag_admin_service.get_upload(upload_id, db)
    try:
        content = Path(upload.original_path).read_text(encoding="utf-8")
    except OSError:
        raise HTTPException(
            500,
            detail={
                "code": "KNOWLEDGE_FILE_MISSING",
                "message": "지식 파일을 디스크에서 찾을 수 없습니다. 운영팀에 문의하세요.",
            },
        )
    return KnowledgeDetailResponse(
        id=upload.id,
        filename=upload.filename,
        uploaded_at=upload.uploaded_at,
        last_modified_at=upload.last_modified_at,
        size_bytes=upload.size_bytes,
        chunk_count=upload.chunk_count,
        category_count=upload.category_count,
        status=upload.status,
        content=content,
    )


@router.put("/knowledge/{upload_id}", response_model=KnowledgeEditResponse)
@audit_action(AUDIT_RAG_KNOWLEDGE_EDIT)
async def edit_knowledge(
    request: Request,
    upload_id: int,
    body: KnowledgeEditRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> KnowledgeEditResponse:
    """지식 파일 내용 편집 (dry-run 재검증 + FS 덮어쓰기 + DB 갱신)."""
    return await rag_admin_service.edit_upload(request, upload_id, body.content, admin, db)


@router.delete("/knowledge/{upload_id}", status_code=204)
@audit_action(AUDIT_RAG_KNOWLEDGE_DELETE)
async def delete_knowledge(
    request: Request,
    upload_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> None:
    """지식 파일 소프트 삭제 (FS 파일 보존 — 30일 Retention은 Story 8.3)."""
    await rag_admin_service.delete_upload(request, upload_id, admin, db)


@router.get("/status", response_model=RagStatusResponse)
async def rag_status(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> RagStatusResponse:
    """재빌드 대기 상태 조회 (GET이므로 audit_logs INSERT 없음)."""
    return await rag_admin_service.get_rag_status(db)


@router.post("/rebuild", response_model=RebuildTriggerResponse, status_code=202)
@audit_action(AUDIT_RAG_REBUILD)
async def trigger_rebuild(
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> RebuildTriggerResponse:
    """벡터스토어 전체 재빌드 트리거 (동시 1건 제한, AC-2)."""
    return await rag_admin_service.trigger_rebuild(request, admin, db)


@router.post("/rebuild/{job_id}/cancel", response_model=RebuildJobStatusResponse)
@audit_action(AUDIT_RAG_REBUILD)
async def cancel_rebuild(
    request: Request,
    job_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> RebuildJobStatusResponse:
    """진행 중인 재빌드 취소 (AC-6)."""
    return await rag_admin_service.cancel_rebuild(request, job_id, admin, db)


@router.get("/rebuild/{job_id}", response_model=RebuildJobStatusResponse)
async def get_rebuild_job(
    job_id: int,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> RebuildJobStatusResponse:
    """재빌드 job 단건 조회 — SSE 불가 환경 폴링 fallback (AC-7)."""
    return await rag_admin_service.get_rebuild_job(job_id, db)
