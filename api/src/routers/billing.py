"""빌링 라우터 — Story 3.1: GET /plans. Story 3.2: POST /billing-key, POST /subscriptions.

Story 3.6 v1.1 (2026-05-12): 자가 환불 폼 폐지. 청약철회 단일 경로만 노출 —
GET /subscriptions/me/refund-eligibility + POST /subscriptions/me/cancel-with-refund.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from redis.asyncio import Redis as AsyncRedis
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.deps.auth import get_current_user
from api.src.deps.rate_limit import limit_billing
from api.src.deps.redis import get_redis_runtime
from api.src.integrations.payment.adapters.toss import TossApiError
from api.src.models.base import get_session
from api.src.models.user import User
from api.src.schemas.admin.runtime_config import TossPgClientConfigResponse
from api.src.schemas.billing import (
    BillingPlansResponse,
    CancelSubscriptionRequest,
    CancelSubscriptionResponse,
    CancelWithRefundRequest,
    CancelWithRefundResponse,
    CurrentSubscriptionResponse,
    IssueBillingKeyRequest,
    IssueBillingKeyResponse,
    RefundEligibilityResponse,
    ResumeSubscriptionResponse,
    StartSubscriptionResponse,
)
from api.src.services import pg_config_service
from api.src.services.billing_service import (
    BillingCardDeclined,
    BillingKeyRequired,
    NoActiveSubscription,
    NoRefundablePayment,
    PaymentNotRefundable,
    RefundAlreadyProcessed,
    RefundAlreadyRequested,
    RefundNotEligible,
    RefundProviderUnavailable,
    ResumeNotApplicable,
    SubscriptionAlreadyActive,
    SubscriptionAlreadyCanceled,
    SubscriptionNotFound,
    cancel_subscription,
    cancel_with_refund,
    check_refund_eligibility,
    get_billing_plans,
    get_current_subscription,
    issue_billing_key,
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


@router.get("/client-config", response_model=TossPgClientConfigResponse)
async def get_billing_client_config(
    response: Response,
    _: User = Depends(get_current_user),
    redis_runtime: AsyncRedis = Depends(get_redis_runtime),
) -> TossPgClientConfigResponse:
    """결제창 초기화용 — 현재 활성 모드의 토스 client_key 반환.

    관리자 페이지에서 모드 토글/키 교체 시 다음 결제 시도부터 즉시 반영된다.
    client_key 가 비어있으면 빈 문자열을 돌려주고, 프론트가 안내 메시지로 폴백.
    """
    response.headers["Cache-Control"] = "no-store"
    client_key, mode = await pg_config_service.get_active_client_key(redis_runtime)
    return TossPgClientConfigResponse(mode=mode, client_key=client_key)


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


# ── Story 3.6 v1.1 — 청약철회 (Cooling-off Refund) ─────────────────────────────
# v1.1 정책 변경(2026-05-12, ADR-0001 편차 #5)으로 자가 환불 폼 폐지.
# 사용자 환불 경로는 본 라우터 2개 엔드포인트로 단일화:
#   · GET  /subscriptions/me/refund-eligibility  (read-only 사전 조회)
#   · POST /subscriptions/me/cancel-with-refund  (즉시 해지 + 전액 환불 실행)
# 운영 환불(관리자 부분/전액)은 Story 9.1 v1.1 admin 라우터 책임.


@router.get(
    "/subscriptions/me/refund-eligibility",
    response_model=RefundEligibilityResponse,
)
async def get_refund_eligibility_endpoint(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> RefundEligibilityResponse:
    """청약철회 가능 여부 조회 (Story 3.6 v1.1 AC1) — read-only, side effect 없음."""
    result = await check_refund_eligibility(user, db)
    return RefundEligibilityResponse(**result)


@router.post(
    "/subscriptions/me/cancel-with-refund",
    response_model=CancelWithRefundResponse,
)
@limit_billing
async def cancel_with_refund_endpoint(
    request: Request,
    body: CancelWithRefundRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> CancelWithRefundResponse:
    """청약철회 — 구독 즉시 해지 + 전액 환불 (Story 3.6 v1.1 AC2~6).

    7일 이내 + 해당 구독 기간 동안 질문 0건 조건을 서버가 재검증한다.
    조건 미충족은 422 REFUND_NOT_ELIGIBLE (클라이언트 사전 조회 우회 방어).
    """
    try:
        result = await cancel_with_refund(user, db)
    except NoActiveSubscription:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "NO_ACTIVE_SUBSCRIPTION",
                "message": "활성 구독이 없습니다.",
            },
        )
    except NoRefundablePayment:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "NO_REFUNDABLE_PAYMENT",
                "message": "환불 대상 결제를 찾을 수 없습니다.",
            },
        )
    except RefundNotEligible as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "REFUND_NOT_ELIGIBLE",
                "message": "청약철회 조건을 충족하지 않습니다.",
                "reason_code": exc.reason_code,
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
                "message": "환불이 진행 중입니다.",
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
    except RefundProviderUnavailable:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "BILLING_PROVIDER_UNAVAILABLE",
                "message": "결제 서비스에 일시 지연이 있습니다. 잠시 후 다시 시도해주세요.",
            },
        )

    return CancelWithRefundResponse(**result)
