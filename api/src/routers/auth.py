"""인증 라우터 — SMS OTP · 회원가입 · 로그인 · 로그아웃 · OAuth."""

import re
import secrets as _secrets
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import quote, urlparse

import sentry_sdk
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.deps.auth import get_current_user
from api.src.integrations.auth_providers.base import (
    OAuthProviderInvalidResponse,
    OAuthProviderUnavailable,
    ProviderName,
)
from api.src.integrations.auth_providers.factory import get_provider
from api.src.integrations.messaging.adapters import get_adapter as _get_messaging
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
from api.src.utils.jwt import (
    JWTDecodeError,
    SessionExpired,
    decode_session_jwt,
    encode_session_jwt,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _is_secure_env() -> bool:
    """cookie.secure 플래그 — production 환경에서만 True (로컬 HTTP 개발 시 False)."""
    return settings.environment.lower() in {"production", "staging"}


# ── SMS ──────────────────────────────────────────────────────────────────────

@router.post("/sms/send", response_model=SmsSendResponse)
async def sms_send(body: SmsSendRequest) -> SmsSendResponse:
    """SMS OTP 발송 — 60초 쿨다운, 시간당 최대 3회."""
    result = await send_sms_otp_flow(
        phone=body.phone,
        purpose=body.purpose,
        redis_url=settings.redis_url,
        messaging=_get_messaging(),
        expose_code=settings.messaging_provider == "stub",
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
        session_id=user.current_session_id,
    )

    secure = _is_secure_env()
    response.set_cookie(
        key="denvia_session",
        value=token,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
        max_age=3600,
    )
    # CSRF 쿠키 — JS가 읽어 헤더로 전송. samesite는 session 쿠키와 동일하게 lax로 통일
    # (strict일 경우 cross-site 리다이렉트 후 첫 요청에서 누락되어 double-submit 검증 실패).
    csrf_token = _secrets.token_urlsafe(32)
    response.set_cookie(
        key="denvia_csrf",
        value=csrf_token,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
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
        session_id=user.current_session_id,
    )

    secure = _is_secure_env()
    cookie_kwargs: dict = dict(
        key="denvia_session",
        value=token,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
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
        secure=secure,
        samesite="lax",
        path="/",
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
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_session),
) -> dict:
    """로그아웃 — 세션·CSRF 쿠키 삭제 + DB 의 current_session_id 도 비워 동일 쿠키 도용을 봉쇄."""
    secure = _is_secure_env()
    # DB 쪽 nonce 도 즉시 비운다. 쿠키만 만료시키면 같은 쿠키 값을 보존한 채 다른 디바이스가
    # 그대로 가져다 쓰는 시나리오가 남으므로, 단일 세션 매칭의 신뢰성을 위해 서버 nonce 도 끊는다.
    raw_cookie = request.cookies.get("denvia_session")
    if raw_cookie:
        try:
            payload = decode_session_jwt(raw_cookie)
        except (SessionExpired, JWTDecodeError):
            payload = None
        if payload is not None:
            user_id = int(payload["sub"])
            try:
                u_row = await db.execute(select(User).where(User.id == user_id))
                user = u_row.scalar_one_or_none()
                if user is not None:
                    user.current_session_id = None
                    await db.commit()
            except Exception:
                await db.rollback()

    response.set_cookie(
        key="denvia_session",
        value="",
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
        max_age=0,
    )
    response.set_cookie(
        key="denvia_csrf",
        value="",
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
        max_age=0,
    )
    return {"ok": True}


# ── OAuth 3종 (Story 1.6) ────────────────────────────────────────────────────

_VALID_PROVIDERS: set[str] = {"kakao", "google", "naver"}

# state / code 파라미터 길이 상한 — 이상치 입력 조기 거부 (provider 요청 낭비 방지)
_OAUTH_STATE_MAX_LEN = 512
_OAUTH_CODE_MAX_LEN = 2048
# 허용 경로 allowlist: /로 시작하되 두 번째 문자가 /이면 거부(프로토콜 상대 경로·open-redirect 방어)
_NEXT_PATH_RE = re.compile(r"^/(?!/)[a-zA-Z0-9/_\-\.]{0,255}$")


def _sanitized_origin() -> str:
    """oauth_web_origin 기본 검증 — scheme+host 이외 문자 제거."""
    parsed = urlparse(settings.oauth_web_origin)
    if not parsed.scheme or not parsed.netloc:
        # 설정 오류 — 로컬 기본값으로 폴백(운영 배포 시 settings에서 필수 값 강제).
        return "http://localhost:3000"
    return f"{parsed.scheme}://{parsed.netloc}"


def _oauth_error_redirect(code: str) -> RedirectResponse:
    origin = _sanitized_origin()
    # code는 서버가 고정 발행한 상수 — 추가 검증 불필요하나 방어적으로 quote.
    return RedirectResponse(
        url=f"{origin}/?oauth_error={quote(code, safe='')}",
        status_code=302,
    )


def _set_session_cookies(response: RedirectResponse, user: User, persist: bool = False) -> None:
    token = encode_session_jwt(
        user_id=user.id,
        role=user.role,
        subscription_status=user.subscription_status,
        persist=persist,
        session_id=user.current_session_id,
    )
    secure = _is_secure_env()
    max_age = 86400 if persist else 3600
    response.set_cookie(
        key="denvia_session",
        value=token,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
        max_age=max_age,
    )

    csrf_token = _secrets.token_urlsafe(32)
    response.set_cookie(
        key="denvia_csrf",
        value=csrf_token,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
        max_age=max_age,
    )


def _safe_next(raw: str | None) -> str:
    """next 쿼리 값이 allowlist(/로 시작하는 상대 경로 + 안전 문자)를 통과하면 반환, 아니면 빈 문자열."""
    if not raw:
        return ""
    if _NEXT_PATH_RE.match(raw):
        return raw
    return ""


@router.get("/oauth/{provider}/authorize")
async def oauth_authorize(
    provider: str,
    mode: Literal["login", "signup"] = Query(default="login"),
    next: str | None = Query(default=None, alias="next"),
) -> RedirectResponse:
    """Provider 동의 페이지로 리다이렉트. 선택적 next 파라미터로 로그인 성공 후 리다이렉트 경로 지정."""
    if provider not in _VALID_PROVIDERS:
        raise HTTPException(
            status_code=404,
            detail={"code": "OAUTH_PROVIDER_UNKNOWN", "message": "지원하지 않는 소셜 로그인입니다."},
        )
    p = get_provider(provider)
    url = await oauth_start(
        provider, mode, p, settings.redis_url, next_path=_safe_next(next)
    )
    return RedirectResponse(url=url, status_code=302)


@router.get("/oauth/{provider}/callback")
async def oauth_callback_endpoint(
    provider: str,
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    db: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    """Provider 콜백 — 302로 프론트로 복귀한다(성공·실패 모두)."""
    if provider not in _VALID_PROVIDERS:
        return _oauth_error_redirect("OAUTH_PROVIDER_UNKNOWN")

    # AC-8: 사용자 취소는 access_denied로 좁혀 매핑. 그 외 provider 에러는 UNAVAILABLE로 구분.
    if error:
        # error 값·설명은 사용자 조작 가능 — 로그/리다이렉트 인젝션 방지
        safe_error = (error or "")[:64]
        safe_desc = (error_description or "")[:256]
        logger.info(
            "auth.oauth.provider_error",
            provider=provider,
            error=re.sub(r"[\x00-\x1f\x7f]", "", safe_error),
            error_description=re.sub(r"[\x00-\x1f\x7f]", "", safe_desc),
        )
        if safe_error == "access_denied":
            logger.info("auth.oauth.cancelled", provider=provider)
            return _oauth_error_redirect("OAUTH_CANCELLED")
        return _oauth_error_redirect("OAUTH_PROVIDER_UNAVAILABLE")

    if not code or not state:
        logger.warning("auth.oauth.state_invalid", provider=provider, reason="missing_params")
        return _oauth_error_redirect("OAUTH_STATE_INVALID")

    # 이상치 길이 거부 (공격자가 Provider 호출 비용을 낭비하는 것 방지)
    if len(state) > _OAUTH_STATE_MAX_LEN or len(code) > _OAUTH_CODE_MAX_LEN:
        logger.warning("auth.oauth.state_invalid", provider=provider, reason="oversize")
        return _oauth_error_redirect("OAUTH_STATE_INVALID")

    p = get_provider(provider)

    try:
        result = await oauth_callback(provider, code, state, p, settings.redis_url, db)
    except OAuthProviderUnavailable:
        logger.warning("auth.oauth.provider_unavailable", provider=provider)
        return _oauth_error_redirect("OAUTH_PROVIDER_UNAVAILABLE")
    except OAuthProviderInvalidResponse:
        # 스펙 AC-10 이벤트 카탈로그와 통합: provider 응답 스키마 이상도 UNAVAILABLE 범주로 로깅
        logger.warning("auth.oauth.provider_unavailable", provider=provider, reason="invalid_response")
        return _oauth_error_redirect("OAUTH_PROVIDER_UNAVAILABLE")
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        code_val = detail.get("code", "OAUTH_STATE_INVALID")
        return _oauth_error_redirect(code_val)
    except Exception:
        # 예상치 못한 예외는 500 HTML 누출 대신 UX-safe 302 리다이렉트로 귀결
        logger.exception("auth.oauth.callback_unexpected", provider=provider)
        try:
            await db.rollback()
        except Exception:
            pass
        return _oauth_error_redirect("OAUTH_PROVIDER_UNAVAILABLE")

    origin = _sanitized_origin()
    action = result.get("action")

    if action in ("login_completed", "signup_completed_full"):
        user_id = result["user_id"]
        # 쿠키 발급에 필요한 user 재로딩
        from sqlalchemy import select
        u_row = await db.execute(select(User).where(User.id == user_id))
        user = u_row.scalar_one_or_none()
        # Story 6.2 (편차 2): OAuth 로그인 성공 시 last_login_at 업데이트
        if user is not None and action == "login_completed":
            from datetime import datetime as _dt, timezone as _tz
            user.last_login_at = _dt.now(tz=_tz.utc)
            # 접속 통계용 login_events 적재 (admin 역할은 일반 OAuth 진입점에 안 옴 — 가드만).
            if user.role != "admin":
                from api.src.models.login_event import LoginEvent as _LoginEvent
                _ip = request.client.host if request.client else None
                _ua = request.headers.get("user-agent")
                db.add(
                    _LoginEvent(
                        user_id=user.id,
                        ip=_ip,
                        ua=_ua,
                        method=f"oauth_{provider}",
                        created_at=_dt.now(tz=_tz.utc),
                    )
                )
        # 단일 세션(later wins) — OAuth 로그인/가입에도 새 nonce 박제. 이전 쿠키는 자동 무효화.
        if user is not None:
            user.current_session_id = _secrets.token_urlsafe(24)
        await db.commit()

        # Story 6.5 — concurrent_ip_login 자동 탐지 hook (편차 3, OAuth 진입점)
        if user is not None and action == "login_completed":
            from api.src.services import anomaly_service as _anomaly_service
            from api.src.services.auth_service import _make_redis_rl as _make_rl
            ip = request.client.host if request.client else None
            ua = request.headers.get("user-agent")
            async with _make_rl(settings.redis_url) as r:
                await _anomaly_service.check_concurrent_ip_login(
                    ip=ip,
                    user_id=user.id,
                    ua=ua,
                    redis_rl=r,
                    db=db,
                    redis_pubsub=r,
                )
            try:
                await db.commit()
            except Exception:
                await db.rollback()

        if user is None:
            return _oauth_error_redirect("OAUTH_STATE_INVALID")

        # AC-3: login_completed일 때 state 저장된 next_path가 있으면 해당 경로로, 아니면 `/`.
        # signup_completed_full은 segment 단계로 고정 (가입 유형 설정 필요).
        next_path = _safe_next(result.get("next_path"))
        if action == "login_completed":
            redirect_target = f"{origin}{next_path}" if next_path else f"{origin}/"
        else:
            redirect_target = f"{origin}/signup/segment"
        redirect = RedirectResponse(url=redirect_target, status_code=302)
        _set_session_cookies(redirect, user, persist=False)
        return redirect

    if action == "signup_pending_phone":
        await db.commit()
        token = result["signup_pending_token"]
        return RedirectResponse(
            url=f"{origin}/signup/phone-verify?token={quote(token, safe='')}",
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
    # 단일 세션(later wins) — SMS 보충 후 첫 진입에 새 nonce 박제.
    user.current_session_id = _secrets.token_urlsafe(24)
    await db.commit()

    token = encode_session_jwt(
        user_id=user.id,
        role=user.role,
        subscription_status=user.subscription_status,
        session_id=user.current_session_id,
    )
    secure = _is_secure_env()
    response.set_cookie(
        key="denvia_session",
        value=token,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
        max_age=3600,
    )
    csrf_token = _secrets.token_urlsafe(32)
    response.set_cookie(
        key="denvia_csrf",
        value=csrf_token,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
        max_age=3600,
    )

    return LoginResponse(
        user_id=user.id,
        email=user.email,
        role=user.role,
        subscription_status=user.subscription_status,
    )
