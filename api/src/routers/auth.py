"""인증 라우터 — SMS OTP · 회원가입 · 로그인 · 로그아웃."""

import secrets as _secrets
from datetime import datetime, timezone

import sentry_sdk
import structlog
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.deps.auth import get_current_user
from api.src.integrations.messaging.adapters.stub import StubMessagingAdapter
from api.src.integrations.messaging.port import MessagingProvider
from api.src.models.base import get_session
from api.src.models.user import User
from api.src.schemas.auth import (
    FindIdRequest,
    FindIdResponse,
    FindPasswordRequest,
    LoginRequest,
    LoginResponse,
    SegmentRequest,
    SignupRequest,
    SmsSendRequest,
    SmsSendResponse,
    SmsVerifyRequest,
    SmsVerifyResponse,
)
from api.src.services.auth_service import (
    login_user,
    lookup_id,
    request_password_reset,
    send_sms_otp_flow,
    signup_user,
    verify_sms_otp_flow,
)
from api.src.settings import settings
from api.src.utils.jwt import encode_session_jwt

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _get_messaging() -> MessagingProvider:
    """메시징 어댑터 팩토리 — MESSAGING_PROVIDER 환경변수로 선택."""
    if settings.messaging_provider == "stub":
        return StubMessagingAdapter()
    # HOLD-MSG: 실 어댑터는 벤더 결정 후 구현
    return StubMessagingAdapter()


# ── SMS ──────────────────────────────────────────────────────────────────────

@router.post("/sms/send", response_model=SmsSendResponse)
async def sms_send(body: SmsSendRequest) -> SmsSendResponse:
    """SMS OTP 발송 — 60초 쿨다운, 시간당 최대 3회."""
    result = await send_sms_otp_flow(
        phone=body.phone,
        purpose=body.purpose,
        redis_url=settings.redis_url,
        messaging=_get_messaging(),
    )
    return SmsSendResponse(**result)


@router.post("/sms/verify", response_model=SmsVerifyResponse)
async def sms_verify(body: SmsVerifyRequest) -> SmsVerifyResponse:
    """SMS OTP 검증 — 성공 시 phone_verification_token 발급."""
    token = await verify_sms_otp_flow(
        phone=body.phone,
        code=body.code,
        purpose=body.purpose,
        redis_url=settings.redis_url,
    )
    return SmsVerifyResponse(phone_verification_token=token)


# ── Signup ────────────────────────────────────────────────────────────────────

@router.post("/signup", status_code=201)
async def signup(
    body: SignupRequest,
    response: Response,
    db: AsyncSession = Depends(get_session),
) -> dict:
    """이메일 회원가입 — argon2id 해시, JWT 쿠키 발급."""
    user = await signup_user(
        email=body.email,
        password=body.password,
        phone=body.phone,
        phone_verification_token=body.phone_verification_token,
        redis_url=settings.redis_url,
        db=db,
    )
    await db.commit()

    token = encode_session_jwt(
        user_id=user.id,
        role=user.role,
        subscription_status=user.subscription_status,
    )

    response.set_cookie(
        key="denvia_session",
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=3600,
    )
    # CSRF 쿠키 — JS가 읽어 헤더로 전송
    csrf_token = _secrets.token_urlsafe(32)
    response.set_cookie(
        key="denvia_csrf",
        value=csrf_token,
        httponly=False,
        secure=True,
        samesite="strict",
        max_age=3600,
    )

    return {
        "user_id": user.id,
        "email": user.email,
        "role": user.role,
        "subscription_status": user.subscription_status,
    }


# ── Login / Logout ─────────────────────────────────────────────────────────────

@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_session),
) -> LoginResponse:
    """이메일 로그인 — argon2id 검증, persist_session에 따라 쿠키 TTL 분기."""
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    user = await login_user(
        email=body.email,
        password=body.password,
        persist_session=body.persist_session,
        ip=ip,
        ua=ua,
        redis_url=settings.redis_url,
        db=db,
    )
    await db.commit()

    token = encode_session_jwt(
        user_id=user.id,
        role=user.role,
        subscription_status=user.subscription_status,
        persist=body.persist_session,
    )

    cookie_kwargs: dict = dict(
        key="denvia_session",
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    if body.persist_session:
        cookie_kwargs["max_age"] = 86400  # 1일
    # persist_session=False → max_age 생략 → 세션 쿠키 (브라우저 종료 시 만료)
    response.set_cookie(**cookie_kwargs)

    csrf_token = _secrets.token_urlsafe(32)
    response.set_cookie(
        key="denvia_csrf",
        value=csrf_token,
        httponly=False,
        secure=True,
        samesite="strict",
        **({"max_age": 86400} if body.persist_session else {}),
    )

    return LoginResponse(
        user_id=user.id,
        email=user.email,
        role=user.role,
        subscription_status=user.subscription_status,
    )


# ── 비밀번호 찾기 / 아이디 찾기 ──────────────────────────────────────────────

@router.post("/find-password", status_code=200)
async def find_password(
    body: FindPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict:
    """비밀번호 찾기 — SMS 임시 비밀번호 발송 (계정 열거 방지: 항상 200)."""
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    await request_password_reset(
        email=body.email,
        phone=body.phone,
        ip=ip,
        ua=ua,
        redis_url=settings.redis_url,
        db=db,
        messaging=_get_messaging(),
    )
    await db.commit()
    return {"ok": True}


@router.post("/find-id", response_model=FindIdResponse)
async def find_id(
    body: FindIdRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> FindIdResponse:
    """아이디(이메일) 찾기 — SMS 인증 토큰으로 이메일 마스킹 반환."""
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    result = await lookup_id(
        phone_verification_token=body.phone_verification_token,
        ip=ip,
        ua=ua,
        redis_url=settings.redis_url,
        db=db,
    )
    await db.commit()
    return FindIdResponse(**result)


@router.post("/logout", status_code=200)
async def logout(response: Response) -> dict:
    """로그아웃 — 세션·CSRF 쿠키 삭제."""
    response.set_cookie(
        key="denvia_session",
        value="",
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=0,
    )
    response.set_cookie(
        key="denvia_csrf",
        value="",
        httponly=False,
        secure=True,
        samesite="strict",
        max_age=0,
    )
    return {"ok": True}
