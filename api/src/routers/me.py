"""현재 세션 사용자 관련 엔드포인트."""

import secrets as _secrets
from datetime import datetime, timezone
from typing import Annotated, Literal

import sentry_sdk
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from redis.asyncio import Redis as AsyncRedis
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import desc, func, select

from api.src.deps.auth import get_current_user
from api.src.deps.redis import get_redis_quota, get_redis_runtime
from api.src.models.base import get_session
from api.src.models.billing_key import BillingKey
from api.src.models.payment import Payment
from api.src.models.qa_log import QALog
from api.src.models.user import User
from api.src.schemas.auth import PasswordChangeRequest, SegmentRequest, SessionUserResponse
from api.src.schemas.inbox import (
    ActivePopupResponse,
    InboxListResponse,
    UnreadCountResponse,
)
from api.src.schemas.me import (
    PaymentHistoryItem,
    PaymentHistoryResponse,
    QuotaResponse,
    UsageSummaryResponse,
)
from api.src.services import inbox_service
from api.src.services.qa_service import (
    ADMIN_UNLIMITED_LIMIT,
    _next_kst_midnight_iso,
    _resolve_bool,
    _resolve_daily_limit,
    _resolve_delay,
    _today_key_kst,
)
from api.src.utils.argon2 import hash_password
from api.src.utils.jwt import encode_session_jwt

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
    if current_user.subscription_status == "admin":
        return QuotaResponse(
            subscription_status="admin",
            daily_limit=ADMIN_UNLIMITED_LIMIT,
            used_today=0,
            remaining=ADMIN_UNLIMITED_LIMIT,
            reset_at=_next_kst_midnight_iso(),
            show_upgrade_prompt=False,
            show_subscribe_button=False,
            delay_seconds=0,
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
    return QuotaResponse(
        subscription_status=current_user.subscription_status,
        daily_limit=limit,
        used_today=used,
        remaining=max(limit - used, 0),
        reset_at=_next_kst_midnight_iso(),
        show_upgrade_prompt=show_upgrade,
        show_subscribe_button=show_subscribe,
        delay_seconds=delay,
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


@router.get("/me/inbox/unread-count", response_model=UnreadCountResponse)
async def get_my_inbox_unread_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> UnreadCountResponse:
    """TopNav 미읽음 뱃지용 카운트."""
    count = await inbox_service.get_unread_count(db, current_user.id)
    return UnreadCountResponse(unread_count=count)


@router.get("/me/popups/active", response_model=ActivePopupResponse | None)
async def get_active_popup(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> Response | ActivePopupResponse:
    """메인 진입 시 자동 노출 후보 1건. 매칭 0건은 204."""
    popup = await inbox_service.get_active_popup(db, current_user)
    if popup is None:
        return Response(status_code=204)
    return popup


@router.post("/me/popups/{popup_id}/seen", status_code=204)
async def mark_popup_seen(
    popup_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> Response:
    """팝업 X/ESC 클릭 시 inbox UPSERT — 동일 팝업 재노출 방지."""
    result = await inbox_service.mark_popup_seen(db, current_user.id, popup_id)
    if result == "not_found":
        raise HTTPException(
            status_code=404,
            detail={
                "code": "POPUP_NOT_FOUND",
                "message": "팝업을 찾을 수 없습니다.",
            },
        )
    logger.info(
        "popup.seen",
        user_id=current_user.id,
        popup_id=popup_id,
        was_first_view=(result == "inserted"),
    )
    return Response(status_code=204)


# ────────────────────────────────────────────────────────────────────────────
# (Existing) GET /me — 세션 유저 정보
# ────────────────────────────────────────────────────────────────────────────


@router.get("/me", response_model=SessionUserResponse)
async def get_me(current_user: User = Depends(get_current_user)) -> SessionUserResponse:
    """세션 쿠키에서 user_id를 꺼내 현재 사용자 정보를 snake_case로 반환한다."""
    return SessionUserResponse(
        user_id=current_user.id,
        email=current_user.email,
        role=current_user.role,
        subscription_status=current_user.subscription_status,
        segment=current_user.segment,
        years_of_experience=current_user.years_of_experience,
        must_reset_password=current_user.must_reset_password,
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
    """임시 비밀번호 → 신규 비밀번호 변경. JWT 및 CSRF 쿠키를 재발급한다."""
    current_user.password_hash = hash_password(body.new_password)
    current_user.must_reset_password = False
    current_user.updated_at = datetime.now(tz=timezone.utc)
    await db.commit()

    token = encode_session_jwt(
        user_id=current_user.id,
        role=current_user.role,
        subscription_status=current_user.subscription_status,
        persist=False,  # NFR-S4: 비밀번호 변경 시 비지속 세션 재발급
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
