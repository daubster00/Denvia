"""현재 세션 사용자 관련 엔드포인트."""

import secrets as _secrets
from datetime import datetime, timezone
from typing import Annotated, Literal

import sentry_sdk
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from redis.asyncio import Redis as AsyncRedis
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import desc, func, select

from api.src.deps.auth import get_current_user, get_current_user_allow_blocked
from api.src.deps.redis import get_redis_quota, get_redis_runtime
from api.src.integrations.messaging.adapters import get_adapter as _get_messaging
from api.src.models.base import get_session
from api.src.models.billing_key import BillingKey
from api.src.models.payment import Payment
from api.src.models.qa_log import QALog
from api.src.models.user import User
from api.src.schemas.auth import PasswordChangeRequest, SegmentRequest, SessionUserResponse
from api.src.schemas.inbox import (
    ActivePopupResponse,
    InboxListResponse,
    InboxPreviewResponse,
    UnreadCountResponse,
)
from api.src.schemas.me import (
    PasswordChangeWithCurrentRequest,
    PaymentHistoryItem,
    PaymentHistoryResponse,
    ProfileResponse,
    ProfileUpdateRequest,
    QuotaResponse,
    UsageSummaryResponse,
    WithdrawOtpSendResponse,
    WithdrawOtpVerifyRequest,
    WithdrawOtpVerifyResponse,
    WithdrawRequest,
)
from api.src.services import auth_service, inbox_service, runtime_config_service
from api.src.services.auth_service import (
    send_sms_otp_flow,
    verify_phone_change_token,
    verify_sms_otp_flow,
    verify_withdraw_token,
)
from api.src.services.qa_service import (
    ADMIN_UNLIMITED_LIMIT,
    _month_key_kst,
    _next_kst_midnight_iso,
    _next_kst_month_start_iso,
    _resolve_bool,
    _resolve_daily_limit,
    _resolve_delay,
    _resolve_pro_monthly_limit,
    _today_key_kst,
)
from api.src.settings import REDIS_DB_RATE_LIMIT, settings
from api.src.utils.argon2 import hash_password, verify_password
from api.src.utils.jwt import encode_session_jwt
from api.src.utils.korean_time import now_kst

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["me"])


@router.get("/me/quota", response_model=QuotaResponse)
async def get_my_quota(
    current_user: User = Depends(get_current_user),
    redis_quota: AsyncRedis = Depends(get_redis_quota),
    redis_runtime: AsyncRedis = Depends(get_redis_runtime),
) -> QuotaResponse:
    """현재 사용자의 일일 Q&A 한도 현황을 반환한다 (AC-6).

    admin은 preflight에서 quota/delay를 우회하므로(qa_service.preflight),
    /me/quota 응답도 동일한 정책으로 일관되게 unlimited 형태로 반환한다.
    """
    # 지연 안내문구 — 글로벌 토글 ON & 무료 플랜일 때만 비어있지 않은 문자열을 반환.
    # Pro/admin 은 지연 자체가 없으므로 안내도 빈 문자열로 강제(필드명 `free_delay_*` 의도와 일치).
    # 프론트는 빈 문자열이면 안내 영역 자체를 렌더하지 않는다.
    delay_enabled_global = await _resolve_bool(
        redis_runtime, "runtime:free_delay_enabled", default=True
    )

    if current_user.subscription_status == "admin":
        return QuotaResponse(
            subscription_status="admin",
            daily_limit=ADMIN_UNLIMITED_LIMIT,
            used_today=0,
            remaining=ADMIN_UNLIMITED_LIMIT,
            reset_at=_next_kst_midnight_iso(),
            show_upgrade_prompt=False,
            show_subscribe_button=False,
            delay_seconds=0.0,
            free_delay_notice_text="",
        )

    raw = await redis_quota.get(_today_key_kst(current_user.id))
    used = int(raw) if raw is not None else 0
    limit, _src = await _resolve_daily_limit(current_user, redis_runtime)
    delay, _dsrc = await _resolve_delay(current_user, redis_runtime)
    is_pro = current_user.subscription_status == "pro"
    show_upgrade = (
        False
        if is_pro
        else await _resolve_bool(redis_runtime, "runtime:show_upgrade_prompt", default=True)
    )
    show_subscribe = (
        False
        if is_pro
        else await _resolve_bool(redis_runtime, "runtime:show_subscribe_button", default=True)
    )
    notice_text = (
        ""
        if is_pro
        else (
            await runtime_config_service.get_free_delay_notice_text(redis_runtime)
            if delay_enabled_global
            else ""
        )
    )
    return QuotaResponse(
        subscription_status=current_user.subscription_status,
        daily_limit=limit,
        used_today=used,
        remaining=max(limit - used, 0),
        reset_at=_next_kst_midnight_iso(),
        show_upgrade_prompt=show_upgrade,
        show_subscribe_button=show_subscribe,
        delay_seconds=float(delay),
        free_delay_notice_text=notice_text,
    )


@router.get("/me/usage-summary", response_model=UsageSummaryResponse)
async def get_my_usage_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    redis_quota: AsyncRedis = Depends(get_redis_quota),
    redis_runtime: AsyncRedis = Depends(get_redis_runtime),
) -> UsageSummaryResponse:
    """마이페이지 — 당월 누적 + 당일 + 플랜 + 가입유형/연차 통합 응답 (Story 4.3 / FR26·FR28·FR48).

    Story 2.3 헬퍼(`_today_key_kst`, `_resolve_daily_limit`, `_resolve_bool`,
    `_next_kst_midnight_iso`)를 그대로 재사용하여 quota 로직 드리프트를 막는다.
    `subscriptions` 정보는 본 응답에 포함하지 않으며 프론트는 Story 3.5
    `fetchCurrentSubscription`을 별도로 호출한다.
    """
    # 1) 당월 누적 질문 수 — KST 월초 기준 (FR26).
    #    UTC 컬럼(created_at)을 KST로 환산한 뒤 월초 시점을 다시 UTC로 비교.
    month_count_stmt = (
        select(func.count())
        .select_from(QALog)
        .where(
            QALog.user_id == current_user.id,
            QALog.created_at
            >= func.timezone(
                "Asia/Seoul",
                func.date_trunc(
                    "month", func.timezone("Asia/Seoul", func.now())
                ),
            ),
        )
    )
    month_count = (await db.execute(month_count_stmt)).scalar_one()

    # 2) 당일 사용량 — Story 2.3 패턴 그대로.
    if current_user.subscription_status == "pro":
        daily_used = 0
        daily_limit = 0
    elif current_user.subscription_status == "admin":
        daily_used = 0
        daily_limit = ADMIN_UNLIMITED_LIMIT
    else:
        raw = await redis_quota.get(_today_key_kst(current_user.id))
        daily_used = int(raw) if raw is not None else 0
        daily_limit, _src = await _resolve_daily_limit(current_user, redis_runtime)

    # 3) A-303 구독 버튼 토글 (FR48). Pro/admin은 항상 False.
    if current_user.subscription_status in ("pro", "admin"):
        show_subscribe = False
    else:
        show_subscribe = await _resolve_bool(
            redis_runtime, "runtime:show_subscribe_button", default=True
        )

    # 4) Pro 월 한도 — 관리자 설정값 + Redis monthly INCR 카운터.
    #    qa_service.preflight 의 enforcement 와 동일 SSOT(quota:user:{id}:month:YYYY-MM)를 읽는다.
    if current_user.subscription_status == "pro":
        monthly_limit = await _resolve_pro_monthly_limit(redis_runtime)
        raw_month = await redis_quota.get(_month_key_kst(current_user.id))
        monthly_used = int(raw_month) if raw_month is not None else 0
    elif current_user.subscription_status == "admin":
        monthly_limit = ADMIN_UNLIMITED_LIMIT
        monthly_used = 0
    else:
        monthly_limit = 0
        monthly_used = 0

    logger.info(
        "me.usage_summary.viewed",
        user_id=current_user.id,
        subscription_status=current_user.subscription_status,
        segment=current_user.segment,
    )

    return UsageSummaryResponse(
        month_question_count=int(month_count),
        daily_used=daily_used,
        daily_limit=daily_limit,
        daily_remaining=max(daily_limit - daily_used, 0),
        daily_reset_at=_next_kst_midnight_iso(),
        subscription_status=current_user.subscription_status,
        segment=current_user.segment,
        years_of_experience=current_user.years_of_experience,
        show_subscribe_button=show_subscribe,
        monthly_limit=monthly_limit,
        monthly_used=monthly_used,
        monthly_remaining=max(monthly_limit - monthly_used, 0),
        monthly_reset_at=_next_kst_month_start_iso(),
    )


_ALLOWED_PER_PAGE = (10, 20, 50)


@router.get("/me/payments", response_model=PaymentHistoryResponse)
async def get_my_payments(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query()] = 20,
) -> PaymentHistoryResponse:
    """본인 결제 내역 페이지네이션 (Story 4.4 / FR27 / F-402).

    - `WHERE Payment.user_id = current_user.id` 절을 강제로 포함해 본인 row만 조회한다.
    - subscriptions / billing_keys 모두 단일 SELECT JOIN으로 처리해 N+1을 회피한다.
    - card_last4/card_company는 결제 시점 활성 빌링키를 LEFT JOIN으로 매칭한다
      (`charged_at >= bk.created_at AND (bk.revoked_at IS NULL OR charged_at < bk.revoked_at)`).
    """
    if per_page not in _ALLOWED_PER_PAGE:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_PARAM",
                "message": "per_page는 10/20/50 중 하나여야 합니다.",
            },
        )

    total = (
        await db.execute(
            select(func.count(Payment.id)).where(Payment.user_id == current_user.id)
        )
    ).scalar_one()

    bk_subq = (
        select(
            BillingKey.user_id.label("bk_user_id"),
            BillingKey.created_at.label("bk_created_at"),
            BillingKey.revoked_at.label("bk_revoked_at"),
            BillingKey.card_last4.label("bk_card_last4"),
            BillingKey.card_company.label("bk_card_company"),
        )
        .where(BillingKey.user_id == current_user.id)
        .subquery()
    )

    # 회차 기간은 결제 당시 박제된 payments.subscription_period_* 스냅샷을 사용한다.
    # Subscription.current_period_end는 자동 갱신 시 미래로 이동하므로 join하면
    # 과거 결제 row의 표시 기간이 "최초 시작 ~ 최신 만료"로 오염된다(코드리뷰 이슈 #3).
    stmt = (
        select(
            Payment.id,
            Payment.charged_at,
            Payment.amount_krw,
            Payment.provider_order_id,
            Payment.status,
            Payment.subscription_period_start.label("sub_started_at"),
            Payment.subscription_period_end.label("sub_period_end"),
            bk_subq.c.bk_card_last4,
            bk_subq.c.bk_card_company,
        )
        .where(Payment.user_id == current_user.id)
        .join(
            bk_subq,
            (bk_subq.c.bk_user_id == Payment.user_id)
            & (Payment.charged_at.isnot(None))
            & (Payment.charged_at >= bk_subq.c.bk_created_at)
            & (
                (bk_subq.c.bk_revoked_at.is_(None))
                | (Payment.charged_at < bk_subq.c.bk_revoked_at)
            ),
            isouter=True,
        )
        .order_by(desc(Payment.charged_at).nulls_last(), desc(Payment.id))
        .offset((page - 1) * per_page)
        .limit(per_page)
    )

    rows = (await db.execute(stmt)).all()

    items = [
        PaymentHistoryItem(
            payment_id=r.id,
            charged_at=r.charged_at.isoformat() if r.charged_at else None,
            subscription_period_start=(
                r.sub_started_at.isoformat() if r.sub_started_at else None
            ),
            subscription_period_end=(
                r.sub_period_end.isoformat() if r.sub_period_end else None
            ),
            buyer_email=current_user.email,
            card_last4=r.bk_card_last4,
            card_company=r.bk_card_company,
            amount_krw=r.amount_krw,
            provider_order_id=r.provider_order_id,
            status=r.status,
        )
        for r in rows
    ]

    logger.info(
        "me.payments.viewed",
        user_id=current_user.id,
        page=page,
        per_page=per_page,
        total_returned=len(items),
    )

    return PaymentHistoryResponse(
        items=items,
        page=page,
        per_page=per_page,
        total=int(total),
    )


# ────────────────────────────────────────────────────────────────────────────
# Story 4.5 — 받은 쪽지함 + 팝업 (F-503)
# ────────────────────────────────────────────────────────────────────────────


_INBOX_ALLOWED_PER_PAGE = (10, 20, 50)


@router.get("/me/inbox", response_model=InboxListResponse)
async def get_my_inbox(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query()] = 20,
    filter: Annotated[Literal["all", "unread"], Query()] = "all",
) -> InboxListResponse:
    """본인 쪽지함 페이지네이션 조회 (Story 4.5 / FR31 / F-503)."""
    if per_page not in _INBOX_ALLOWED_PER_PAGE:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_PARAM",
                "message": "per_page는 10/20/50 중 하나여야 합니다.",
            },
        )
    response = await inbox_service.list_inbox(
        db,
        current_user.id,
        page=page,
        per_page=per_page,
        filter_unread=(filter == "unread"),
    )
    logger.info(
        "inbox.viewed",
        user_id=current_user.id,
        page=page,
        per_page=per_page,
        total_returned=len(response.items),
        unread_count=response.unread_count,
    )
    return response


@router.patch("/me/inbox/{message_id}/read", status_code=204)
async def mark_inbox_message_read(
    message_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> Response:
    """본인 쪽지를 읽음 처리한다(멱등). 타인 row 또는 미존재 시 404."""
    was_already = await inbox_service.mark_read(db, current_user.id, message_id)
    if was_already is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "INBOX_MESSAGE_NOT_FOUND",
                "message": "쪽지를 찾을 수 없습니다.",
            },
        )
    logger.info(
        "inbox.message.read",
        user_id=current_user.id,
        message_id=message_id,
        was_already_read=was_already,
    )
    return Response(status_code=204)


@router.delete("/me/inbox/{message_id}", status_code=204)
async def delete_my_inbox_message(
    message_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> Response:
    """본인 쪽지를 휴지통으로 보낸다(soft delete).

    deleted_at=NOW가 채워지면 즉시 쪽지함/미읽음 카운트에서 사라진다.
    실제 행 삭제는 30일 후 retention 배치(purge_old_inbox_messages)가 처리한다.
    멱등 — 이미 삭제된 row도 204.
    """
    ok = await inbox_service.soft_delete(db, current_user.id, message_id)
    if not ok:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "INBOX_MESSAGE_NOT_FOUND",
                "message": "쪽지를 찾을 수 없습니다.",
            },
        )
    logger.info(
        "inbox.message.deleted",
        user_id=current_user.id,
        message_id=message_id,
    )
    return Response(status_code=204)


@router.get("/me/inbox/unread-count", response_model=UnreadCountResponse)
async def get_my_inbox_unread_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> UnreadCountResponse:
    """TopNav 미읽음 뱃지용 카운트."""
    count = await inbox_service.get_unread_count(db, current_user.id)
    return UnreadCountResponse(unread_count=count)


@router.get("/me/inbox/preview", response_model=InboxPreviewResponse)
async def get_my_inbox_preview(
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    redis_runtime: AsyncRedis = Depends(get_redis_runtime),
) -> InboxPreviewResponse:
    """쪽지함 아이콘 밑 미리보기 드롭다운 — Story 7.1.

    동시 노출 개수는 관리자 설정(Redis)에서 강제 — client limit 쿼리는 받지 않는다.
    """
    response.headers["Cache-Control"] = "no-store"
    max_count = await runtime_config_service.get_inbox_preview_max_count(redis_runtime)
    return await inbox_service.get_preview_messages(db, current_user.id, max_count)


@router.get("/me/popups/active", response_model=list[ActivePopupResponse])
async def get_active_popups(
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    device: Annotated[Literal["pc", "mobile"], Query()] = "pc",
) -> list[ActivePopupResponse]:
    """메인 진입 시 노출 후보 배열 — Story 7.2 v2.

    캐러셀 형태로 노출. 디바이스 필터: target_device IN ('both', :device).
    노출 1회/세션 + '오늘 안보기' 필터는 클라이언트 sessionStorage/localStorage에서 처리.
    """
    response.headers["Cache-Control"] = "no-store"
    return await inbox_service.get_active_popups(db, current_user, device)


# ────────────────────────────────────────────────────────────────────────────
# Story 1.7 — 회원 탈퇴 (F-108)
# ────────────────────────────────────────────────────────────────────────────


def _is_secure_env() -> bool:
    return settings.environment.lower() in {"production", "staging"}


def _mask_phone(phone: str) -> str:
    """`010-12345678` 또는 `01012345678` 형식 모두 `010-****-5678` 마스킹."""
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) < 7:
        return "***-****-****"
    return f"{digits[:3]}-****-{digits[-4:]}"


@router.post("/me/withdraw/send-otp", response_model=WithdrawOtpSendResponse)
async def withdraw_send_otp(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> WithdrawOtpSendResponse:
    """소셜 가입자 본인 인증용 OTP 발송 (Story 1.7 / AC-9).

    - 자체 가입자(password_hash 존재)는 비밀번호 경로를 사용하므로 403.
    - phone이 NULL인 소셜 사용자(Story 1.6 보충 전 계정 등)는 422.
    """
    if current_user.password_hash is not None:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "NOT_SOCIAL_ACCOUNT",
                "message": "자체 가입 계정은 비밀번호로 본인 인증해주세요.",
            },
        )
    if current_user.phone is None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "PHONE_NOT_REGISTERED",
                "message": "등록된 휴대폰이 없습니다.",
            },
        )
    ip = request.client.host if request.client else None
    await send_sms_otp_flow(
        phone=current_user.phone,
        purpose="withdraw",
        redis_url=settings.redis_url,
        messaging=_get_messaging(),
        expose_code=settings.messaging_provider == "stub",
        db=db,
        ip=ip,
    )
    return WithdrawOtpSendResponse(masked_phone=_mask_phone(current_user.phone))


@router.post("/me/withdraw/verify-otp", response_model=WithdrawOtpVerifyResponse)
async def withdraw_verify_otp(
    body: WithdrawOtpVerifyRequest,
    current_user: User = Depends(get_current_user),
) -> WithdrawOtpVerifyResponse:
    """소셜 가입자 OTP 검증 — phone_verification_token 발급 (Story 1.7 / AC-9)."""
    if current_user.password_hash is not None:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "NOT_SOCIAL_ACCOUNT",
                "message": "자체 가입 계정은 비밀번호로 본인 인증해주세요.",
            },
        )
    if current_user.phone is None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "PHONE_NOT_REGISTERED",
                "message": "등록된 휴대폰이 없습니다.",
            },
        )
    token = await verify_sms_otp_flow(
        phone=current_user.phone,
        code=body.code,
        purpose="withdraw",
        redis_url=settings.redis_url,
    )
    return WithdrawOtpVerifyResponse(phone_verification_token=token)


@router.delete("/me", status_code=204)
async def withdraw_me(
    body: WithdrawRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> Response:
    """본인 계정 탈퇴 (Story 1.7).

    - 자체 가입자: `password` 필수 → argon2 검증
    - 소셜 가입자: `phone_verification_token` 필수 → Redis 1회용 소진
    - 활성 Pro 구독자는 409로 차단(서비스 레이어에서)
    - 성공 시 PII 즉시 파기 + 쿠키 소거 + 204
    """
    is_social = current_user.password_hash is None

    if is_social:
        if not body.phone_verification_token:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "SMS_TOKEN_INVALID",
                    "message": "휴대폰 인증이 필요합니다.",
                },
            )
        if current_user.phone is None:
            # 토큰만으로는 phone 매칭 불가 — 방어적 422
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "PHONE_NOT_REGISTERED",
                    "message": "등록된 휴대폰이 없습니다.",
                },
            )
        await verify_withdraw_token(
            phone_verification_token=body.phone_verification_token,
            expected_phone=current_user.phone,
            redis_url=settings.redis_url,
        )
    else:
        if not body.password:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "AUTH_INVALID_CREDENTIALS",
                    "message": "비밀번호가 일치하지 않습니다.",
                },
            )
        if not verify_password(body.password, current_user.password_hash):
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "AUTH_INVALID_CREDENTIALS",
                    "message": "비밀번호가 일치하지 않습니다.",
                },
            )

    # request 메타데이터 추출
    forwarded_for = request.headers.get("X-Forwarded-For")
    ip = (
        forwarded_for.split(",")[0].strip()
        if forwarded_for
        else (request.client.host if request.client else None)
    )
    ua = request.headers.get("User-Agent")
    trace_id = getattr(request.state, "trace_id", None)

    await auth_service.withdraw(
        user=current_user,
        ip=ip,
        ua=ua,
        db=db,
        trace_id=trace_id,
    )

    # 쿠키 소거 (denvia_session + denvia_csrf, Max-Age=0).
    # Response 인스턴스를 직접 만들어 두 Set-Cookie 헤더를 모두 보존한다
    # (dict(response.headers)는 동일 키를 합쳐 두 번째 쿠키가 손실됨).
    secure = _is_secure_env()
    out = Response(status_code=204)
    out.set_cookie(
        key="denvia_session",
        value="",
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
        max_age=0,
    )
    out.set_cookie(
        key="denvia_csrf",
        value="",
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
        max_age=0,
    )
    return out


# ────────────────────────────────────────────────────────────────────────────
# (Existing) GET /me — 세션 유저 정보
# ────────────────────────────────────────────────────────────────────────────


@router.get("/me", response_model=SessionUserResponse)
async def get_me(current_user: User = Depends(get_current_user_allow_blocked)) -> SessionUserResponse:
    """세션 쿠키에서 user_id를 꺼내 현재 사용자 정보를 snake_case로 반환한다."""
    return SessionUserResponse(
        user_id=current_user.id,
        email=current_user.email,
        role=current_user.role,
        subscription_status=current_user.subscription_status,
        segment=current_user.segment,
        years_of_experience=current_user.years_of_experience,
        must_reset_password=current_user.must_reset_password,
        is_social=current_user.password_hash is None,
    )


@router.post("/me/segment", status_code=204)
async def set_segment(
    body: SegmentRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> None:
    """가입유형·연차 설정 — 최초 설정만 허용 (AR34: 사후 변경은 관리자만).

    - doctor/hygienist → years_of_experience 필수
    - student_other → years_of_experience 허용 안 함
    """
    # 이미 설정된 경우 409
    if current_user.segment is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "SEGMENT_ALREADY_SET",
                "message": "가입유형 변경은 고객 문의로 요청해주세요.",
            },
        )

    # 연차 일관성 검증
    needs_years = body.segment in ("doctor", "hygienist")
    if needs_years and body.years_of_experience is None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "SEGMENT_YEARS_INCONSISTENT",
                "message": "치과의사/위생사는 연차 입력이 필요합니다.",
            },
        )
    if not needs_years and body.years_of_experience is not None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "SEGMENT_YEARS_INCONSISTENT",
                "message": "학생·기타는 연차를 입력할 수 없습니다.",
            },
        )

    current_user.segment = body.segment
    current_user.years_of_experience = body.years_of_experience
    # 매년 1월 1일 +1 가산 배치의 가드값 — 가입한 해는 카운트하지 않도록
    # 현재 KST 연도를 기록(연차가 NULL이면 가산 대상도 아니므로 None 유지).
    if body.years_of_experience is not None:
        current_user.experience_last_increment_year = now_kst().year
    current_user.updated_at = datetime.now(tz=timezone.utc)
    await db.commit()

    sentry_sdk.add_breadcrumb(
        message="user.segment.set",
        data={"user_id": current_user.id, "segment": body.segment},
    )
    logger.info(
        "user.segment.set",
        user_id=current_user.id,
        segment=body.segment,
    )


@router.post("/me/password", status_code=200)
async def change_password(
    body: PasswordChangeRequest,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """비밀번호 신규 설정 — 두 가지 경로만 통과:

    1) 소셜 가입자(`password_hash IS NULL`) → 최초 비밀번호 설정
    2) 임시 비밀번호 발급 직후(`must_reset_password=True`) → 정식 비밀번호로 교체

    그 외 평범한 이메일 가입자는 기존 비밀번호 확인이 필요한 `/me/password/change`로
    유도(403 PASSWORD_ALREADY_SET) — old-PW 검증 없이 덮어쓰는 경로를 차단한다.

    JWT 및 CSRF 쿠키를 재발급한다.
    """
    if current_user.password_hash is not None and not current_user.must_reset_password:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "PASSWORD_ALREADY_SET",
                "message": "기존 비밀번호가 있는 계정은 비밀번호 변경 경로를 사용해주세요.",
            },
        )

    current_user.password_hash = hash_password(body.new_password)
    current_user.must_reset_password = False
    # 비밀번호 변경 시 단일 세션 nonce 도 회전 — 다른 기기에 남아있던 세션은 sid mismatch 로 자동 무효화.
    current_user.current_session_id = _secrets.token_urlsafe(24)
    current_user.updated_at = datetime.now(tz=timezone.utc)
    await db.commit()

    token = encode_session_jwt(
        user_id=current_user.id,
        role=current_user.role,
        subscription_status=current_user.subscription_status,
        persist=False,  # NFR-S4: 비밀번호 변경 시 비지속 세션 재발급
        session_id=current_user.current_session_id,
    )
    response.set_cookie(
        key="denvia_session",
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=3600,
    )
    csrf_token = _secrets.token_urlsafe(32)
    response.set_cookie(
        key="denvia_csrf",
        value=csrf_token,
        httponly=False,
        secure=True,
        samesite="strict",
        max_age=3600,
    )

    logger.info("auth.password.reset_completed", user_id=current_user.id)

    return {"ok": True}


# ────────────────────────────────────────────────────────────────────────────
# 회원정보(My Profile) — GET/PATCH /me/profile, POST /me/password/change
# ────────────────────────────────────────────────────────────────────────────

# 비밀번호 변경 브루트포스 방어 — user_id 기반(이미 인증된 세션이므로 email이 아닌
# user_id 기준). login_user(이메일 기반)와 동일한 5분 락아웃 / 3회 임계치를 사용.
_PW_CHANGE_FAIL_KEY = "pw_change_fail:{user_id}"
_PW_CHANGE_LOCKOUT_KEY = "pw_change_lockout:{user_id}"
_PW_CHANGE_LOCKOUT_TTL = 300
_PW_CHANGE_FAIL_WINDOW = 300
_PW_CHANGE_BRUTE_THRESHOLD = 3


def _make_pw_rl_redis() -> AsyncRedis:
    return AsyncRedis.from_url(
        f"{settings.redis_url}/{REDIS_DB_RATE_LIMIT}",
        decode_responses=True,
    )


@router.get("/me/profile", response_model=ProfileResponse)
async def get_me_profile(
    current_user: User = Depends(get_current_user),
) -> ProfileResponse:
    """마이페이지 회원정보 — 이메일·이름·휴대폰·주소를 한 번에 반환.

    `/me`(세션 부트스트랩)는 빈번히 호출되므로 PII를 섞지 않는다.
    이 엔드포인트는 `/my/profile` 페이지 마운트 시 1회 호출된다.
    """
    return ProfileResponse(
        email=current_user.email,
        name=current_user.name,
        phone=current_user.phone,
        phone_verified=current_user.phone_verified,
        is_social=current_user.password_hash is None,
        postcode=current_user.postcode,
        address_road=current_user.address_road,
        address_detail=current_user.address_detail,
        gender=current_user.gender,
        birthdate=current_user.birthdate,
        marketing_consent=current_user.marketing_consent_at is not None,
        marketing_consent_at=(
            current_user.marketing_consent_at.isoformat()
            if current_user.marketing_consent_at
            else None
        ),
        segment=current_user.segment,
        years_of_experience=current_user.years_of_experience,
    )


@router.patch("/me/profile", status_code=204)
async def patch_me_profile(
    body: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> Response:
    """마이페이지 회원정보 부분 수정.

    - 이름·주소(우편번호·도로명·상세): 즉시 갱신
    - 휴대폰: `body.phone`이 현재 값과 다르면 `phone_verification_token` 필수
      (SMS OTP `purpose=phone_change`로 발급된 토큰), 충돌 검사 통과 시
      `phone_verified=True` 갱신
    - 빈 문자열은 Pydantic validator에서 None으로 정규화됨
    - 이메일은 변경 불가(요청 본문에 포함되지 않음)
    """
    # PATCH 의미 — 클라이언트가 명시적으로 보낸 키만 갱신한다(`exclude_unset`).
    # 빈 문자열은 validator에서 None으로 정규화되므로 "필드를 비우는" 요청과
    # "필드를 건드리지 않는" 요청을 구분할 수 있다.
    sent_fields = body.model_fields_set
    changed = False

    if "name" in sent_fields and body.name != current_user.name:
        current_user.name = body.name
        changed = True

    if "postcode" in sent_fields and body.postcode != current_user.postcode:
        current_user.postcode = body.postcode
        changed = True

    if "address_road" in sent_fields and body.address_road != current_user.address_road:
        current_user.address_road = body.address_road
        changed = True

    if (
        "address_detail" in sent_fields
        and body.address_detail != current_user.address_detail
    ):
        current_user.address_detail = body.address_detail
        changed = True

    if "gender" in sent_fields and body.gender != current_user.gender:
        current_user.gender = body.gender
        changed = True

    if "birthdate" in sent_fields and body.birthdate != current_user.birthdate:
        current_user.birthdate = body.birthdate
        changed = True

    if "marketing_consent" in sent_fields and body.marketing_consent is not None:
        # 단일 토글 — True면 동의 시각 기록, False면 동의 해제 + 철회 시각 박제.
        # 이미 동일 상태면 시각을 덮어쓰지 않는다(불필요한 audit 노이즈 방지).
        currently_consented = current_user.marketing_consent_at is not None
        if body.marketing_consent and not currently_consented:
            current_user.marketing_consent_at = datetime.now(tz=timezone.utc)
            changed = True
        elif not body.marketing_consent and currently_consented:
            current_user.marketing_consent_at = None
            current_user.marketing_withdrawn_at = datetime.now(tz=timezone.utc)
            changed = True

    if "phone" in sent_fields and body.phone != current_user.phone:
        if body.phone is None:
            # 휴대폰은 가입 시 필수이므로 마이페이지에서 비울 수 없다.
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "PHONE_REQUIRED",
                    "message": "휴대폰 번호는 비울 수 없습니다.",
                },
            )
        if not body.phone_verification_token:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "SMS_TOKEN_INVALID",
                    "message": "휴대폰 인증이 필요합니다.",
                },
            )
        # 활성 다른 계정과 휴대폰 중복 — signup_user 패턴과 동일.
        # user/admin 멤버 완전 분리 — user 진영만 비교(관리자 휴대폰과 동일해도 허용).
        existing = await db.execute(
            select(User).where(
                User.phone == body.phone,
                User.role == "user",
                User.withdrawn_at.is_(None),
                User.id != current_user.id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "ACCOUNT_PHONE_DUPLICATE",
                    "message": "이미 사용 중인 휴대폰 번호입니다.",
                },
            )

        await verify_phone_change_token(
            phone_verification_token=body.phone_verification_token,
            expected_phone=body.phone,
            redis_url=settings.redis_url,
        )
        current_user.phone = body.phone
        current_user.phone_verified = True
        changed = True

    if changed:
        current_user.updated_at = datetime.now(tz=timezone.utc)
        await db.commit()
        logger.info("me.profile.updated", user_id=current_user.id)

    return Response(status_code=204)


@router.post("/me/password/change", status_code=200)
async def change_password_with_current(
    body: PasswordChangeWithCurrentRequest,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """기존 비밀번호 확인이 필요한 정규 비밀번호 변경.

    - 소셜 가입자(`password_hash IS NULL`) → 403 NO_PASSWORD_SET
      (`/me/password`로 최초 설정 유도)
    - argon2 검증 실패 → 401 AUTH_INVALID_CREDENTIALS + 실패 카운터 증가
    - 3회 실패 → 5분 락아웃, 429 AUTH_TEMPORARILY_LOCKED
      (login_user와 동일 정책. 키는 user_id 기준)
    - 성공 시 JWT/CSRF 쿠키 재발급(NFR-S4)
    """
    if current_user.password_hash is None:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "NO_PASSWORD_SET",
                "message": "소셜 가입 계정은 비밀번호를 먼저 설정해주세요.",
            },
        )

    fail_key = _PW_CHANGE_FAIL_KEY.format(user_id=current_user.id)
    lockout_key = _PW_CHANGE_LOCKOUT_KEY.format(user_id=current_user.id)

    async with _make_pw_rl_redis() as r:
        if await r.exists(lockout_key):
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "AUTH_TEMPORARILY_LOCKED",
                    "message": "잠시 후 다시 시도해주세요.",
                },
            )

    if not verify_password(body.current_password, current_user.password_hash):
        async with _make_pw_rl_redis() as r:
            count_raw = await r.get(fail_key)
            count = int(count_raw) + 1 if count_raw else 1
            await r.set(fail_key, str(count), ex=_PW_CHANGE_FAIL_WINDOW)
            if count >= _PW_CHANGE_BRUTE_THRESHOLD:
                await r.set(lockout_key, "1", ex=_PW_CHANGE_LOCKOUT_TTL)
                logger.warning(
                    "auth.password.change_brute_force",
                    user_id=current_user.id,
                    attempt_count=count,
                )
        raise HTTPException(
            status_code=401,
            detail={
                "code": "AUTH_INVALID_CREDENTIALS",
                "message": "현재 비밀번호가 일치하지 않습니다.",
            },
        )

    # 성공 — 카운터 초기화 + 해시 갱신 + 쿠키 재발급
    async with _make_pw_rl_redis() as r:
        await r.delete(fail_key)

    current_user.password_hash = hash_password(body.new_password)
    current_user.must_reset_password = False
    # 비밀번호 변경 시 단일 세션 nonce 회전 — 다른 기기에 남아있던 세션은 sid mismatch 로 자동 무효화.
    current_user.current_session_id = _secrets.token_urlsafe(24)
    current_user.updated_at = datetime.now(tz=timezone.utc)
    await db.commit()

    token = encode_session_jwt(
        user_id=current_user.id,
        role=current_user.role,
        subscription_status=current_user.subscription_status,
        persist=False,
        session_id=current_user.current_session_id,
    )
    response.set_cookie(
        key="denvia_session",
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=3600,
    )
    csrf_token = _secrets.token_urlsafe(32)
    response.set_cookie(
        key="denvia_csrf",
        value=csrf_token,
        httponly=False,
        secure=True,
        samesite="strict",
        max_age=3600,
    )

    logger.info("auth.password.changed", user_id=current_user.id)
    return {"ok": True}
