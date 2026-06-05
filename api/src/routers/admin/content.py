"""콘텐츠 관리 라우터 — Story 7.1 공지(쪽지) + 7.2 v2 팝업 admin CRUD + 7.3/7.4 토글.

엔드포인트:
- GET    /admin/popups                   목록 페이지네이션
- GET    /admin/popups/{popup_id}        단건 조회 (편집 prefill)
- POST   /admin/popups                   신규 생성
- PUT    /admin/popups/{popup_id}        전체 필드 교체 (편집 모달 저장)
- PATCH  /admin/popups/{popup_id}        is_active 즉시 토글 (목록 행)
- DELETE /admin/popups/{popup_id}        soft delete
- POST   /admin/popups/image-upload      이미지 업로드 (Story 7.2 v2)
- GET    /admin/notices                  공지(쪽지) 목록 — broadcast + admin_dm UNION
- GET    /admin/notices/{notice_id}      공지 단건 조회 (broadcast)
- GET    /admin/notices/{notice_id}/recipients  수신자 목록 — read/unread 분리 페이지네이션
- POST   /admin/notices                  공지 작성+즉시 발행 (target_segment fan-out)
- DELETE /admin/notices/{notice_id}      공지 hard delete (CASCADE로 inbox 회수)
- GET    /admin/notices/dm/{message_id}  관리자 1:1 쪽지 단건 조회
- DELETE /admin/notices/dm/{message_id}  관리자 1:1 쪽지 hard delete (사용자 inbox에서 회수)
- GET    /admin/inbox/preview-config     쪽지함 미리보기 동시 노출 최대 개수 조회
- PUT    /admin/inbox/preview-config     쪽지함 미리보기 동시 노출 최대 개수 저장
- GET    /admin/runtime-config           서비스 전체 토글 4종 조회
- PUT    /admin/runtime-config           서비스 전체 토글 4종 일괄 저장
- GET    /admin/runtime-config/chat-model  관리자 설정 — RAG 채팅 모델 조회 + 허용 목록
- PUT    /admin/runtime-config/chat-model  관리자 설정 — RAG 채팅 모델 변경 (화이트리스트)
- GET    /admin/runtime-config/forex       USD→KRW 환율 + 자동 갱신 메타 (read-only)
- GET    /admin/runtime-config/toss-pg     관리자 설정 — 토스 PG 모드 + 4개 키 마스킹 조회
- PUT    /admin/runtime-config/toss-pg     관리자 설정 — 토스 PG 모드 토글 + 키 부분 업데이트
"""

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from redis.asyncio import Redis as AsyncRedis
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.deps.auth import require_admin, require_admin_page
from api.src.deps.redis import get_redis_runtime
from api.src.middleware.audit_actions import (
    AUDIT_ADMIN_DM_DELETE,
    AUDIT_ANOMALY_THRESHOLDS_UPDATE,
    AUDIT_ANOMALY_THROTTLE_CONFIG_UPDATE,
    AUDIT_INBOX_PREVIEW_CONFIG_UPDATE,
    AUDIT_LOGIN_BRUTE_THRESHOLD_UPDATE,
    AUDIT_MODEL_PARAMS_EDIT,
    AUDIT_NOTICE_CREATE,
    AUDIT_NOTICE_DELETE,
    AUDIT_PG_CONFIG_UPDATE,
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
    AdminDMDetailResponse,
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
    AnomalyThresholdsConfigResponse,
    AnomalyThresholdsConfigUpdateRequest,
    AnomalyThrottleConfigResponse,
    AnomalyThrottleConfigUpdateRequest,
    ChatModelConfigResponse,
    ChatModelConfigUpdateRequest,
    ForexConfigResponse,
    LoginBruteThresholdConfigResponse,
    LoginBruteThresholdConfigUpdateRequest,
    RuntimeConfigResponse,
    RuntimeConfigUpdateRequest,
    TossPgConfigResponse,
    TossPgConfigUpdateRequest,
    TossPgKeyView,
)
from api.src.services import notice_service, pg_config_service, popup_service, runtime_config_service

router = APIRouter(prefix="/admin", tags=["admin-content"])
# NOTE: content.py 는 prefix가 `/admin`이고 `/admin/runtime-config*` 같이 여러 사이드바 페이지
# (콘텐츠·설정·대시보드)가 공유하는 엔드포인트를 다수 포함한다. 라우터-레벨에서 한 페이지로
# 묶으면 일부 등급에서 정상 사용이 막힌다. 본 라우터의 페이지 단위 차단은 프론트 사이드바/
# URL 가드(admin/layout.tsx)에서 수행한다 — 백엔드는 require_admin 단일 가드 유지.


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


@router.get(
    "/runtime-config/anomaly-throttle", response_model=AnomalyThrottleConfigResponse
)
async def get_anomaly_throttle_config(
    response: Response,
    admin: User = Depends(require_admin),
    redis_runtime: AsyncRedis = Depends(get_redis_runtime),
) -> AnomalyThrottleConfigResponse:
    """이상 질문 패턴 throttle 설정 조회 — enabled + 무료/유료 지연 초.

    탐지 규칙: 답변 출력 완료 시각 기준 3초 이내 후속 질문 연속 3회.
    적용 대상은 사용자 ``users.anomaly_throttled_at``. 본 엔드포인트는 전역 설정만.
    """
    response.headers["Cache-Control"] = "no-store"
    return await runtime_config_service.get_anomaly_throttle_config(redis_runtime)


@router.put(
    "/runtime-config/anomaly-throttle", response_model=AnomalyThrottleConfigResponse
)
@audit_action(AUDIT_ANOMALY_THROTTLE_CONFIG_UPDATE)
async def update_anomaly_throttle_config(
    request: Request,
    body: AnomalyThrottleConfigUpdateRequest,
    admin: User = Depends(require_admin),
    redis_runtime: AsyncRedis = Depends(get_redis_runtime),
) -> AnomalyThrottleConfigResponse:
    """throttle 설정 일괄 저장 — diff_json 은 audit middleware 가 INSERT."""
    return await runtime_config_service.update_anomaly_throttle_config(
        request, body, redis_runtime
    )


@router.get(
    "/runtime-config/login-brute-threshold",
    response_model=LoginBruteThresholdConfigResponse,
)
async def get_login_brute_threshold_config(
    response: Response,
    admin: User = Depends(require_admin),
    redis_runtime: AsyncRedis = Depends(get_redis_runtime),
) -> LoginBruteThresholdConfigResponse:
    """로그인 실패 이상탐지 기준 횟수 조회 — 현재값 + bounds.

    이 임계값에 도달하면 ``auth_service.login_user`` 가
    anomaly_events INSERT(stage=1) + 동일 이메일 10분 lockout 을 동시 트리거한다.
    """
    response.headers["Cache-Control"] = "no-store"
    return await runtime_config_service.get_login_brute_threshold_config(
        redis_runtime
    )


@router.put(
    "/runtime-config/login-brute-threshold",
    response_model=LoginBruteThresholdConfigResponse,
)
@audit_action(AUDIT_LOGIN_BRUTE_THRESHOLD_UPDATE)
async def update_login_brute_threshold_config(
    request: Request,
    body: LoginBruteThresholdConfigUpdateRequest,
    admin: User = Depends(require_admin),
    redis_runtime: AsyncRedis = Depends(get_redis_runtime),
) -> LoginBruteThresholdConfigResponse:
    """로그인 실패 이상탐지 기준 횟수 저장 (1~20). diff_json 은 audit middleware 가 INSERT."""
    return await runtime_config_service.update_login_brute_threshold_config(
        request, body, redis_runtime
    )


@router.get(
    "/runtime-config/anomaly-thresholds",
    response_model=AnomalyThresholdsConfigResponse,
)
async def get_anomaly_thresholds_config(
    response: Response,
    admin: User = Depends(require_admin),
    redis_runtime: AsyncRedis = Depends(get_redis_runtime),
) -> AnomalyThresholdsConfigResponse:
    """이상탐지 통합 임계값 조회 — 6 카테고리 11 항목.

    /admin/anomaly/thresholds 페이지 prefill 전용. 본 응답은 각 항목의 현재값과 함께
    bounds(min/max/default)도 동봉해 프론트 폼이 동적으로 안내한다.
    """
    response.headers["Cache-Control"] = "no-store"
    return await runtime_config_service.get_anomaly_thresholds_config(redis_runtime)


@router.put(
    "/runtime-config/anomaly-thresholds",
    response_model=AnomalyThresholdsConfigResponse,
)
@audit_action(AUDIT_ANOMALY_THRESHOLDS_UPDATE)
async def update_anomaly_thresholds_config(
    request: Request,
    body: AnomalyThresholdsConfigUpdateRequest,
    admin: User = Depends(require_admin),
    redis_runtime: AsyncRedis = Depends(get_redis_runtime),
) -> AnomalyThresholdsConfigResponse:
    """이상탐지 통합 임계값 일괄 저장 — 서버에서 추가 clamp 후 SET. 즉시 반영(배포 불필요)."""
    return await runtime_config_service.update_anomaly_thresholds_config(
        request, body, redis_runtime
    )


@router.get("/runtime-config/forex", response_model=ForexConfigResponse)
async def get_forex_config(
    response: Response,
    admin: User = Depends(require_admin),
    redis_runtime: AsyncRedis = Depends(get_redis_runtime),
) -> ForexConfigResponse:
    """USD→KRW 환율 + 자동 갱신 메타 조회 (read-only).

    자동 갱신은 Celery beat ``forex_tasks.update_usd_krw`` 가 매일 09:00 KST 수행.
    PUT/PATCH 미제공 — "자동이 항상 덮어쓰기" 정책. 운영자 직개입 필요 시 redis-cli SET.
    """
    response.headers["Cache-Control"] = "no-store"
    snap = await runtime_config_service.get_usd_to_krw_snapshot(redis_runtime)
    source = "auto" if snap.updated_at is not None else "fallback"
    return ForexConfigResponse(
        rate=snap.rate,
        default_rate=runtime_config_service.DEFAULT_USD_TO_KRW,
        updated_at=snap.updated_at,
        search_date=snap.search_date,
        source=source,
    )


# ── 관리자 설정 → 결제(PG) — 토스 모드 + 4개 키 관리 ───────────────────────────


def _snapshot_to_response(snap: pg_config_service.TossPgSnapshot) -> TossPgConfigResponse:
    def view(v: pg_config_service.TossPgKeyView) -> TossPgKeyView:
        return TossPgKeyView(masked=v.masked, has_value=v.has_value)

    return TossPgConfigResponse(
        mode=snap.mode,
        test_client=view(snap.test_client),
        test_secret=view(snap.test_secret),
        live_client=view(snap.live_client),
        live_secret=view(snap.live_secret),
    )


@router.get("/runtime-config/toss-pg", response_model=TossPgConfigResponse)
async def get_toss_pg_config(
    response: Response,
    admin: User = Depends(require_admin),
    redis_runtime: AsyncRedis = Depends(get_redis_runtime),
) -> TossPgConfigResponse:
    """토스 PG 설정 조회 — 모드(test|live) + 4개 키 마스킹 묶음.

    secret 키 원본은 절대 응답에 실리지 않는다. 관리자 UI 는 "수정" 버튼을 눌러
    빈 입력창에 새 값을 직접 다시 입력하는 흐름이다.
    """
    response.headers["Cache-Control"] = "no-store"
    snap = await pg_config_service.get_snapshot(redis_runtime)
    return _snapshot_to_response(snap)


@router.put("/runtime-config/toss-pg", response_model=TossPgConfigResponse)
@audit_action(AUDIT_PG_CONFIG_UPDATE)
async def update_toss_pg_config(
    request: Request,
    body: TossPgConfigUpdateRequest,
    admin: User = Depends(require_admin),
    redis_runtime: AsyncRedis = Depends(get_redis_runtime),
) -> TossPgConfigResponse:
    """토스 PG 모드 토글 + 키 부분 업데이트.

    빈 문자열/공백/None 인 키 필드는 무시(미변경). 모드만 바꾸려면 키 필드는
    모두 비워둔다. audit diff_json 에는 마스킹 전후 상태만 기록한다(원본 금지).
    """
    before = await pg_config_service.get_snapshot(redis_runtime)

    if body.mode is not None:
        try:
            await pg_config_service.set_mode(redis_runtime, body.mode)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    updates = (
        (pg_config_service.KEY_TEST_CLIENT, body.test_client_key),
        (pg_config_service.KEY_TEST_SECRET, body.test_secret_key),
        (pg_config_service.KEY_LIVE_CLIENT, body.live_client_key),
        (pg_config_service.KEY_LIVE_SECRET, body.live_secret_key),
    )
    for key, value in updates:
        if value is None:
            continue
        stripped = value.strip()
        if not stripped:
            continue
        await pg_config_service.set_key(redis_runtime, key, stripped)

    after = await pg_config_service.get_snapshot(redis_runtime)

    request.state.audit_target_type = "pg_config"
    request.state.audit_diff = {
        "before": {
            "mode": before.mode,
            "test_client_has_value": before.test_client.has_value,
            "test_secret_has_value": before.test_secret.has_value,
            "live_client_has_value": before.live_client.has_value,
            "live_secret_has_value": before.live_secret.has_value,
        },
        "after": {
            "mode": after.mode,
            "test_client_has_value": after.test_client.has_value,
            "test_secret_has_value": after.test_secret.has_value,
            "live_client_has_value": after.live_client.has_value,
            "live_secret_has_value": after.live_secret.has_value,
        },
    }

    return _snapshot_to_response(after)


# ── Story 7.1 — 공지(쪽지) admin CRUD ─────────────────────────────────────────


@router.get("/notices", response_model=NoticeListResponse)
async def list_notices(
    response: Response,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    target_filter: str = Query("all", pattern="^(all|broadcast|dm)$"),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> NoticeListResponse:
    """공지/개별 쪽지 통합 목록 — 발행시각 desc. broadcast(notices) + admin_dm UNION."""
    response.headers["Cache-Control"] = "no-store"
    return await notice_service.list_notices(
        page, per_page, admin, db, target_filter=target_filter
    )


@router.get("/notices/dm/{message_id}", response_model=AdminDMDetailResponse)
async def get_admin_dm_detail(
    message_id: int,
    response: Response,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> AdminDMDetailResponse:
    """관리자 → 특정 사용자 1:1 쪽지 단건 조회."""
    response.headers["Cache-Control"] = "no-store"
    return await notice_service.get_admin_dm_detail(message_id, admin, db)


@router.delete("/notices/dm/{message_id}", status_code=204)
@audit_action(AUDIT_ADMIN_DM_DELETE)
async def delete_admin_dm(
    request: Request,
    message_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> None:
    """관리자 1:1 쪽지 hard delete — 사용자 inbox에서 즉시 회수."""
    await notice_service.delete_admin_dm(request, message_id, admin, db)


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
