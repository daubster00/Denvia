"""인증 라우터 — SMS OTP · 회원가입 · 로그인 · 로그아웃 · OAuth."""

import secrets as _secrets
from datetime import datetime, timezone
from typing import Literal

import sentry_sdk
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.deps.auth import get_current_user
from api.src.integrations.auth_providers.base import (
    OAuthProviderInvalidResponse,
    OAuthProviderUnavailable,
    ProviderName,
)
from api.src.integrations.auth_providers.factory import get_provider
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
    OAuthCompleteRequest,
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
    oauth_callback,
    oauth_complete_phone_supplement,
    oauth_start,
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


# ── OAuth 3종 (Story 1.6) ────────────────────────────────────────────────────

_VALID_PROVIDERS: set[str] = {"kakao", "google", "naver"}


def _oauth_error_redirect(code: str) -> RedirectResponse:
    origin = settings.oauth_web_origin.rstrip("/")
    return RedirectResponse(
        url=f"{origin}/?oauth_error={code}",
        status_code=302,
    )


def _set_session_cookies(response: RedirectResponse, user: User, persist: bool = False) -> None:
    token = encode_session_jwt(
        user_id=user.id,
        role=user.role,
        subscription_status=user.subscription_status,
        persist=persist,
    )
    cookie_kwargs: dict = dict(
        key="denvia_session",
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    if persist:
        cookie_kwargs["max_age"] = 86400
    else:
        cookie_kwargs["max_age"] = 3600
    response.set_cookie(**cookie_kwargs)

    csrf_token = _secrets.token_urlsafe(32)
    response.set_cookie(
        key="denvia_csrf",
        value=csrf_token,
        httponly=False,
        secure=True,
        samesite="strict",
        max_age=cookie_kwargs["max_age"],
    )


@router.get("/oauth/{provider}/authorize")
async def oauth_authorize(
    provider: str,
    mode: Literal["login", "signup"] = Query(default="login"),
) -> RedirectResponse:
    """Provider 동의 페이지로 리다이렉트."""
    if provider not in _VALID_PROVIDERS:
        raise HTTPException(
            status_code=404,
            detail={"code": "OAUTH_PROVIDER_UNKNOWN", "message": "지원하지 않는 소셜 로그인입니다."},
        )
    p = get_provider(provider)
    url = await oauth_start(provider, mode, p, settings.redis_url)
    return RedirectResponse(url=url, status_code=302)


@router.get("/oauth/{provider}/callback")
async def oauth_callback_endpoint(
    provider: str,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    """Provider 콜백 — 302로 프론트로 복귀한다(성공·실패 모두)."""
    if provider not in _VALID_PROVIDERS:
        return _oauth_error_redirect("OAUTH_PROVIDER_UNKNOWN")

    # 사용자 취소
    if error:
        logger.info("auth.oauth.cancelled", provider=provider, trace_id="")
        return _oauth_error_redirect("OAUTH_CANCELLED")

    if not code or not state:
        return _oauth_error_redirect("OAUTH_STATE_INVALID")

    p = get_provider(provider)

    try:
        result = await oauth_callback(provider, code, state, p, settings.redis_url, db)
    except OAuthProviderUnavailable:
        logger.warning("auth.oauth.provider_unavailable", provider=provider, trace_id="")
        return _oauth_error_redirect("OAUTH_PROVIDER_UNAVAILABLE")
    except OAuthProviderInvalidResponse:
        logger.warning("auth.oauth.provider_invalid_response", provider=provider, trace_id="")
        return _oauth_error_redirect("OAUTH_PROVIDER_UNAVAILABLE")
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        code_val = detail.get("code", "OAUTH_STATE_INVALID")
        return _oauth_error_redirect(code_val)

    origin = settings.oauth_web_origin.rstrip("/")
    action = result.get("action")

    if action in ("login_completed", "signup_completed_full"):
        user_id = result["user_id"]
        # 쿠키 발급에 필요한 user 재로딩
        from sqlalchemy import select
        u_row = await db.execute(select(User).where(User.id == user_id))
        user = u_row.scalar_one_or_none()
        await db.commit()

        if user is None:
            return _oauth_error_redirect("OAUTH_STATE_INVALID")

        redirect_target = f"{origin}/" if action == "login_completed" else f"{origin}/signup/segment"
        redirect = RedirectResponse(url=redirect_target, status_code=302)
        _set_session_cookies(redirect, user, persist=False)
        return redirect

    if action == "signup_pending_phone":
        await db.commit()
        token = result["signup_pending_token"]
        return RedirectResponse(
            url=f"{origin}/signup/phone-verify?token={token}",
            status_code=302,
        )

    if action == "email_collision":
        await db.commit()
        return _oauth_error_redirect("OAUTH_EMAIL_COLLISION_WITH_EMAIL_SIGNUP")

    if action == "phone_collision":
        await db.commit()
        return _oauth_error_redirect("OAUTH_PHONE_COLLISION")

    # 방어적 분기
    return _oauth_error_redirect("OAUTH_STATE_INVALID")


@router.post("/oauth/complete", response_model=LoginResponse)
async def oauth_complete(
    body: OAuthCompleteRequest,
    response: Response,
    db: AsyncSession = Depends(get_session),
) -> LoginResponse:
    """SMS 보충 후 소셜 가입 확정 + JWT 쿠키 발급."""
    user = await oauth_complete_phone_supplement(
        signup_pending_token=body.signup_pending_token,
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
    csrf_token = _secrets.token_urlsafe(32)
    response.set_cookie(
        key="denvia_csrf",
        value=csrf_token,
        httponly=False,
        secure=True,
        samesite="strict",
        max_age=3600,
    )

    return LoginResponse(
        user_id=user.id,
        email=user.email,
        role=user.role,
        subscription_status=user.subscription_status,
    )
