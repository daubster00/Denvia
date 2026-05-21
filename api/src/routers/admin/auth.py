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

import re
import secrets as _secrets
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.deps.auth import get_current_admin
from api.src.models.base import get_session
from api.src.models.user import User
from api.src.services.admin_board_service import BTMDESIGN_EMAIL
from api.src.services.auth_service import login_user
from api.src.settings import settings
from api.src.utils.argon2 import hash_password, verify_password
from api.src.utils.jwt import encode_admin_session_jwt

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin/auth", tags=["admin-auth"])

ADMIN_COOKIE_NAME = "denvia_admin_session"
ADMIN_CSRF_COOKIE_NAME = "denvia_admin_csrf"
ADMIN_COOKIE_PATH = "/api/v1/admin"
# CSRF 쿠키는 프론트 어드민 페이지(/admin/*)에서 document.cookie로 읽어야 하므로 path="/"
# 세션 쿠키는 API 경로에만 전송되도록 path="/api/v1/admin" 유지
ADMIN_CSRF_COOKIE_PATH = "/"
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
        path=ADMIN_CSRF_COOKIE_PATH,
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
        path=ADMIN_CSRF_COOKIE_PATH,
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
    # 마스터 권한 — btmdesign@naver.com 만 True. 게시판 상태 변경·등급 표시 등에서 사용.
    is_master: bool = False


class AdminProfileResponse(BaseModel):
    """관리자 본인 계정 페이지(/admin/account) 응답."""

    user_id: int
    email: str
    phone: str | None
    name: str | None
    role: str  # 항상 "admin"
    is_master: bool
    # 화면 표시용 등급 라벨 — "마스터" 또는 "관리자"
    grade_label: str


class AdminProfileUpdateRequest(BaseModel):
    """PATCH /api/v1/admin/auth/profile — 이메일·휴대폰·이름 부분 수정."""

    email: str | None = None
    phone: str | None = None
    name: str | None = None

    @field_validator("email")
    @classmethod
    def email_format(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("EMAIL_REQUIRED")
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("이메일 형식이 올바르지 않습니다.")
        return v.lower()

    @field_validator("phone")
    @classmethod
    def phone_format(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = re.sub(r"[^0-9]", "", v)
        if cleaned == "":
            return None  # 빈 입력은 NULL 처리(연락처는 관리자 계정에서 선택값)
        if not re.match(r"^010\d{8}$", cleaned):
            raise ValueError("올바른 휴대폰 번호를 입력하세요.")
        return cleaned

    @field_validator("name")
    @classmethod
    def name_trim(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class AdminPasswordChangeRequest(BaseModel):
    """POST /api/v1/admin/auth/password — 현재 비밀번호 확인 + 신규 비밀번호 교체."""

    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("PASSWORD_TOO_SHORT")
        return v


def _grade_label_for(email: str) -> tuple[bool, str]:
    """이메일로 마스터 여부 + 화면 표시용 라벨 산출."""
    is_master = email.lower() == BTMDESIGN_EMAIL.lower()
    return is_master, ("마스터" if is_master else "관리자")


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

    is_master, _ = _grade_label_for(user.email)
    return AdminMeResponse(
        user_id=user.id, email=user.email, role=user.role, is_master=is_master
    )


@router.post("/logout", status_code=200)
async def admin_logout(response: Response) -> dict:
    """관리자 로그아웃 — 쿠키 즉시 만료."""
    _clear_admin_cookies(response)
    return {"ok": True}


@router.get("/me", response_model=AdminMeResponse)
async def admin_me(admin: User = Depends(get_current_admin)) -> AdminMeResponse:
    """현재 관리자 세션 정보 (미인증 시 401)."""
    is_master, _ = _grade_label_for(admin.email)
    return AdminMeResponse(
        user_id=admin.id, email=admin.email, role=admin.role, is_master=is_master
    )


@router.get("/profile", response_model=AdminProfileResponse)
async def admin_get_profile(
    admin: User = Depends(get_current_admin),
) -> AdminProfileResponse:
    """관리자 본인 계정 정보 — /admin/account 페이지 진입 시 호출."""
    is_master, grade_label = _grade_label_for(admin.email)
    return AdminProfileResponse(
        user_id=admin.id,
        email=admin.email,
        phone=admin.phone,
        name=admin.name,
        role=admin.role,
        is_master=is_master,
        grade_label=grade_label,
    )


@router.patch("/profile", response_model=AdminProfileResponse)
async def admin_update_profile(
    body: AdminProfileUpdateRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_session),
) -> AdminProfileResponse:
    """관리자 본인 계정 정보 수정 — 이메일·휴대폰·이름.

    - 이메일은 활성 다른 사용자와 중복 불가 (409 ACCOUNT_EMAIL_DUPLICATE)
    - 휴대폰은 활성 다른 사용자와 중복 불가 (409 ACCOUNT_PHONE_DUPLICATE)
    - 비밀번호는 별도 POST /password 엔드포인트로 변경
    """
    sent_fields = body.model_fields_set
    changed = False

    if "email" in sent_fields and body.email is not None and body.email != admin.email:
        existing = await db.execute(
            select(User).where(
                User.email == body.email,
                User.withdrawn_at.is_(None),
                User.id != admin.id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "ACCOUNT_EMAIL_DUPLICATE",
                    "message": "이미 사용 중인 이메일입니다.",
                },
            )
        admin.email = body.email
        changed = True

    if "phone" in sent_fields and body.phone != admin.phone:
        if body.phone is not None:
            existing = await db.execute(
                select(User).where(
                    User.phone == body.phone,
                    User.withdrawn_at.is_(None),
                    User.id != admin.id,
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
        admin.phone = body.phone
        changed = True

    if "name" in sent_fields and body.name != admin.name:
        admin.name = body.name
        changed = True

    if changed:
        admin.updated_at = datetime.now(tz=timezone.utc)
        await db.commit()
        logger.info("admin.profile.updated", user_id=admin.id)

    is_master, grade_label = _grade_label_for(admin.email)
    return AdminProfileResponse(
        user_id=admin.id,
        email=admin.email,
        phone=admin.phone,
        name=admin.name,
        role=admin.role,
        is_master=is_master,
        grade_label=grade_label,
    )


@router.post("/password", status_code=200)
async def admin_change_password(
    body: AdminPasswordChangeRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """관리자 본인 비밀번호 변경 — 현재 비밀번호 확인 + 신규 비밀번호 교체.

    - argon2 검증 실패 시 401 AUTH_INVALID_CREDENTIALS
    - 신규 비밀번호 8자 미만은 422 (Pydantic validator)
    """
    if admin.password_hash is None:
        # 관리자 계정은 항상 자체 비밀번호를 가져야 한다(seed_admin이 보장). 방어용.
        raise HTTPException(
            status_code=403,
            detail={
                "code": "NO_PASSWORD_SET",
                "message": "비밀번호가 설정되어 있지 않습니다.",
            },
        )

    if not verify_password(body.current_password, admin.password_hash):
        logger.warning("admin.password.change_invalid_current", user_id=admin.id)
        raise HTTPException(
            status_code=401,
            detail={
                "code": "AUTH_INVALID_CREDENTIALS",
                "message": "현재 비밀번호가 일치하지 않습니다.",
            },
        )

    admin.password_hash = hash_password(body.new_password)
    admin.must_reset_password = False
    admin.updated_at = datetime.now(tz=timezone.utc)
    await db.commit()

    logger.info("admin.password.changed", user_id=admin.id)
    return {"ok": True}
