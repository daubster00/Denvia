"""관리자 전용 인증 라우터 — 일반 사이트 로그인과 완전히 분리된 출입증.

엔드포인트:
- POST /api/v1/admin/auth/login   — 이메일+비밀번호 검증 → role=='admin'만 통과 → denvia_admin_session 쿠키
- POST /api/v1/admin/auth/logout  — denvia_admin_session 쿠키 즉시 만료
- GET  /api/v1/admin/auth/me      — 현재 관리자 세션 정보(미인증 시 401)

쿠키 정책:
- name: denvia_admin_session
- path: /api/v1/admin   (일반 사이트 요청에는 절대 동봉되지 않음)
- httponly + samesite=lax + 운영에서 secure
- TTL 1시간 고정 (persist 옵션 없음)
"""

from __future__ import annotations

import secrets as _secrets

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.deps.auth import get_current_admin
from api.src.models.base import get_session
from api.src.models.user import User
from api.src.schemas.auth import LoginRequest
from api.src.services.auth_service import login_user
from api.src.settings import settings
from api.src.utils.jwt import encode_admin_session_jwt

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin/auth", tags=["admin-auth"])

ADMIN_COOKIE_NAME = "denvia_admin_session"
ADMIN_CSRF_COOKIE_NAME = "denvia_admin_csrf"
ADMIN_COOKIE_PATH = "/api/v1/admin"
ADMIN_COOKIE_MAX_AGE = 3600  # 1시간


def _is_secure_env() -> bool:
    return settings.environment.lower() in {"production", "staging"}


def _set_admin_cookies(response: Response, token: str) -> None:
    secure = _is_secure_env()
    response.set_cookie(
        key=ADMIN_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=secure,
        samesite="lax",
        path=ADMIN_COOKIE_PATH,
        max_age=ADMIN_COOKIE_MAX_AGE,
    )
    csrf_token = _secrets.token_urlsafe(32)
    response.set_cookie(
        key=ADMIN_CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,
        secure=secure,
        samesite="lax",
        path=ADMIN_COOKIE_PATH,
        max_age=ADMIN_COOKIE_MAX_AGE,
    )


def _clear_admin_cookies(response: Response) -> None:
    secure = _is_secure_env()
    response.set_cookie(
        key=ADMIN_COOKIE_NAME,
        value="",
        httponly=True,
        secure=secure,
        samesite="lax",
        path=ADMIN_COOKIE_PATH,
        max_age=0,
    )
    response.set_cookie(
        key=ADMIN_CSRF_COOKIE_NAME,
        value="",
        httponly=False,
        secure=secure,
        samesite="lax",
        path=ADMIN_COOKIE_PATH,
        max_age=0,
    )


class AdminLoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def email_format(cls, v: str) -> str:
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("invalid email format")
        return v.lower().strip()


class AdminMeResponse(BaseModel):
    user_id: int
    email: str
    role: str  # 항상 "admin"


@router.post("/login", response_model=AdminMeResponse)
async def admin_login(
    body: AdminLoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_session),
) -> AdminMeResponse:
    """관리자 로그인 — 비밀번호 검증 + role=='admin' 확인.

    role이 'admin'이 아닌 경우에도 동일한 401 에러 코드를 반환해 계정 열거 방지.
    """
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    # 일반 로그인 서비스를 재사용 — argon2 검증·브루트포스 락아웃 정책 동일 적용
    user = await login_user(
        email=body.email,
        password=body.password,
        persist_session=False,
        ip=ip,
        ua=ua,
        redis_url=settings.redis_url,
        db=db,
    )
    await db.commit()

    if user.role != "admin":
        # 비-관리자 계정은 비밀번호 일치 여부와 무관하게 401(동일 메시지) — 관리자 계정 존재 노출 방지
        logger.warning(
            "admin.auth.non_admin_attempt",
            user_id=user.id,
            ip=ip,
        )
        raise HTTPException(
            status_code=401,
            detail={
                "code": "AUTH_INVALID_CREDENTIALS",
                "message": "이메일 또는 비밀번호가 일치하지 않습니다.",
            },
        )

    token = encode_admin_session_jwt(user_id=user.id)
    _set_admin_cookies(response, token)

    logger.info("admin.auth.login.success", user_id=user.id, ip=ip)

    return AdminMeResponse(user_id=user.id, email=user.email, role=user.role)


@router.post("/logout", status_code=200)
async def admin_logout(response: Response) -> dict:
    """관리자 로그아웃 — 쿠키 즉시 만료."""
    _clear_admin_cookies(response)
    return {"ok": True}


@router.get("/me", response_model=AdminMeResponse)
async def admin_me(admin: User = Depends(get_current_admin)) -> AdminMeResponse:
    """현재 관리자 세션 정보 (미인증 시 401)."""
    return AdminMeResponse(user_id=admin.id, email=admin.email, role=admin.role)
