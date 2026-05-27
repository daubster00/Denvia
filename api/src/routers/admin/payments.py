"""Admin 운영 환불 v1.1 라우터 — Story 9.1 v1.1 (ADR-0001 편차 #5).

기존 `admin/finance.py`는 동일 prefix `/admin/payments`에 결제 이벤트 타임라인(GET-only)을
얹어둔다. 본 모듈은 같은 prefix에 환불 입력 화면용 quote와 환불 실행 엔드포인트를 추가한다.
FastAPI는 prefix가 같아도 경로가 충돌하지 않으면 다중 라우터 등록을 허용한다 — `finance.py`는
`/events*`만 다루고 본 모듈은 `/{payment_id}/refund-quote`·`/{payment_id}/refunds`만 다룬다.

엔드포인트:
- GET  /api/v1/admin/payments/{payment_id}/refund-quote  60/min — 환불 입력 화면 참고 계산값
- POST /api/v1/admin/payments/{payment_id}/refunds       30/min — 환불 실행(부분/전액)
- GET  /api/v1/admin/payments/{payment_id}/refunds       60/min — 결제별 환불 이력 목록

가드:
- require_admin (denvia_admin_session 쿠키 전용).
- rate limit 키는 관리자 user_id 기반 (IP 폴백).
- 환불 실행은 응답 후 fire-and-forget으로 알림톡 + Redis admin:events publish.
- audit_logs는 AuditMiddleware가 응답 직후 자동 INSERT (서비스가 request.state에 audit_* 설정).

v1.0 자가 환불 폼(`manual_refund_queue` 기반)은 Story 3.6 v1.1 Phase 4에서 삭제됨.
"""

from __future__ import annotations

import structlog
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Request,
    Response,
)
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.deps.auth import require_admin, require_admin_page
from api.src.middleware.rate_limit import limiter
from api.src.models.base import get_session
from api.src.models.user import User
from api.src.schemas.admin.payment_refunds import (
    RefundCreateRequest,
    RefundCreateResponse,
    RefundListResponse,
    RefundQuoteResponse,
)
from api.src.services import admin_payment_service
from api.src.services.refund_quote_service import get_refund_quote
from api.src.utils.jwt import (
    JWTDecodeError,
    SessionExpired,
    decode_admin_session_jwt,
)

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/admin/payments",
    tags=["admin-payments"],
    dependencies=[Depends(require_admin_page("/admin/finance"))],
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


@router.get(
    "/{payment_id}/refund-quote",
    response_model=RefundQuoteResponse,
)
@limiter.limit("60/minute", key_func=_admin_user_id_key)
async def get_refund_quote_endpoint(
    request: Request,
    response: Response,
    payment_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> RefundQuoteResponse:
    """환불 입력 화면 진입 시 노출되는 참고 계산값 묶음.

    잔액 가드 상한, 전액·일할 권장값, 청약철회 판정, 다음 sequence를 한 번에 묶어 반환한다.
    실제 환불 실행은 별도 POST 엔드포인트.

    404는 `refund_quote_service.get_refund_quote`가 던지는 HTTPException을 그대로 통과시킨다.
    """
    result = await get_refund_quote(db, payment_id)
    response.headers["Cache-Control"] = "no-store"
    logger.info(
        "admin.payments.refund_quote.viewed",
        admin_id=admin.id,
        payment_id=payment_id,
        refundable_balance=result.refundable_balance,
        next_refund_sequence=result.next_refund_sequence,
        is_within_cooling_off=result.is_within_cooling_off,
        trace_id=str(getattr(request.state, "trace_id", "")),
    )
    return result


@router.post(
    "/{payment_id}/refunds",
    response_model=RefundCreateResponse,
)
@limiter.limit("30/minute", key_func=_admin_user_id_key)
async def create_payment_refund(
    request: Request,
    payment_id: int,
    payload: RefundCreateRequest,
    background_tasks: BackgroundTasks,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> RefundCreateResponse:
    """관리자 운영 환불(부분/전액) 실행.

    응답 후 fire-and-forget:
    - 알림톡 billing.refund_manual (UI_1758, 2026-05-26 청약철회와 본문 분리)
    - Redis admin:events publish ({type: 'refund_operational_created', ...})

    서비스 레이어는 `request.state.refund_op_*`에 후처리 페이로드를 저장한다 — 실패 경로에서는
    설정되지 않으므로 분기 발행한다.
    """
    result = await admin_payment_service.create_refund(
        request, db, payment_id, payload, admin_id=admin.id
    )

    user_id = getattr(request.state, "refund_op_user_id", None)
    payload_payment_id = getattr(request.state, "refund_op_payment_id", None)
    amount_krw = getattr(request.state, "refund_op_amount_krw", None)
    cancel_amount = getattr(request.state, "refund_op_cancel_amount", None)
    refund_reason = getattr(request.state, "refund_op_refund_reason", None)
    idempotency_key = getattr(request.state, "refund_op_idempotency_key", None)
    refunded_at = getattr(request.state, "refund_op_now", None)

    if (
        user_id is not None
        and payload_payment_id is not None
        and idempotency_key is not None
        and refunded_at is not None
    ):
        background_tasks.add_task(
            admin_payment_service.notify_refund_succeeded,
            user_id=user_id,
            payment_id=payload_payment_id,
            amount_krw=amount_krw,
            refund_amount_krw=cancel_amount,
            refund_reason=refund_reason,
            refunded_at=refunded_at,
            idempotency_key=idempotency_key,
        )
        background_tasks.add_task(
            admin_payment_service.publish_admin_event,
            {
                "type": "refund_operational_created",
                "payment_id": payload_payment_id,
                "refund_id": result.refund_id,
                "refund_sequence": result.refund_sequence,
                "cancel_amount": result.cancel_amount,
                "refund_reason": refund_reason,
            },
        )

    return result


@router.get(
    "/{payment_id}/refunds",
    response_model=RefundListResponse,
)
@limiter.limit("60/minute", key_func=_admin_user_id_key)
async def list_payment_refunds(
    request: Request,
    response: Response,
    payment_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> RefundListResponse:
    """결제별 환불 이력 목록 — 시계열(created_at ASC) 정렬.

    환불 입력 화면에서 누적 부분환불 현황을 보여줄 때 quote 응답과 함께 호출한다.
    payment 존재 검증은 서비스 레이어에서 404를 던지면 전역 핸들러가 표준 포맷으로 변환한다.
    """
    result = await admin_payment_service.list_refunds(db, payment_id)
    response.headers["Cache-Control"] = "no-store"
    logger.info(
        "admin.payments.refunds.listed",
        admin_id=admin.id,
        payment_id=payment_id,
        total=result.total,
        trace_id=str(getattr(request.state, "trace_id", "")),
    )
    return result


__all__ = ["router"]
