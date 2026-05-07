"""Admin 수동 환불 검토 라우터 — Story 9.3 (A-503).

GET   /api/v1/admin/refunds                     manual_refund_queue 목록 — 60/min
POST  /api/v1/admin/refunds/{queue_id}/approve  PG refund 호출 + 9 테이블 전이 — 30/min
POST  /api/v1/admin/refunds/{queue_id}/deny     payment 원복 + 알림 — 30/min

가드:
- require_admin (denvia_admin_session 쿠키 전용).
- 응답 후 fire-and-forget: 알림톡(승인/거부) + Redis admin:events publish.
- audit_logs 는 미들웨어가 응답 직후 자동 INSERT.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.deps.auth import require_admin
from api.src.middleware.rate_limit import limiter
from api.src.models.base import get_session
from api.src.models.user import User
from api.src.schemas.admin.refunds import (
    RefundActionRequest,
    RefundActionResponse,
    RefundQueueListResponse,
)
from api.src.services import admin_refund_service
from api.src.utils.jwt import (
    JWTDecodeError,
    SessionExpired,
    decode_admin_session_jwt,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin/refunds", tags=["admin-refunds"])

_ALLOWED_PER_PAGE = (50, 100, 200)
_VALID_QUEUE_STATUS = {"pending", "approved", "denied"}
_KST = ZoneInfo("Asia/Seoul")


def _admin_user_id_key(request: Request) -> str:
    cookie = request.cookies.get("denvia_admin_session")
    if not cookie:
        return get_remote_address(request)
    try:
        payload = decode_admin_session_jwt(cookie)
        return f"admin:{payload['sub']}"
    except (JWTDecodeError, SessionExpired, KeyError, Exception):
        return get_remote_address(request)


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


@router.get("", response_model=RefundQueueListResponse)
@limiter.limit("60/minute", key_func=_admin_user_id_key)
async def list_refunds(
    request: Request,
    response: Response,
    status: str = Query("pending"),
    from_: date | None = Query(None, alias="from"),
    to: date | None = Query(None),
    q: str | None = Query(None, min_length=1, max_length=100),
    page: int = Query(1, ge=1),
    per_page: int = Query(50),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> RefundQueueListResponse:
    """수동 환불 큐 목록."""
    if per_page not in _ALLOWED_PER_PAGE:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_PARAM",
                "message": "per_page는 50/100/200 중 하나여야 합니다.",
            },
        )
    if status not in _VALID_QUEUE_STATUS:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_PARAM",
                "message": f"status는 {sorted(_VALID_QUEUE_STATUS)} 중 하나여야 합니다.",
            },
        )

    f, t = _resolve_window(from_, to)
    result = await admin_refund_service.list_queue(
        db,
        status=status,
        f=f,
        t=t,
        q=q,
        page=page,
        per_page=per_page,
    )
    response.headers["Cache-Control"] = "no-store"
    logger.info(
        "admin.refunds.listed",
        actor_user_id=admin.id,
        status=status,
        from_=f.isoformat(),
        to=t.isoformat(),
        has_q=bool(q),
        page=page,
        per_page=per_page,
        total=result.total,
        trace_id=str(getattr(request.state, "trace_id", "")),
    )
    return result


@router.post("/{queue_id}/approve", response_model=RefundActionResponse)
@limiter.limit("30/minute", key_func=_admin_user_id_key)
async def approve_refund(
    request: Request,
    queue_id: int,
    payload: RefundActionRequest,
    background_tasks: BackgroundTasks,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> RefundActionResponse:
    """수동 환불 승인 — PG 호출 후 9 테이블 동시 전이.

    응답 후 fire-and-forget:
    - 알림톡 billing.refund_success
    - Redis admin:events publish ({type: 'refund_approved', ...})
    """
    result = await admin_refund_service.approve(
        request, db, queue_id, payload.note, admin_id=admin.id
    )

    user_id = getattr(request.state, "refund_action_user_id", None)
    payment_id = getattr(request.state, "refund_action_payment_id", None)
    amount_krw = getattr(request.state, "refund_action_amount_krw", None)
    refunded_at = getattr(request.state, "refund_action_now", None)

    if user_id is not None and payment_id is not None:
        background_tasks.add_task(
            admin_refund_service.notify_refund_approved,
            user_id=user_id,
            payment_id=payment_id,
            amount_krw=amount_krw,
            refunded_at=refunded_at,
        )
        background_tasks.add_task(
            admin_refund_service.publish_admin_event,
            {
                "type": "refund_approved",
                "queue_id": result.queue_id,
                "payment_id": result.payment_id,
                "amount_krw": result.amount_krw,
            },
        )

    return result


@router.post("/{queue_id}/deny", response_model=RefundActionResponse)
@limiter.limit("30/minute", key_func=_admin_user_id_key)
async def deny_refund(
    request: Request,
    queue_id: int,
    payload: RefundActionRequest,
    background_tasks: BackgroundTasks,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> RefundActionResponse:
    """수동 환불 거부 — payment.status 원복 + 알림."""
    result = await admin_refund_service.deny(
        request, db, queue_id, payload.note, admin_id=admin.id
    )

    user_id = getattr(request.state, "refund_action_user_id", None)
    payment_id = getattr(request.state, "refund_action_payment_id", None)
    note_summary = getattr(request.state, "refund_action_note_summary", "")

    if user_id is not None and payment_id is not None:
        background_tasks.add_task(
            admin_refund_service.notify_refund_denied,
            user_id=user_id,
            payment_id=payment_id,
            reason_summary=note_summary,
        )
        background_tasks.add_task(
            admin_refund_service.publish_admin_event,
            {
                "type": "refund_denied",
                "queue_id": result.queue_id,
                "payment_id": result.payment_id,
            },
        )

    return result


__all__ = ["router"]
