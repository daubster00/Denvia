"""빌링 라우터 — Story 3.1: GET /plans. Story 3.2: POST /billing-key, POST /subscriptions."""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.deps.auth import get_current_user
from api.src.deps.rate_limit import limit_billing
from api.src.integrations.payment.adapters.toss import TossApiError
from api.src.models.base import get_session
from api.src.models.user import User
from api.src.schemas.billing import (
    BillingPlansResponse,
    CancelSubscriptionRequest,
    CancelSubscriptionResponse,
    CurrentSubscriptionResponse,
    IssueBillingKeyRequest,
    IssueBillingKeyResponse,
    RefundRequest,
    RefundResponse,
    ResumeSubscriptionResponse,
    StartSubscriptionResponse,
)
from api.src.services.billing_service import (
    BillingCardDeclined,
    BillingKeyRequired,
    PaymentNotFound,
    PaymentNotRefundable,
    RefundAlreadyProcessed,
    RefundAlreadyRequested,
    RefundProviderUnavailable,
    ResumeNotApplicable,
    SubscriptionAlreadyActive,
    SubscriptionAlreadyCanceled,
    SubscriptionNotFound,
    cancel_subscription,
    get_billing_plans,
    get_current_subscription,
    issue_billing_key,
    request_refund,
    resume_subscription,
    start_subscription,
)

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/plans", response_model=BillingPlansResponse)
async def list_billing_plans(
    _: User = Depends(get_current_user),
) -> BillingPlansResponse:
    """구독 플랜 목록을 반환한다. 인증 필수(로그인 사용자 전용)."""
    plans = get_billing_plans()
    return BillingPlansResponse(plans=plans)


@router.post(
    "/billing-key",
    status_code=201,
    response_model=IssueBillingKeyResponse,
)
@limit_billing
async def issue_billing_key_endpoint(
    request: Request,
    body: IssueBillingKeyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> IssueBillingKeyResponse:
    """카드 토큰으로 빌링키를 발급한다."""
    try:
        result = await issue_billing_key(user, body.pg_token, body.customer_key, db)
    except TossApiError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "BILLING_TOKEN_INVALID",
                "message": e.message,
                "details": {"pg_error_code": e.code},
            },
        )
    except Exception:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "BILLING_PROVIDER_UNAVAILABLE",
                "message": "결제 서비스에 일시 지연이 있습니다. 잠시 후 다시 시도해주세요.",
            },
        )
    return IssueBillingKeyResponse(**result)


@router.post(
    "/subscriptions",
    status_code=200,
    response_model=StartSubscriptionResponse,
)
@limit_billing
async def start_subscription_endpoint(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> StartSubscriptionResponse:
    """활성 빌링키로 최초 결제 후 Pro 구독을 시작한다."""
    try:
        result = await start_subscription(user, db)
    except SubscriptionAlreadyActive:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "SUBSCRIPTION_ALREADY_ACTIVE",
                "message": "이미 Pro 구독이 활성화되어 있습니다",
            },
        )
    except BillingKeyRequired:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "BILLING_KEY_REQUIRED",
                "message": "먼저 결제 카드를 등록해주세요",
            },
        )
    except BillingCardDeclined as e:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "BILLING_CARD_DECLINED",
                "message": "카드 결제가 거절되었습니다. 카드사 확인 후 다시 시도해주세요.",
                "details": {"pg_error_code": e.pg_error_code},
            },
        )
    except Exception:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "BILLING_PROVIDER_UNAVAILABLE",
                "message": "결제 서비스에 일시 지연이 있습니다. 잠시 후 다시 시도해주세요.",
            },
        )
    return StartSubscriptionResponse(**result)


# ── Story 3.5 ────────────────────────────────────────────────────────────────


@router.post(
    "/subscriptions/cancel",
    status_code=200,
    response_model=CancelSubscriptionResponse,
)
@limit_billing
async def cancel_subscription_endpoint(
    request: Request,
    body: CancelSubscriptionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> CancelSubscriptionResponse:
    """active 구독을 cancel_pending으로 전이. 멱등 처리."""
    try:
        result = await cancel_subscription(user, body.reason, db)
    except SubscriptionAlreadyCanceled:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "SUBSCRIPTION_ALREADY_CANCELED",
                "message": "구독이 이미 해지되었습니다.",
            },
        )
    except SubscriptionNotFound:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "SUBSCRIPTION_NOT_FOUND",
                "message": "활성 구독이 없습니다.",
            },
        )
    return CancelSubscriptionResponse(**result)


@router.post(
    "/subscriptions/resume",
    status_code=200,
    response_model=ResumeSubscriptionResponse,
)
@limit_billing
async def resume_subscription_endpoint(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> ResumeSubscriptionResponse:
    """cancel_pending 구독을 active로 복원. active 멱등 200."""
    try:
        result = await resume_subscription(user, db)
    except SubscriptionAlreadyCanceled:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "SUBSCRIPTION_ALREADY_CANCELED",
                "message": "해지가 이미 적용되었습니다. 새 구독을 시작하려면 구독 페이지로 이동해주세요.",
            },
        )
    except ResumeNotApplicable:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "SUBSCRIPTION_NOT_CANCELED",
                "message": "철회할 해지 대기 구독이 없습니다.",
            },
        )
    return ResumeSubscriptionResponse(**result)


@router.get(
    "/subscriptions/current",
    response_model=CurrentSubscriptionResponse,
)
async def get_current_subscription_endpoint(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> CurrentSubscriptionResponse:
    """현재 활성/대기 구독 1건 또는 status='none'."""
    result = await get_current_subscription(user, db)
    return CurrentSubscriptionResponse(**result)


# ── Story 3.6 ────────────────────────────────────────────────────────────────


@router.post(
    "/payments/{payment_id}/refund",
    responses={
        200: {"description": "자동 환불 완료", "model": RefundResponse},
        202: {"description": "수동 검토 큐 INSERT", "model": RefundResponse},
    },
)
@limit_billing
async def refund_payment_endpoint(
    request: Request,
    payment_id: int,
    body: RefundRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """결제 환불 요청 — 자동(7일·qa=0) vs 수동 검토 분기."""
    try:
        result = await request_refund(user, payment_id, body.reason, db)
    except PaymentNotFound:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "PAYMENT_NOT_FOUND",
                "message": "결제 내역을 찾을 수 없습니다.",
            },
        )
    except PaymentNotRefundable:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "PAYMENT_NOT_REFUNDABLE",
                "message": "환불할 수 없는 결제입니다.",
            },
        )
    except RefundAlreadyProcessed:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "REFUND_ALREADY_PROCESSED",
                "message": "이미 환불된 결제입니다.",
            },
        )
    except RefundAlreadyRequested:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "REFUND_ALREADY_REQUESTED",
                "message": "환불이 이미 요청되었습니다.",
            },
        )
    except RefundProviderUnavailable:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "BILLING_PROVIDER_UNAVAILABLE",
                "message": "결제 서비스에 일시 지연이 있습니다. 잠시 후 다시 시도해주세요.",
            },
        )

    if result["status"] == "queued_for_review":
        return JSONResponse(status_code=202, content=result)
    return result
