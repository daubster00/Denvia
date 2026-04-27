"""현재 세션 사용자 관련 엔드포인트."""

import secrets as _secrets
from datetime import datetime, timezone

import sentry_sdk
import structlog
from fastapi import APIRouter, Depends, HTTPException, Response
from redis.asyncio import Redis as AsyncRedis
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.deps.auth import get_current_user
from api.src.deps.redis import get_redis_quota, get_redis_runtime
from api.src.models.base import get_session
from api.src.models.user import User
from api.src.schemas.auth import PasswordChangeRequest, SegmentRequest, SessionUserResponse
from api.src.schemas.me import QuotaResponse
from api.src.services.qa_service import (
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
    """현재 사용자의 일일 Q&A 한도 현황을 반환한다 (AC-6)."""
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
