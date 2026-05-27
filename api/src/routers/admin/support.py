"""Admin 고객문의 관리 라우터 — Story 4.5 + Story 9.3 확장.

GET   /api/v1/admin/support/inquiries              목록 (status_in/q/from/to + 페이지네이션) — 60/min
GET   /api/v1/admin/support/inquiries/{id}         상세 (recent_qa + replies) — 60/min
PATCH /api/v1/admin/support/inquiries/{id}         status / plain text reply (4.5 호환) / force — 30/min (Story 9.3 강화)
POST  /api/v1/admin/support/inquiries/{id}/reply   Tiptap reply_html — 30/min (Story 9.3 신규)
GET   /api/v1/admin/support/counts                 open inquiries + pending refunds — 60/min (Story 9.3 신규)

가드:
- require_admin (denvia_admin_session 쿠키 전용).
- 쓰기 액션은 30/min, 읽기 액션은 60/min (admin user_id 키, IP 폴백).
- audit_logs 는 PATCH/POST 의 경우 미들웨어가 응답 직후 자동 INSERT.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, Response, UploadFile
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.deps.auth import require_admin, require_admin_page
from api.src.middleware.audit_actions import (
    AUDIT_SUPPORT_REPLY_IMAGE_UPLOAD,
    audit_action,
)
from api.src.middleware.rate_limit import limiter
from api.src.models.base import get_session
from api.src.models.user import User
from api.src.schemas.admin.support import (
    InquiryDetailResponse,
    InquiryListResponse,
    InquiryReplyEditRequest,
    InquiryReplyRequest,
    InquiryReplyResponse,
    InquiryStatus,
    InquiryUpdateRequest,
    ReplyImageUploadResponse,
    SupportCountsResponse,
)
from api.src.services import admin_support_service
from api.src.utils.jwt import (
    JWTDecodeError,
    SessionExpired,
    decode_admin_session_jwt,
)

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/admin/support",
    tags=["admin-support"],
    dependencies=[Depends(require_admin_page("/admin/cs"))],
)

_ALLOWED_PER_PAGE = (50, 100, 200)
_VALID_STATUSES = {"open", "in_progress", "resolved"}
_KST = ZoneInfo("Asia/Seoul")


def _admin_user_id_key(request: Request) -> str:
    """레이트 리밋 키 — denvia_admin_session 쿠키에서 user_id 추출, 실패 시 IP 폴백."""
    cookie = request.cookies.get("denvia_admin_session")
    if not cookie:
        return get_remote_address(request)
    try:
        payload = decode_admin_session_jwt(cookie)
        return f"admin:{payload['sub']}"
    except (JWTDecodeError, SessionExpired, KeyError, Exception):
        return get_remote_address(request)


def _parse_status_in(value: str | None) -> set[str] | None:
    if not value:
        return None
    parts = {p.strip() for p in value.split(",") if p.strip()}
    if not parts:
        return None
    invalid = parts - _VALID_STATUSES
    if invalid:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_PARAM",
                "message": f"status_in 허용 값 외: {sorted(invalid)}",
            },
        )
    return parts


def _resolve_window(from_: date | None, to: date | None) -> tuple[date, date]:
    today = datetime.now(_KST).date()
    t = to or today
    f = from_ or (t - timedelta(days=30))
    if f > t:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_PARAM", "message": "from은 to보다 이전이어야 합니다."},
        )
    return f, t


@router.get("/inquiries", response_model=InquiryListResponse)
@limiter.limit("60/minute", key_func=_admin_user_id_key)
async def list_inquiries(
    request: Request,
    response: Response,
    status: InquiryStatus | None = Query(None, description="단건 status (4.5 하위 호환)"),
    status_in: str | None = Query(None, description="CSV 다중 status 필터"),
    q: str | None = Query(None, min_length=1, max_length=100),
    from_: date | None = Query(None, alias="from"),
    to: date | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> InquiryListResponse:
    """고객문의 목록 — Story 9.3: status_in 다중 + q ILIKE + from/to 범위."""
    if per_page not in _ALLOWED_PER_PAGE:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_PARAM",
                "message": "per_page는 50/100/200 중 하나여야 합니다.",
            },
        )

    status_set = _parse_status_in(status_in)
    f, t = _resolve_window(from_, to)

    result = await admin_support_service.list_inquiries(
        db,
        status=status,
        status_in=status_set,
        q=q,
        f=f,
        t=t,
        page=page,
        per_page=per_page,
    )
    response.headers["Cache-Control"] = "no-store"
    logger.info(
        "admin.support.inquiries.listed",
        actor_user_id=admin.id,
        status=status,
        status_in=sorted(status_set) if status_set else None,
        has_q=bool(q),
        from_=f.isoformat(),
        to=t.isoformat(),
        page=page,
        per_page=per_page,
        total=result.total,
        trace_id=str(getattr(request.state, "trace_id", "")),
    )
    return result


@router.get("/counts", response_model=SupportCountsResponse)
@limiter.limit("60/minute", key_func=_admin_user_id_key)
async def get_counts(
    request: Request,
    response: Response,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> SupportCountsResponse:
    """탭 카운트 — open inquiries + pending refunds 동시 반환."""
    open_inquiries = await admin_support_service.count_open_inquiries(db)
    # v1.1 환불 정책은 관리자 즉시 실행 단일 경로 — 승인 대기 큐 개념 없음.
    # `pending_refunds` 필드는 FE 호환을 위해 유지하되 항상 0을 반환한다.
    pending_refunds = 0
    response.headers["Cache-Control"] = "no-store"
    return SupportCountsResponse(
        open_inquiries=open_inquiries,
        pending_refunds=pending_refunds,
    )


@router.get("/inquiries/{inquiry_id}", response_model=InquiryDetailResponse)
@limiter.limit("60/minute", key_func=_admin_user_id_key)
async def get_inquiry(
    request: Request,
    response: Response,
    inquiry_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> InquiryDetailResponse:
    """고객문의 상세 — recent_qa(3건) + replies 이력 포함."""
    detail = await admin_support_service.get_inquiry(db, inquiry_id)
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "INQUIRY_NOT_FOUND", "message": "문의를 찾을 수 없습니다."},
        )
    response.headers["Cache-Control"] = "no-store"
    logger.info(
        "admin.support.inquiry.viewed",
        actor_user_id=admin.id,
        target_inquiry_id=inquiry_id,
        trace_id=str(getattr(request.state, "trace_id", "")),
    )
    return detail


@router.patch("/inquiries/{inquiry_id}", response_model=InquiryDetailResponse)
@limiter.limit("30/minute", key_func=_admin_user_id_key)
async def patch_inquiry(
    request: Request,
    inquiry_id: int,
    payload: InquiryUpdateRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> InquiryDetailResponse:
    """상태 변경 / plain text 답변 (Story 4.5 호환) + force 분기 (Story 9.3).

    audit_logs INSERT 는 미들웨어가 응답 직후 자동 처리.
    """
    detail = await admin_support_service.update_inquiry(
        request, db, inquiry_id, payload, admin_id=admin.id
    )
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "INQUIRY_NOT_FOUND", "message": "문의를 찾을 수 없습니다."},
        )
    logger.info(
        "admin.support.inquiry.patched",
        actor_user_id=admin.id,
        target_inquiry_id=inquiry_id,
        reply_sent=payload.reply_message is not None,
        status_changed_to=payload.status,
        force=payload.force,
        trace_id=str(getattr(request.state, "trace_id", "")),
    )
    return detail


@router.post(
    "/inquiries/{inquiry_id}/reply",
    response_model=InquiryReplyResponse,
    status_code=201,
)
@limiter.limit("30/minute", key_func=_admin_user_id_key)
async def reply_inquiry(
    request: Request,
    inquiry_id: int,
    payload: InquiryReplyRequest,
    background_tasks: BackgroundTasks,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> InquiryReplyResponse:
    """Tiptap reply_html 답변 — Story 9.3 신규.

    응답 후 fire-and-forget:
    - 알림톡 support.reply_received
    """
    detail = await admin_support_service.create_reply(
        request, db, inquiry_id, payload, admin_id=admin.id
    )
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "INQUIRY_NOT_FOUND", "message": "문의를 찾을 수 없습니다."},
        )

    user_id = getattr(request.state, "support_reply_user_id", None)
    reply_id = getattr(request.state, "support_reply_id", None)
    inquiry_subject = getattr(request.state, "support_reply_inquiry_subject", "")

    if user_id is not None and reply_id is not None:
        background_tasks.add_task(
            _notify_inquiry_reply,
            user_id=user_id,
            inquiry_id=inquiry_id,
            reply_id=reply_id,
            inquiry_subject=inquiry_subject,
        )

    logger.info(
        "admin.support.reply.created",
        actor_user_id=admin.id,
        target_inquiry_id=inquiry_id,
        reply_id=reply_id,
        new_status=payload.new_status or "resolved",
        trace_id=str(getattr(request.state, "trace_id", "")),
    )
    return InquiryReplyResponse(inquiry=detail)


@router.patch(
    "/inquiries/{inquiry_id}/replies/{reply_id}",
    response_model=InquiryDetailResponse,
)
@limiter.limit("30/minute", key_func=_admin_user_id_key)
async def edit_reply(
    request: Request,
    inquiry_id: int,
    reply_id: int,
    payload: InquiryReplyEditRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> InquiryDetailResponse:
    """답변 본문 수정 — inquiry_replies + 매칭 inbox 동기 갱신.

    권한: 모든 admin. audit_logs는 미들웨어가 응답 직후 자동 INSERT.
    """
    detail = await admin_support_service.update_reply(
        request, db, inquiry_id, reply_id, payload, admin_id=admin.id
    )
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "INQUIRY_REPLY_NOT_FOUND",
                "message": "답변을 찾을 수 없습니다.",
            },
        )
    logger.info(
        "admin.support.reply.edited",
        actor_user_id=admin.id,
        target_inquiry_id=inquiry_id,
        target_reply_id=reply_id,
        trace_id=str(getattr(request.state, "trace_id", "")),
    )
    return detail


@router.delete(
    "/inquiries/{inquiry_id}/replies/{reply_id}",
    response_model=InquiryDetailResponse,
)
@limiter.limit("30/minute", key_func=_admin_user_id_key)
async def remove_reply(
    request: Request,
    inquiry_id: int,
    reply_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> InquiryDetailResponse:
    """답변 삭제 — inquiry_replies + 매칭 inbox row 동기 삭제.

    삭제 후 남은 답변이 0건이고 status='resolved'이면
    자동으로 status='open' + resolved_at=NULL로 되돌린다
    (답변 없는데 "답변완료" 표시 모순 차단).
    """
    detail = await admin_support_service.delete_reply(
        request, db, inquiry_id, reply_id, admin_id=admin.id
    )
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "INQUIRY_REPLY_NOT_FOUND",
                "message": "답변을 찾을 수 없습니다.",
            },
        )
    logger.info(
        "admin.support.reply.deleted",
        actor_user_id=admin.id,
        target_inquiry_id=inquiry_id,
        target_reply_id=reply_id,
        trace_id=str(getattr(request.state, "trace_id", "")),
    )
    return detail


@router.post(
    "/reply-image-upload",
    response_model=ReplyImageUploadResponse,
    status_code=201,
)
@limiter.limit("30/minute", key_func=_admin_user_id_key)
@audit_action(AUDIT_SUPPORT_REPLY_IMAGE_UPLOAD)
async def upload_reply_image(
    request: Request,
    file: UploadFile = File(...),
    admin: User = Depends(require_admin),
) -> ReplyImageUploadResponse:
    """CS 답변 본문 에디터(Tiptap) 이미지 업로드.

    PNG·JPG·WEBP, 5MB 이하. 응답의 image_url 을 본문에 <img src="..."> 로 삽입.
    """
    return await admin_support_service.upload_reply_image(request, file, admin.id)


async def _notify_inquiry_reply(
    *, user_id: int, inquiry_id: int, reply_id: int, inquiry_subject: str
) -> None:
    """fire-and-forget 알림톡 — support.reply_received."""
    try:
        from api.src.integrations.messaging.notification_service import (
            get_notification_service,
        )
        from api.src.models.base import async_session_factory
        from sqlalchemy import select

        async with async_session_factory() as db:
            user = (
                await db.execute(
                    select(User).where(User.id == user_id, User.withdrawn_at.is_(None))
                )
            ).scalar_one_or_none()
        if user is None:
            return
        svc = get_notification_service()
        await svc.send(
            user_id=user_id,
            phone=user.phone or "",
            template_code="support.reply_received",
            variables={"inquiry_subject": inquiry_subject},
            idempotency_key=f"support:{inquiry_id}:reply:{reply_id}",
        )
    except Exception:
        logger.warning(
            "admin.support.reply.notify_failed",
            user_id=user_id,
            inquiry_id=inquiry_id,
            reply_id=reply_id,
        )


__all__ = ["router"]
