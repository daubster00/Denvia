"""Story 10.2 — 관리자 가입 신청(/admin/signup) 서비스 + master/operator 알림톡 enqueue.

2026-05-27 변경: 휴대폰 OTP 인증 단계 제거. 이름/이메일/연락처/비밀번호만으로 가입.
2026-05-28 변경: user/admin 멤버 완전 분리 — 이메일·연락처 중복은 활성 관리자(role='admin')
진영 내에서만 검사한다. 같은 이메일/휴대폰이 일반 사용자 계정에 존재해도 관리자 가입을 허용.
"""

from __future__ import annotations

import secrets as _secrets
from datetime import datetime, timezone

import structlog
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.notification_queue import (
    CHANNEL_ALIMTALK,
    STATUS_QUEUED,
    NotificationQueue,
)
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


async def enqueue_admin_signup_request_alert(
    *,
    db: AsyncSession,
    new_admin_user_id: int,
) -> int:
    """master/operator 활성 관리자(휴대폰 있음)에게 admin.account.signup_request 알림톡 enqueue.

    Returns:
        enqueue 시도한 row 수 (멱등 키 충돌은 silent — 동일 신청·동일 수신자는 1행만 유지).
    """
    new_admin = (
        await db.execute(select(User).where(User.id == new_admin_user_id))
    ).scalar_one_or_none()
    if new_admin is None:
        logger.warning("admin.signup.alert.applicant_not_found", user_id=new_admin_user_id)
        return 0

    recipients = (
        await db.execute(
            select(User).where(
                User.role == "admin",
                User.admin_grade.in_(("master", "operator")),
                User.withdrawn_at.is_(None),
                User.phone.is_not(None),
            )
        )
    ).scalars().all()

    if not recipients:
        logger.info("admin.signup.alert.no_recipients", user_id=new_admin_user_id)
        return 0

    applicant_email_masked = mask_email(new_admin.email)
    # KST 표시 — 알림톡 본문은 사람이 읽으므로 +09:00 변환.
    from datetime import timedelta as _td

    applied_at = new_admin.admin_signup_at or datetime.now(tz=timezone.utc)
    if applied_at.tzinfo is None:
        applied_at = applied_at.replace(tzinfo=timezone.utc)
    applied_at_kst = (applied_at + _td(hours=9)).strftime("%Y-%m-%d %H:%M")

    now_naive = datetime.now(tz=timezone.utc).replace(tzinfo=None)
    enqueued = 0
    for admin in recipients:
        stmt = (
            pg_insert(NotificationQueue)
            .values(
                user_id=admin.id,
                template_code="admin.account.signup_request",
                variables={
                    "applicant_email_masked": applicant_email_masked,
                    "applied_at_kst": applied_at_kst,
                },
                channel=CHANNEL_ALIMTALK,
                status=STATUS_QUEUED,
                attempts=0,
                idempotency_key=f"admin_signup:{new_admin_user_id}:{admin.id}",
                created_at=now_naive,
            )
            .on_conflict_do_nothing(
                index_elements=["user_id", "template_code", "idempotency_key"],
                index_where=NotificationQueue.user_id.is_not(None),
            )
        )
        try:
            await db.execute(stmt)
            enqueued += 1
        except Exception:
            logger.error(
                "admin.signup.alert.enqueue_failed",
                user_id=new_admin_user_id,
                admin_user_id=admin.id,
                exc_info=True,
            )

    logger.info(
        "admin.signup.alert.enqueued",
        user_id=new_admin_user_id,
        recipients=enqueued,
    )
    return enqueued


__all__ = [
    "signup_admin_pending",
    "enqueue_admin_signup_request_alert",
]
