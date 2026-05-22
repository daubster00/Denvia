"""세션 슬라이딩 미들웨어 — 활동 중에는 세션 쿠키 만료 시각을 매 요청마다 연장.

규칙:
- denvia_session / denvia_admin_session 쿠키가 유효(서명+만료)하면 응답 직전에 새 JWT 발급
- 라우터에서 이미 동일 쿠키를 Set-Cookie 한 경우(로그인/로그아웃/회원가입)는 건드리지 않음
- 만료·무효 토큰은 그대로 둠 (deps.auth가 401 처리)
- CSRF 쿠키도 같은 TTL로 max_age 재설정

JWT 갱신 비용은 HS256 sign 1회로 매우 작아 매 요청 적용 가능.
"""

from __future__ import annotations

import secrets as _secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from api.src.settings import settings
from api.src.utils.jwt import (
    ADMIN_SESSION_TTL,
    JWTDecodeError,
    SESSION_TTL_LONG,
    SESSION_TTL_SHORT,
    SessionExpired,
    decode_admin_session_jwt,
    decode_session_jwt,
    encode_admin_session_jwt,
    encode_session_jwt,
)

USER_SESSION_COOKIE = "denvia_session"
USER_CSRF_COOKIE = "denvia_csrf"
ADMIN_SESSION_COOKIE = "denvia_admin_session"
ADMIN_CSRF_COOKIE = "denvia_admin_csrf"

ADMIN_COOKIE_PATH = "/api/v1/admin"
ADMIN_CSRF_COOKIE_PATH = "/"


def _is_secure_env() -> bool:
    return settings.environment.lower() in {"production", "staging"}


def _response_sets_cookie(response: Response, cookie_name: str) -> bool:
    """응답 헤더에 cookie_name= 으로 시작하는 Set-Cookie가 이미 있는지 검사.

    라우터가 직접 쿠키를 발급한 경우(로그인 success, 로그아웃 expire 등) 미들웨어가 덮어쓰면 안 됨.
    """
    prefix = f"{cookie_name}="
    for raw in response.headers.getlist("set-cookie"):
        if raw.startswith(prefix):
            return True
    return False


class SessionRefreshMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1) 요청 시점의 세션 쿠키 사전 디코드 (유효한 것만 슬라이딩)
        user_token_raw = request.cookies.get(USER_SESSION_COOKIE)
        admin_token_raw = request.cookies.get(ADMIN_SESSION_COOKIE)

        user_payload: dict | None = None
        admin_payload: dict | None = None

        if user_token_raw:
            try:
                user_payload = decode_session_jwt(user_token_raw)
            except (SessionExpired, JWTDecodeError):
                user_payload = None

        if admin_token_raw:
            try:
                admin_payload = decode_admin_session_jwt(admin_token_raw)
            except (SessionExpired, JWTDecodeError):
                admin_payload = None

        response: Response = await call_next(request)

        secure = _is_secure_env()

        # 2) 유저 세션 슬라이딩 — 라우터가 직접 안 쓴 경우에만
        if user_payload is not None and not _response_sets_cookie(response, USER_SESSION_COOKIE):
            persist = bool(user_payload.get("persist", False))
            ttl = SESSION_TTL_LONG if persist else SESSION_TTL_SHORT
            new_token = encode_session_jwt(
                user_id=int(user_payload["sub"]),
                role=user_payload["role"],
                subscription_status=user_payload["sub_status"],
                persist=persist,
                # sid 는 단일 세션(later wins) 매칭용 — 슬라이딩 갱신 시 그대로 보존해야
                # 새 토큰도 users.current_session_id 와 동일하게 유지된다.
                session_id=user_payload.get("sid"),
            )
            cookie_kwargs: dict = dict(
                key=USER_SESSION_COOKIE,
                value=new_token,
                httponly=True,
                secure=secure,
                samesite="lax",
                path="/",
            )
            # persist=False는 브라우저 세션 쿠키 — max_age 생략. persist=True만 86400.
            if persist:
                cookie_kwargs["max_age"] = int(ttl.total_seconds())
            response.set_cookie(**cookie_kwargs)

            # CSRF 쿠키도 재발급되지 않은 경우 max_age 갱신 (값은 유지)
            if not _response_sets_cookie(response, USER_CSRF_COOKIE):
                existing_csrf = request.cookies.get(USER_CSRF_COOKIE)
                csrf_value = existing_csrf if existing_csrf else _secrets.token_urlsafe(32)
                csrf_kwargs: dict = dict(
                    key=USER_CSRF_COOKIE,
                    value=csrf_value,
                    httponly=False,
                    secure=secure,
                    samesite="lax",
                    path="/",
                )
                if persist:
                    csrf_kwargs["max_age"] = int(ttl.total_seconds())
                response.set_cookie(**csrf_kwargs)

        # 3) 관리자 세션 슬라이딩
        if admin_payload is not None and not _response_sets_cookie(response, ADMIN_SESSION_COOKIE):
            new_admin_token = encode_admin_session_jwt(user_id=int(admin_payload["sub"]))
            ttl_seconds = int(ADMIN_SESSION_TTL.total_seconds())
            response.set_cookie(
                key=ADMIN_SESSION_COOKIE,
                value=new_admin_token,
                httponly=True,
                secure=secure,
                samesite="lax",
                path=ADMIN_COOKIE_PATH,
                max_age=ttl_seconds,
            )
            if not _response_sets_cookie(response, ADMIN_CSRF_COOKIE):
                existing_admin_csrf = request.cookies.get(ADMIN_CSRF_COOKIE)
                csrf_value = existing_admin_csrf if existing_admin_csrf else _secrets.token_urlsafe(32)
                response.set_cookie(
                    key=ADMIN_CSRF_COOKIE,
                    value=csrf_value,
                    httponly=False,
                    secure=secure,
                    samesite="lax",
                    path=ADMIN_CSRF_COOKIE_PATH,
                    max_age=ttl_seconds,
                )

        return response
