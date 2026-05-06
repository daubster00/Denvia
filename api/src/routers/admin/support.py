"""Admin 고객문의 관리 라우터 — Story 9.3 계열.

GET   /api/v1/admin/support/inquiries           목록 (status 필터 + 페이지네이션)
GET   /api/v1/admin/support/inquiries/{id}      상세
PATCH /api/v1/admin/support/inquiries/{id}      상태 변경 / 답변 등록

가드:
- require_admin (denvia_admin_session 쿠키 전용).
- 60/min slowapi 레이트 리밋 (admin user_id 키, IP 폴백).
- audit_logs 는 PATCH 의 경우 미들웨어가 응답 직후 자동 INSERT.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.deps.auth import require_admin
from api.src.middleware.rate_limit import limiter
from api.src.models.base import get_session
from api.src.models.user import User
from api.src.schemas.admin.support import (
    InquiryDetailResponse,
    InquiryListResponse,
    InquiryStatus,
    InquiryUpdateRequest,
)
from api.src.services import admin_support_service
from api.src.utils.jwt import (
    JWTDecodeError,
    SessionExpired,
    decode_admin_session_jwt,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin/support", tags=["admin-support"])


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


@router.get("/inquiries", response_model=InquiryListResponse)
@limiter.limit("60/minute", key_func=_admin_user_id_key)
async def list_inquiries(
    request: Request,
    status: InquiryStatus | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> InquiryListResponse:
    """고객문의 목록 — GET 이므로 audit_logs INSERT 없음."""
    result = await admin_support_service.list_inquiries(
        db, status=status, page=page, per_page=per_page
    )
    logger.info(
        "admin.support.inquiries.listed",
        actor_user_id=admin.id,
        filters={"status": status},
        page=page,
        per_page=per_page,
        total=result.total,
        trace_id=str(getattr(request.state, "trace_id", "")),
    )
    return result


@router.get("/inquiries/{inquiry_id}", response_model=InquiryDetailResponse)
@limiter.limit("60/minute", key_func=_admin_user_id_key)
async def get_inquiry(
    request: Request,
    inquiry_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> InquiryDetailResponse:
    """고객문의 상세."""
    detail = await admin_support_service.get_inquiry(db, inquiry_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="inquiry not found")
    logger.info(
        "admin.support.inquiries.viewed",
        actor_user_id=admin.id,
        target_inquiry_id=inquiry_id,
        trace_id=str(getattr(request.state, "trace_id", "")),
    )
    return detail


@router.patch("/inquiries/{inquiry_id}", response_model=InquiryDetailResponse)
@limiter.limit("60/minute", key_func=_admin_user_id_key)
async def patch_inquiry(
    request: Request,
    inquiry_id: int,
    payload: InquiryUpdateRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> InquiryDetailResponse:
    """상태 변경 / 답변 등록.

    reply_message 지정 시 사용자 inbox 알림 1건 INSERT + status='resolved' 자동 마감.
    audit_logs INSERT 는 미들웨어가 응답 직후 자동 처리.
    """
    detail = await admin_support_service.update_inquiry(request, db, inquiry_id, payload)
    if detail is None:
        raise HTTPException(status_code=404, detail="inquiry not found")
    logger.info(
        "admin.support.inquiries.patched",
        actor_user_id=admin.id,
        target_inquiry_id=inquiry_id,
        reply_sent=payload.reply_message is not None,
        status_changed_to=payload.status,
        trace_id=str(getattr(request.state, "trace_id", "")),
    )
    return detail


__all__ = ["router"]
