"""Story 6.1 — Admin 사용자 통합 검색·상세 라우터.

GET /admin/users          — 통합 검색 + 필터 + 페이지네이션
GET /admin/users/{user_id} — 단건 상세 (Drawer 4 섹션)

특징:
- require_admin 가드, denvia_admin_session 쿠키 전용.
- slowapi 60/min 관리자 user_id 키 — IP 폴백.
- structlog admin.users.searched/viewed PII 마스킹(q 원문 미기록).
- GET 전용이므로 audit_logs INSERT 자동 제외 (audit middleware는 WRITE 메서드만).
"""

from __future__ import annotations

from datetime import date
from typing import Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.deps.auth import require_admin
from api.src.middleware.rate_limit import limiter
from api.src.models.base import get_session
from api.src.models.user import User
from api.src.schemas.admin.user_activity import (
    UserAnomalyEventListResponse,
    UserInquiryListResponse,
    UserQALogDetail,
    UserQALogListResponse,
)
from api.src.schemas.admin.users import (
    UserDetailResponse,
    UserPermissionUpdateRequest,
    UserSearchItem,
    UserSearchListResponse,
)
from api.src.services import (
    admin_user_activity_service,
    admin_user_service,
    user_service,
)
from api.src.utils.jwt import (
    JWTDecodeError,
    SessionExpired,
    decode_admin_session_jwt,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin/users", tags=["admin-users"])


async def _require_user_exists(db: AsyncSession, user_id: int) -> None:
    """대상 사용자 존재 검증 — 404 ADMIN_USER_NOT_FOUND."""
    exists = (
        await db.execute(select(User.id).where(User.id == user_id))
    ).scalar_one_or_none()
    if exists is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "ADMIN_USER_NOT_FOUND",
                "message": "사용자를 찾을 수 없습니다.",
            },
        )


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


@router.get("", response_model=UserSearchListResponse)
@limiter.limit("60/minute", key_func=_admin_user_id_key)
async def list_users(
    request: Request,
    q: str | None = Query(None, min_length=1, max_length=100),
    segment: Literal["doctor", "hygienist", "student_other"] | None = Query(None),
    subscription_status: Literal["free", "pro", "blocked"] | None = Query(None),
    blocked: bool | None = Query(None),
    created_from: date | None = Query(
        None, description="가입일 시작(KST, YYYY-MM-DD). 해당일 00:00부터 포함."
    ),
    created_to: date | None = Query(
        None, description="가입일 종료(KST, YYYY-MM-DD). 해당일 23:59까지 포함."
    ),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> UserSearchListResponse:
    """관리자용 사용자 통합 검색 (GET이므로 audit_logs INSERT 없음)."""
    if created_from is not None and created_to is not None and created_from > created_to:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "ADMIN_USERS_INVALID_DATE_RANGE",
                "message": "가입일 시작이 종료보다 늦을 수 없습니다.",
            },
        )

    result = await admin_user_service.search_users(
        db,
        q=q,
        segment=segment,
        subscription_status=subscription_status,
        blocked=blocked,
        created_from=created_from,
        created_to=created_to,
        page=page,
        per_page=per_page,
    )

    # PII 마스킹 — q 원문은 절대 로그에 포함하지 않음 (NFR-S2/NFR-O3)
    logger.info(
        "admin.users.searched",
        actor_user_id=admin.id,
        q_length=len(q or ""),
        q_has_email_at=("@" in (q or "")),
        filters={
            "segment": segment,
            "subscription_status": subscription_status,
            "blocked": blocked,
            "created_from": created_from.isoformat() if created_from else None,
            "created_to": created_to.isoformat() if created_to else None,
        },
        page=page,
        per_page=per_page,
        total=result.total,
        trace_id=str(getattr(request.state, "trace_id", "")),
    )

    return result


@router.get("/{user_id}", response_model=UserDetailResponse)
@limiter.limit("60/minute", key_func=_admin_user_id_key)
async def get_user(
    request: Request,
    user_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> UserDetailResponse:
    """관리자용 사용자 상세 — Drawer 4 섹션."""
    detail = await admin_user_service.get_user_detail(db, user_id)

    logger.info(
        "admin.users.viewed",
        actor_user_id=admin.id,
        target_user_id=user_id,
        trace_id=str(getattr(request.state, "trace_id", "")),
    )

    return detail


@router.get("/{user_id}/qa-logs", response_model=UserQALogListResponse)
@limiter.limit("60/minute", key_func=_admin_user_id_key)
async def list_user_qa_logs(
    request: Request,
    user_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> UserQALogListResponse:
    """관리자용 사용자 질의 로그 — 사용자 활동 로그 페이지의 질의 탭."""
    await _require_user_exists(db, user_id)
    result = await admin_user_activity_service.list_user_qa_logs(
        db, user_id=user_id, page=page, per_page=per_page
    )
    logger.info(
        "admin.users.activity.qa_logs.viewed",
        actor_user_id=admin.id,
        target_user_id=user_id,
        page=page,
        per_page=per_page,
        total=result.total,
        trace_id=str(getattr(request.state, "trace_id", "")),
    )
    return result


@router.get(
    "/{user_id}/qa-logs/{qa_log_id}",
    response_model=UserQALogDetail,
)
@limiter.limit("60/minute", key_func=_admin_user_id_key)
async def get_user_qa_log_detail(
    request: Request,
    user_id: int,
    qa_log_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> UserQALogDetail:
    """관리자용 단건 질의 상세 — '상세보기' 버튼.

    응답에 ``normalized_query``, ``retrieved_docs`` 포함. SSE/사용자 응답에는
    절대 노출되지 않는 데이터로, 관리자 감사 목적 한정 (ADR-0002 보강).
    본 마이그레이션(0038) 이전 행은 두 필드 모두 NULL/빈 리스트.
    """
    await _require_user_exists(db, user_id)
    detail = await admin_user_activity_service.get_user_qa_log_detail(
        db, user_id=user_id, qa_log_id=qa_log_id
    )
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "ADMIN_QA_LOG_NOT_FOUND",
                "message": "질의 기록을 찾을 수 없습니다.",
            },
        )
    logger.info(
        "admin.users.activity.qa_log.detail_viewed",
        actor_user_id=admin.id,
        target_user_id=user_id,
        qa_log_id=qa_log_id,
        trace_id=str(getattr(request.state, "trace_id", "")),
    )
    return detail


@router.get("/{user_id}/inquiries", response_model=UserInquiryListResponse)
@limiter.limit("60/minute", key_func=_admin_user_id_key)
async def list_user_inquiries(
    request: Request,
    user_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> UserInquiryListResponse:
    """관리자용 사용자 문의 내역 — 사용자 활동 로그 페이지의 문의 탭."""
    await _require_user_exists(db, user_id)
    result = await admin_user_activity_service.list_user_inquiries(
        db, user_id=user_id, page=page, per_page=per_page
    )
    logger.info(
        "admin.users.activity.inquiries.viewed",
        actor_user_id=admin.id,
        target_user_id=user_id,
        page=page,
        per_page=per_page,
        total=result.total,
        trace_id=str(getattr(request.state, "trace_id", "")),
    )
    return result


@router.get(
    "/{user_id}/anomaly-events", response_model=UserAnomalyEventListResponse
)
@limiter.limit("60/minute", key_func=_admin_user_id_key)
async def list_user_anomaly_events(
    request: Request,
    user_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> UserAnomalyEventListResponse:
    """관리자용 사용자 이상 이벤트 — 사용자 활동 로그 페이지의 이상 이벤트 탭."""
    await _require_user_exists(db, user_id)
    result = await admin_user_activity_service.list_user_anomaly_events(
        db, user_id=user_id, page=page, per_page=per_page
    )
    logger.info(
        "admin.users.activity.anomaly_events.viewed",
        actor_user_id=admin.id,
        target_user_id=user_id,
        page=page,
        per_page=per_page,
        total=result.total,
        trace_id=str(getattr(request.state, "trace_id", "")),
    )
    return result


@router.patch("/{user_id}", response_model=UserSearchItem)
@limiter.limit("60/minute", key_func=_admin_user_id_key)
async def patch_user(
    request: Request,
    user_id: int,
    payload: UserPermissionUpdateRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> UserSearchItem:
    """Story 6.2 — 관리자용 사용자 권한·한도·차단 통합 편집.

    audit_logs INSERT는 AuditMiddleware가 응답 직후 자동 처리한다.
    request.state.audit_action / audit_target_* / audit_diff 는 user_service에서 설정.
    """
    item = await user_service.update_permission(request, user_id, payload, db)

    logger.info(
        "admin.users.permission_edited",
        actor_user_id=admin.id,
        target_user_id=user_id,
        # 변경 필드 키만 로그 — 값 자체는 PII 가능성 있어 제외
        changed_fields=list(payload.model_dump(exclude_none=True).keys()),
        trace_id=str(getattr(request.state, "trace_id", "")),
    )

    return item


__all__ = ["router"]
