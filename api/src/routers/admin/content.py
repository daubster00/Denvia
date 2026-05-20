"""콘텐츠 관리 라우터 — Story 7.1 공지(쪽지) + 7.2 v2 팝업 admin CRUD + 7.3/7.4 토글.

엔드포인트:
- GET    /admin/popups                   목록 페이지네이션
- GET    /admin/popups/{popup_id}        단건 조회 (편집 prefill)
- POST   /admin/popups                   신규 생성
- PUT    /admin/popups/{popup_id}        전체 필드 교체 (편집 모달 저장)
- PATCH  /admin/popups/{popup_id}        is_active 즉시 토글 (목록 행)
- DELETE /admin/popups/{popup_id}        soft delete
- POST   /admin/popups/image-upload      이미지 업로드 (Story 7.2 v2)
- GET    /admin/notices                  공지(쪽지) 목록
- GET    /admin/notices/{notice_id}      공지 단건 조회
- GET    /admin/notices/{notice_id}/recipients  수신자 목록 — read/unread 분리 페이지네이션
- POST   /admin/notices                  공지 작성+즉시 발행 (target_segment fan-out)
- DELETE /admin/notices/{notice_id}      공지 hard delete (CASCADE로 inbox 회수)
- GET    /admin/inbox/preview-config     쪽지함 미리보기 동시 노출 최대 개수 조회
- PUT    /admin/inbox/preview-config     쪽지함 미리보기 동시 노출 최대 개수 저장
- GET    /admin/runtime-config           서비스 전체 토글 4종 조회
- PUT    /admin/runtime-config           서비스 전체 토글 4종 일괄 저장
- GET    /admin/runtime-config/chat-model  관리자 설정 — RAG 채팅 모델 조회 + 허용 목록
- PUT    /admin/runtime-config/chat-model  관리자 설정 — RAG 채팅 모델 변경 (화이트리스트)
"""

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from redis.asyncio import Redis as AsyncRedis
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.deps.auth import require_admin
from api.src.deps.redis import get_redis_runtime
from api.src.middleware.audit_actions import (
    AUDIT_INBOX_PREVIEW_CONFIG_UPDATE,
    AUDIT_MODEL_PARAMS_EDIT,
    AUDIT_NOTICE_CREATE,
    AUDIT_NOTICE_DELETE,
    AUDIT_POPUP_CREATE,
    AUDIT_POPUP_DELETE,
    AUDIT_POPUP_IMAGE_UPLOAD,
    AUDIT_POPUP_TOGGLE,
    AUDIT_POPUP_UPDATE,
    AUDIT_RUNTIME_CONFIG_UPDATE,
    audit_action,
)
from api.src.models.base import get_session
from api.src.models.user import User
from api.src.schemas.admin.notice import (
    InboxPreviewConfigResponse,
    InboxPreviewConfigUpdateRequest,
    NoticeCreateRequest,
    NoticeDetailResponse,
    NoticeListResponse,
    NoticeRecipientsResponse,
)
from api.src.schemas.admin.popup import (
    PopupCreateRequest,
    PopupDetailResponse,
    PopupImageUploadResponse,
    PopupListResponse,
    PopupTogglePatchRequest,
    PopupToggleResponse,
    PopupUpdateRequest,
)
from api.src.schemas.admin.runtime_config import (
    ChatModelConfigResponse,
    ChatModelConfigUpdateRequest,
    RuntimeConfigResponse,
    RuntimeConfigUpdateRequest,
)
from api.src.services import notice_service, popup_service, runtime_config_service

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


@router.post(
    "/popups/image-upload",
    response_model=PopupImageUploadResponse,
    status_code=201,
)
@audit_action(AUDIT_POPUP_IMAGE_UPLOAD)
async def upload_popup_image(
    request: Request,
    file: UploadFile = File(...),
    admin: User = Depends(require_admin),
) -> PopupImageUploadResponse:
    """팝업 이미지 업로드 — Story 7.2 v2.

    PNG/JPG/WEBP, 5MB 이하. 응답의 image_url을 /admin/popups POST/PUT body.image_url에 사용.
    """
    return await popup_service.upload_popup_image(request, file, admin)


# ── 서비스 전체 토글 (Story 7.3/7.4 부분) ──────────────────────────────────────


@router.get("/runtime-config", response_model=RuntimeConfigResponse)
async def get_runtime_config(
    response: Response,
    admin: User = Depends(require_admin),
    redis_runtime: AsyncRedis = Depends(get_redis_runtime),
) -> RuntimeConfigResponse:
    """서비스 전체 토글 4종 조회 (구독 버튼 노출, 1일 무료 질문 한도, 답변 지연 ON/OFF·초)."""
    response.headers["Cache-Control"] = "no-store"
    return await runtime_config_service.get_runtime_config(redis_runtime)


@router.put("/runtime-config", response_model=RuntimeConfigResponse)
@audit_action(AUDIT_RUNTIME_CONFIG_UPDATE)
async def update_runtime_config(
    request: Request,
    body: RuntimeConfigUpdateRequest,
    admin: User = Depends(require_admin),
    redis_runtime: AsyncRedis = Depends(get_redis_runtime),
) -> RuntimeConfigResponse:
    """서비스 전체 토글 4종 일괄 저장 — diff_json은 audit middleware가 INSERT."""
    return await runtime_config_service.update_runtime_config(request, body, redis_runtime)


# ── 관리자 설정 페이지 — RAG 본 체인 채팅 모델 선택 ─────────────────────────────


@router.get("/runtime-config/chat-model", response_model=ChatModelConfigResponse)
async def get_chat_model_config(
    response: Response,
    admin: User = Depends(require_admin),
    redis_runtime: AsyncRedis = Depends(get_redis_runtime),
) -> ChatModelConfigResponse:
    """현재 선택된 채팅 모델 + 허용 모델 목록 조회 (드롭다운 옵션 채움용)."""
    response.headers["Cache-Control"] = "no-store"
    current = await runtime_config_service.get_chat_model(redis_runtime)
    return ChatModelConfigResponse(
        chat_model=current,
        allowed_models=list(runtime_config_service.ALLOWED_CHAT_MODELS),
        default_model=runtime_config_service.DEFAULT_CHAT_MODEL,
    )


@router.put("/runtime-config/chat-model", response_model=ChatModelConfigResponse)
@audit_action(AUDIT_MODEL_PARAMS_EDIT)
async def update_chat_model_config(
    request: Request,
    body: ChatModelConfigUpdateRequest,
    admin: User = Depends(require_admin),
    redis_runtime: AsyncRedis = Depends(get_redis_runtime),
) -> ChatModelConfigResponse:
    """채팅 모델 변경 — 화이트리스트 위반 시 400."""
    before = await runtime_config_service.get_chat_model(redis_runtime)
    try:
        after = await runtime_config_service.set_chat_model(redis_runtime, body.chat_model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    request.state.audit_target_type = "runtime_config"
    request.state.audit_diff = {
        "before": {"chat_model": before},
        "after": {"chat_model": after},
    }
    return ChatModelConfigResponse(
        chat_model=after,
        allowed_models=list(runtime_config_service.ALLOWED_CHAT_MODELS),
        default_model=runtime_config_service.DEFAULT_CHAT_MODEL,
    )


# ── Story 7.1 — 공지(쪽지) admin CRUD ─────────────────────────────────────────


@router.get("/notices", response_model=NoticeListResponse)
async def list_notices(
    response: Response,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> NoticeListResponse:
    """공지 목록 — 발행시각 desc. delivered_user_count 동봉."""
    response.headers["Cache-Control"] = "no-store"
    return await notice_service.list_notices(page, per_page, admin, db)


@router.get("/notices/{notice_id}", response_model=NoticeDetailResponse)
async def get_notice_detail(
    notice_id: int,
    response: Response,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> NoticeDetailResponse:
    """공지 단건 조회."""
    response.headers["Cache-Control"] = "no-store"
    return await notice_service.get_notice_detail(notice_id, admin, db)


@router.get(
    "/notices/{notice_id}/recipients",
    response_model=NoticeRecipientsResponse,
)
async def list_notice_recipients(
    notice_id: int,
    response: Response,
    status: str = Query("unread", pattern="^(read|unread)$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> NoticeRecipientsResponse:
    """쪽지 수신자 목록 — read/unread 분리 페이지네이션. 두 그룹의 카운트는 항상 동봉."""
    response.headers["Cache-Control"] = "no-store"
    return await notice_service.list_notice_recipients(
        notice_id, status, page, per_page, admin, db
    )


@router.post("/notices", response_model=NoticeDetailResponse, status_code=201)
@audit_action(AUDIT_NOTICE_CREATE)
async def create_notice(
    request: Request,
    body: NoticeCreateRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> NoticeDetailResponse:
    """공지 작성 + 즉시 발행 + target_segment fan-out → inbox_messages bulk INSERT."""
    return await notice_service.create_notice(request, body, admin, db)


@router.delete("/notices/{notice_id}", status_code=204)
@audit_action(AUDIT_NOTICE_DELETE)
async def delete_notice(
    request: Request,
    notice_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> None:
    """공지 hard delete — CASCADE로 매칭 user들의 inbox_messages도 회수."""
    await notice_service.delete_notice(request, notice_id, admin, db)


# ── 쪽지함 미리보기 동시 노출 최대 개수 (관리자 CS 페이지 컨트롤) ─────────────


@router.get("/inbox/preview-config", response_model=InboxPreviewConfigResponse)
async def get_inbox_preview_config(
    response: Response,
    admin: User = Depends(require_admin),
    redis_runtime: AsyncRedis = Depends(get_redis_runtime),
) -> InboxPreviewConfigResponse:
    """쪽지함 미리보기에 동시 노출되는 최대 카드 수."""
    response.headers["Cache-Control"] = "no-store"
    max_count = await runtime_config_service.get_inbox_preview_max_count(redis_runtime)
    return InboxPreviewConfigResponse(max_count=max_count)


@router.put("/inbox/preview-config", response_model=InboxPreviewConfigResponse)
@audit_action(AUDIT_INBOX_PREVIEW_CONFIG_UPDATE)
async def update_inbox_preview_config(
    request: Request,
    body: InboxPreviewConfigUpdateRequest,
    admin: User = Depends(require_admin),
    redis_runtime: AsyncRedis = Depends(get_redis_runtime),
) -> InboxPreviewConfigResponse:
    """쪽지함 미리보기 동시 노출 최대 개수 저장 (1..5)."""
    before = await runtime_config_service.get_inbox_preview_max_count(redis_runtime)
    after = await runtime_config_service.set_inbox_preview_max_count(
        redis_runtime, body.max_count
    )
    request.state.audit_target_type = "runtime_config"
    request.state.audit_diff = {
        "before": {"inbox_preview_max_count": before},
        "after": {"inbox_preview_max_count": after},
    }
    return InboxPreviewConfigResponse(max_count=after)
