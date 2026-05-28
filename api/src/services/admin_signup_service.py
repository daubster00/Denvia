"""Story 10.2 — 관리자 가입 신청(/admin/signup) 서비스.

2026-05-27 변경: 휴대폰 OTP 인증 단계 제거. 이름/이메일/연락처/비밀번호만으로 가입.
2026-05-28 변경: user/admin 멤버 완전 분리 — 이메일·연락처 중복은 활성 관리자(role='admin')
진영 내에서만 검사한다. 같은 이메일/휴대폰이 일반 사용자 계정에 존재해도 관리자 가입을 허용.
2026-05-28 변경: 신규 가입 알림톡(`admin.account.signup_request`) 발송 폐기.
master/operator는 /admin/admins 페이지에서 pending 항목을 직접 확인한다.
"""

from __future__ import annotations

import secrets as _secrets
from datetime import datetime, timezone

import structlog
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.user import User
from api.src.utils.argon2 import hash_password
from api.src.utils.mask import mask_email

logger = structlog.get_logger(__name__)


async def signup_admin_pending(
    *,
    name: str,
    email: str,
    password: str,
    phone: str,
    db: AsyncSession,
) -> User:
    """role='admin' + admin_grade='pending' 으로 INSERT.

    Raises:
        HTTPException 409 ACCOUNT_EMAIL_DUPLICATE — 활성 관리자 이메일 중복
        HTTPException 409 ACCOUNT_PHONE_DUPLICATE — 활성 관리자 연락처 중복
    """
    # 1) 이메일 중복 검사 — 활성 관리자 진영만(일반 사용자와 같은 이메일은 허용)
    existing_email = (
        await db.execute(
            select(User).where(
                User.email == email,
                User.role == "admin",
                User.withdrawn_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing_email is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "ACCOUNT_EMAIL_DUPLICATE",
                "message": "이미 사용 중인 이메일입니다.",
            },
        )

    # 2) 연락처 중복 검사 — 활성 관리자 진영만
    existing_phone = (
        await db.execute(
            select(User).where(
                User.phone == phone,
                User.role == "admin",
                User.withdrawn_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing_phone is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "ACCOUNT_PHONE_DUPLICATE",
                "message": "이미 사용 중인 연락처입니다.",
            },
        )

    now = datetime.now(tz=timezone.utc)
    user = User(
        email=email,
        phone=phone,
        name=name,
        password_hash=hash_password(password),
        # 휴대폰 OTP 인증을 받지 않으므로 phone_verified=False 로 INSERT.
        phone_verified=False,
        role="admin",
        admin_grade="pending",
        admin_signup_at=now,
        subscription_status="free",
        segment=None,
        # 단일 세션 nonce — pending 은 로그인 불가이나 컬럼 일관성을 위해 빈 nonce 발급.
        current_session_id=_secrets.token_urlsafe(24),
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    await db.flush()  # user.id 획득

    logger.info(
        "admin.signup.inserted",
        user_id=user.id,
        email_masked=mask_email(user.email),
    )
    return user


__all__ = ["signup_admin_pending"]
