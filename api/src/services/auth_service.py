"""인증 서비스 — SMS OTP, 회원가입, 로그인 비즈니스 로직."""

import hashlib
import json
import random
import secrets
import string
from datetime import datetime, timezone
from typing import Literal, TypedDict

import sentry_sdk
import structlog
from fastapi import HTTPException
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.integrations.auth_providers.base import (
    OAuthProvider,
    OAuthProviderUnavailable,
    ProviderName,
)
from api.src.integrations.messaging.port import MessagingProvider
from api.src.models.anomaly_event import AnomalyEvent
from api.src.models.oauth_identity import OAuthIdentity
from api.src.models.user import User
from api.src.settings import REDIS_DB_OTP, REDIS_DB_RATE_LIMIT
from api.src.utils.argon2 import hash_password, verify_password
from api.src.utils.jwt import encode_session_jwt
from api.src.utils.mask import mask_email

logger = structlog.get_logger(__name__)

# Redis 키 패턴
_OTP_KEY = "otp:{purpose}:{phone}"
_COOLDOWN_KEY = "otp_cooldown:{purpose}:{phone}"
_RETRY_COUNT_KEY = "otp_retry_count:{purpose}:{phone}"
_TOKEN_KEY = "phone_token:{token}"

_OTP_TTL = 300       # 5분
_COOLDOWN_TTL = 60   # 60초
_RETRY_WINDOW = 3600  # 1시간
_MAX_RETRIES = 3      # 시간당 최대 발송 횟수 (4번째 = 429)
_MAX_WRONG = 3        # OTP 불일치 최대 횟수
_TOKEN_TTL = 600      # phone_verification_token 10분


def _make_redis(base_url: str) -> Redis:
    return Redis.from_url(f"{base_url}/{REDIS_DB_OTP}", decode_responses=True)


def _make_redis_rl(base_url: str) -> Redis:
    """Rate Limit DB (DB 2) — 브루트포스 카운터·락아웃."""
    return Redis.from_url(f"{base_url}/{REDIS_DB_RATE_LIMIT}", decode_responses=True)


# Recovery 관련 Redis 키 (DB 2 공유)
_RECOVERY_KEY = "recovery_attempts:{phone}"
_RECOVERY_TTL = 3600
_RECOVERY_ABUSE_THRESHOLD = 4

# 타이밍 균일화용 dummy 해시 (argon2id verify 1회 소모)
_DUMMY_HASH = "$argon2id$v=19$m=65536,t=3,p=4$dummyhash0000000000000000$dummyhash0000000000000000000000000000000000"

# 브루트포스 Redis 키
_LOGIN_FAIL_KEY = "login_fail:{email}"
_LOGIN_LOCKOUT_KEY = "login_lockout:{email}"
_LOGIN_LOCKOUT_TTL = 300   # 5분
_LOGIN_FAIL_WINDOW = 300   # 카운터 TTL도 5분 (성공 시 초기화)
_LOGIN_BRUTE_THRESHOLD = 3  # 3회 이상 실패 → anomaly + 4번째부터 lockout


def _otp_keys(purpose: str, phone: str) -> tuple[str, str, str]:
    return (
        _OTP_KEY.format(purpose=purpose, phone=phone),
        _COOLDOWN_KEY.format(purpose=purpose, phone=phone),
        _RETRY_COUNT_KEY.format(purpose=purpose, phone=phone),
    )


async def send_sms_otp_flow(
    phone: str,
    purpose: str,
    redis_url: str,
    messaging: MessagingProvider,
) -> dict:
    """SMS OTP 발송 플로우.

    Returns:
        {"sent_at": iso_str, "cooldown_seconds": 60, "max_retries": 3}

    Raises:
        HTTPException 429 SMS_COOLDOWN_ACTIVE — 60초 쿨다운 중
        HTTPException 429 SMS_MAX_RETRIES_EXCEEDED — 시간당 4회 초과
    """
    otp_key, cooldown_key, retry_key = _otp_keys(purpose, phone)

    async with _make_redis(redis_url) as r:
        # 쿨다운 확인
        if await r.exists(cooldown_key):
            raise HTTPException(
                status_code=429,
                detail={"code": "SMS_COOLDOWN_ACTIVE", "message": "잠시 후 다시 요청해주세요."},
            )

        # 시간당 재시도 횟수 확인
        count_raw = await r.get(retry_key)
        count = int(count_raw) if count_raw else 0
        if count >= _MAX_RETRIES:
            raise HTTPException(
                status_code=429,
                detail={"code": "SMS_MAX_RETRIES_EXCEEDED", "message": "인증번호 발송 한도를 초과했습니다. 1시간 후 다시 시도해주세요."},
            )

        # OTP 생성 및 저장
        otp = "".join(random.choices(string.digits, k=6))
        pipe = r.pipeline()
        pipe.set(otp_key, otp, ex=_OTP_TTL)
        # wrong-count 키도 초기화
        wrong_key = f"otp_wrong:{purpose}:{phone}"
        pipe.delete(wrong_key)
        pipe.set(cooldown_key, "1", ex=_COOLDOWN_TTL)
        if count == 0:
            pipe.set(retry_key, "1", ex=_RETRY_WINDOW)
        else:
            pipe.incr(retry_key)
        await pipe.execute()

    await messaging.send_sms_otp(phone, otp)
    sent_at = datetime.now(tz=timezone.utc).isoformat()

    logger.info("auth.sms_otp.sent", phone=f"****{phone[-4:]}", purpose=purpose)

    return {"sent_at": sent_at, "cooldown_seconds": _COOLDOWN_TTL, "max_retries": _MAX_RETRIES}


async def verify_sms_otp_flow(
    phone: str,
    code: str,
    purpose: str,
    redis_url: str,
) -> str:
    """SMS OTP 검증 플로우.

    Returns:
        phone_verification_token (UUID 문자열)

    Raises:
        HTTPException 400 SMS_CODE_INVALID — OTP 불일치
        HTTPException 400 SMS_SESSION_EXPIRED — OTP 없음/만료
        HTTPException 400 SMS_MAX_WRONG_ATTEMPTS — 3회 오류 후 무효화
    """
    otp_key, _, _ = _otp_keys(purpose, phone)
    wrong_key = f"otp_wrong:{purpose}:{phone}"

    async with _make_redis(redis_url) as r:
        # 저장된 OTP 조회
        stored_otp = await r.get(otp_key)
        if stored_otp is None:
            raise HTTPException(
                status_code=400,
                detail={"code": "SMS_SESSION_EXPIRED", "message": "인증번호가 만료되었습니다. 다시 요청해주세요."},
            )

        # 불일치 횟수 확인
        wrong_raw = await r.get(wrong_key)
        wrong_count = int(wrong_raw) if wrong_raw else 0
        if wrong_count >= _MAX_WRONG:
            await r.delete(otp_key)
            raise HTTPException(
                status_code=400,
                detail={"code": "SMS_MAX_WRONG_ATTEMPTS", "message": "인증 시도 횟수를 초과했습니다. 인증번호를 다시 요청해주세요."},
            )

        # OTP 검증
        if stored_otp != code:
            new_wrong = wrong_count + 1
            if new_wrong >= _MAX_WRONG:
                await r.delete(otp_key)
                await r.delete(wrong_key)
                raise HTTPException(
                    status_code=400,
                    detail={"code": "SMS_MAX_WRONG_ATTEMPTS", "message": "인증 시도 횟수를 초과했습니다. 인증번호를 다시 요청해주세요."},
                )
            await r.set(wrong_key, str(new_wrong), ex=_OTP_TTL)
            raise HTTPException(
                status_code=400,
                detail={"code": "SMS_CODE_INVALID", "message": "인증번호가 일치하지 않습니다."},
            )

        # OTP 사용 완료 → 삭제
        await r.delete(otp_key)
        await r.delete(wrong_key)

        # phone_verification_token 발급
        token = secrets.token_urlsafe(32)
        token_key = _TOKEN_KEY.format(token=token)
        await r.set(token_key, phone, ex=_TOKEN_TTL)

    logger.info("auth.sms_otp.verified", phone=f"****{phone[-4:]}", purpose=purpose)
    return token


async def signup_user(
    email: str,
    password: str,
    phone: str,
    phone_verification_token: str,
    redis_url: str,
    db: AsyncSession,
) -> User:
    """회원가입 처리.

    Returns:
        생성된 User 객체

    Raises:
        HTTPException 400 SMS_TOKEN_INVALID — phone_verification_token 검증 실패
        HTTPException 409 ACCOUNT_EMAIL_DUPLICATE / ACCOUNT_PHONE_DUPLICATE
    """
    # phone_verification_token 검증
    token_key = _TOKEN_KEY.format(token=phone_verification_token)
    async with _make_redis(redis_url) as r:
        stored_phone = await r.get(token_key)
        if stored_phone is None or stored_phone != phone:
            raise HTTPException(
                status_code=400,
                detail={"code": "SMS_TOKEN_INVALID", "message": "휴대폰 인증이 필요합니다."},
            )
        # 토큰 즉시 소진
        await r.delete(token_key)

    # 이메일 중복 검사
    existing_email = await db.execute(
        select(User).where(User.email == email, User.withdrawn_at.is_(None))
    )
    if existing_email.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail={"code": "ACCOUNT_EMAIL_DUPLICATE", "message": "이미 존재하는 정보입니다. 로그인해주세요."},
        )

    # 휴대폰 중복 검사
    existing_phone = await db.execute(
        select(User).where(User.phone == phone, User.withdrawn_at.is_(None))
    )
    if existing_phone.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail={"code": "ACCOUNT_PHONE_DUPLICATE", "message": "이미 존재하는 정보입니다. 로그인해주세요."},
        )

    # 비밀번호 해싱
    password_hash = hash_password(password)

    now = datetime.now(tz=timezone.utc)
    user = User(
        email=email,
        phone=phone,
        password_hash=password_hash,
        phone_verified=True,
        subscription_status="free",
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    await db.flush()  # id 획득

    sentry_sdk.add_breadcrumb(
        message="auth.signup.completed",
        data={"user_id": user.id, "trace_id": ""},
    )
    logger.info(
        "auth.signup.completed",
        user_id=user.id,
    )

    return user


async def login_user(
    email: str,
    password: str,
    persist_session: bool,
    ip: str | None,
    ua: str | None,
    redis_url: str,
    db: AsyncSession,
) -> User:
    """이메일 로그인 처리.

    Returns:
        인증된 User 객체

    Raises:
        HTTPException 429 AUTH_TEMPORARILY_LOCKED — 락아웃 중
        HTTPException 401 AUTH_INVALID_CREDENTIALS — 인증 실패 (이메일 존재 여부 비노출)
    """
    fail_key = _LOGIN_FAIL_KEY.format(email=email)
    lockout_key = _LOGIN_LOCKOUT_KEY.format(email=email)

    # 락아웃 체크
    async with _make_redis_rl(redis_url) as r:
        if await r.exists(lockout_key):
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "AUTH_TEMPORARILY_LOCKED",
                    "message": "잠시 후 다시 시도해주세요.",
                },
            )

    # 사용자 조회 (이메일 미존재 시에도 동일 에러 반환 — timing-safe)
    result = await db.execute(
        select(User).where(User.email == email, User.withdrawn_at.is_(None))
    )
    user = result.scalar_one_or_none()

    # 비밀번호 검증 (미존재 시 dummy 검증으로 timing 균일화)
    password_correct = False
    if user is not None and user.password_hash is not None:
        password_correct = verify_password(password, user.password_hash)
    else:
        # dummy 검증 — timing attack 방지
        verify_password(password, "$argon2id$v=19$m=65536,t=3,p=4$dummyhash0000000000000000$dummyhash0000000000000000000000000000000000")

    if not password_correct:
        # 실패 카운터 증가
        async with _make_redis_rl(redis_url) as r:
            count_raw = await r.get(fail_key)
            count = int(count_raw) + 1 if count_raw else 1
            await r.set(fail_key, str(count), ex=_LOGIN_FAIL_WINDOW)

            if count >= _LOGIN_BRUTE_THRESHOLD:
                # anomaly_events INSERT (3회째부터)
                now = datetime.now(tz=timezone.utc)
                event = AnomalyEvent(
                    type="login_brute_force",
                    target_user_id=user.id if user else None,
                    ip=ip,
                    ua=ua,
                    details={"attempt_count": count},
                    status="new",
                    created_at=now,
                )
                db.add(event)
                try:
                    await db.flush()
                except Exception:
                    await db.rollback()

                # 4회째부터 lockout (3회째 기록 후 다음 요청부터 차단)
                await r.set(lockout_key, "1", ex=_LOGIN_LOCKOUT_TTL)

                logger.warning(
                    "auth.login.brute_force",
                    email=f"****{email[-4:]}",
                    attempt_count=count,
                    ip=ip,
                )

        raise HTTPException(
            status_code=401,
            detail={
                "code": "AUTH_INVALID_CREDENTIALS",
                "message": "이메일 또는 비밀번호가 일치하지 않습니다.",
            },
        )

    # 로그인 성공 — 실패 카운터 초기화
    async with _make_redis_rl(redis_url) as r:
        await r.delete(fail_key)

    logger.info(
        "auth.login.success",
        user_id=user.id,
        persist=persist_session,
    )

    return user


async def _check_recovery_abuse(
    phone: str,
    endpoint: str,
    ip: str | None,
    ua: str | None,
    redis_url: str,
    db: AsyncSession,
) -> None:
    """복구 요청 횟수를 카운트하고 남용 임계 도달 시 anomaly_events에 기록한다."""
    recovery_key = _RECOVERY_KEY.format(phone=phone)
    async with _make_redis_rl(redis_url) as r:
        count_raw = await r.get(recovery_key)
        count = int(count_raw) + 1 if count_raw else 1
        if count_raw is None:
            await r.set(recovery_key, str(count), ex=_RECOVERY_TTL)
        else:
            await r.incr(recovery_key)

        if count >= _RECOVERY_ABUSE_THRESHOLD:
            now = datetime.now(tz=timezone.utc)
            event = AnomalyEvent(
                type="recovery_abuse",
                target_user_id=None,
                ip=ip,
                ua=ua,
                details={
                    "phone_tail": phone[-4:],
                    "attempt_count": count,
                    "endpoint": endpoint,
                },
                status="new",
                created_at=now,
            )
            db.add(event)
            try:
                await db.flush()
            except Exception:
                await db.rollback()


async def request_password_reset(
    email: str,
    phone: str,
    ip: str | None,
    ua: str | None,
    redis_url: str,
    db: AsyncSession,
    messaging: MessagingProvider,
) -> None:
    """비밀번호 찾기 처리 — SMS 임시 비밀번호 발송.

    계정 열거 방지: 일치/불일치/소셜 전용 모두 동일 200 응답.
    타이밍 균일화: 불일치/소셜 분기에서도 dummy argon2 1회 수행.
    """
    # 이상탐지 카운터 (응답 변경 없음)
    await _check_recovery_abuse(phone, "find-password", ip, ua, redis_url, db)

    # DB 조회
    result = await db.execute(
        select(User).where(
            User.email == email,
            User.phone == phone,
            User.withdrawn_at.is_(None),
        )
    )
    user = result.scalar_one_or_none()

    matched = user is not None

    if matched and user.password_hash is not None:
        # 8자리 임시 비밀번호 생성
        temp_password = "".join(
            secrets.choice(string.ascii_letters + string.digits) for _ in range(8)
        )
        user.password_hash = hash_password(temp_password)
        user.must_reset_password = True
        user.updated_at = datetime.now(tz=timezone.utc)

        body = f"Denvia 임시 비밀번호: {temp_password} (로그인 후 즉시 변경됩니다)"
        await messaging.send_sms(phone, body)

        logger.info(
            "auth.password_reset.requested",
            phone=f"****{phone[-4:]}",
            matched=True,
            trace_id="",
        )
    elif matched and user.password_hash is None:
        # 소셜 전용 계정 — dummy argon2 타이밍 균일화
        verify_password("dummy", _DUMMY_HASH)
        logger.info(
            "auth.password_reset.skipped_social",
            phone=f"****{phone[-4:]}",
            trace_id="",
        )
        logger.info(
            "auth.password_reset.requested",
            phone=f"****{phone[-4:]}",
            matched=False,
            trace_id="",
        )
    else:
        # 불일치 — dummy argon2 타이밍 균일화
        verify_password("dummy", _DUMMY_HASH)
        logger.info(
            "auth.password_reset.requested",
            phone=f"****{phone[-4:]}",
            matched=False,
            trace_id="",
        )


async def lookup_id(
    phone_verification_token: str,
    ip: str | None,
    ua: str | None,
    redis_url: str,
    db: AsyncSession,
) -> dict:
    """아이디(이메일) 찾기 — SMS OTP 인증 후 이메일 마스킹 반환.

    Raises:
        HTTPException 400 SMS_TOKEN_INVALID — 토큰 없음/재사용
    """
    token_key = _TOKEN_KEY.format(token=phone_verification_token)
    async with _make_redis(redis_url) as r:
        phone = await r.get(token_key)
        if phone is None:
            raise HTTPException(
                status_code=400,
                detail={"code": "SMS_TOKEN_INVALID", "message": "휴대폰 인증이 필요합니다."},
            )
        # 토큰 즉시 소진 (1회용)
        await r.delete(token_key)

    # 이상탐지 카운터 (응답 변경 없음)
    await _check_recovery_abuse(phone, "find-id", ip, ua, redis_url, db)

    result = await db.execute(
        select(User).where(
            User.phone == phone,
            User.withdrawn_at.is_(None),
        )
    )
    user = result.scalar_one_or_none()

    matched = user is not None

    logger.info(
        "auth.id_lookup.requested",
        phone=f"****{phone[-4:]}",
        matched=matched,
        trace_id="",
    )

    if not matched:
        return {"email_masked": None, "signup_method": None}

    email_masked = mask_email(user.email)

    # signup_method 결정 — Story 1.6에서 4값으로 확장
    if user.password_hash is not None:
        signup_method: str = "email"
    else:
        oi_row = await db.execute(
            select(OAuthIdentity.provider)
            .where(OAuthIdentity.user_id == user.id)
            .order_by(OAuthIdentity.id.asc())
            .limit(1)
        )
        provider = oi_row.scalar_one_or_none()
        signup_method = provider if provider in {"kakao", "google", "naver"} else "social"

    return {"email_masked": email_masked, "signup_method": signup_method}


# ── OAuth 3종 (Story 1.6) ────────────────────────────────────────────────────

REDIS_DB_OAUTH_STATE = REDIS_DB_RATE_LIMIT  # DB 2 공용 (일시성 도메인)

_OAUTH_STATE_KEY = "oauth_state:{state}"
_OAUTH_STATE_TTL = 600  # 10분
_SIGNUP_PENDING_KEY = "signup_pending:{token}"
_SIGNUP_PENDING_TTL = 600  # 10분


class OAuthCallbackResult(TypedDict, total=False):
    action: Literal[
        "login_completed",
        "signup_completed_full",
        "signup_pending_phone",
        "email_collision",
        "phone_collision",
    ]
    user_id: int
    signup_pending_token: str
    provider: str


def _sub_hash(sub: str) -> str:
    return hashlib.sha256(sub.encode("utf-8")).hexdigest()[:16]


async def oauth_start(
    provider_name: ProviderName,
    mode: Literal["login", "signup"],
    provider: OAuthProvider,
    redis_url: str,
) -> str:
    """OAuth authorize URL 생성 — state 32B nonce를 Redis DB 2에 기록."""
    state = secrets.token_urlsafe(32)
    key = _OAUTH_STATE_KEY.format(state=state)
    payload = json.dumps({"provider": provider_name, "mode": mode})
    async with _make_redis_rl(redis_url) as r:
        await r.set(key, payload, ex=_OAUTH_STATE_TTL)
    return provider.get_authorization_url(state=state)


async def _consume_oauth_state(state: str, provider_name: str, redis_url: str) -> dict:
    """state 검증 + 즉시 삭제. 없거나 provider 불일치면 OAUTH_STATE_INVALID."""
    key = _OAUTH_STATE_KEY.format(state=state)
    async with _make_redis_rl(redis_url) as r:
        raw = await r.get(key)
        if raw is None:
            raise HTTPException(
                status_code=400,
                detail={"code": "OAUTH_STATE_INVALID", "message": "소셜 로그인 세션이 만료되었습니다."},
            )
        await r.delete(key)

    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail={"code": "OAUTH_STATE_INVALID", "message": "소셜 로그인 세션이 만료되었습니다."},
        )

    if payload.get("provider") != provider_name:
        raise HTTPException(
            status_code=400,
            detail={"code": "OAUTH_STATE_INVALID", "message": "소셜 로그인 세션이 만료되었습니다."},
        )
    return payload


async def oauth_callback(
    provider_name: ProviderName,
    code: str,
    state: str,
    provider: OAuthProvider,
    redis_url: str,
    db: AsyncSession,
) -> OAuthCallbackResult:
    """OAuth 콜백 — state 검증 후 분기 결과를 반환.

    action 종류:
        - login_completed: (user_id)
        - signup_completed_full: (user_id)
        - signup_pending_phone: (signup_pending_token)
        - email_collision: 자체 가입자 이메일 충돌
        - phone_collision: provider 제공 휴대폰 중복

    Provider HTTP 실패는 OAuthProviderUnavailable을 재발생시킨다.
    """
    await _consume_oauth_state(state, provider_name, redis_url)

    token_body = await provider.exchange_code(code)
    access_token = token_body["access_token"]
    profile = await provider.fetch_profile(access_token)

    provider_sub = profile["provider_sub"]
    email = profile["email"]
    phone = profile["phone"]

    # 분기 1: oauth_identity 매칭 → 로그인
    oi_row = await db.execute(
        select(OAuthIdentity)
        .where(
            OAuthIdentity.provider == provider_name,
            OAuthIdentity.provider_sub == provider_sub,
        )
    )
    oi = oi_row.scalar_one_or_none()
    if oi is not None:
        u_row = await db.execute(
            select(User).where(User.id == oi.user_id, User.withdrawn_at.is_(None))
        )
        matched_user = u_row.scalar_one_or_none()
        if matched_user is not None:
            logger.info(
                "auth.oauth.login_completed",
                provider=provider_name,
                user_id=matched_user.id,
                sub_hash=_sub_hash(provider_sub),
                trace_id="",
            )
            return {"action": "login_completed", "user_id": matched_user.id}
        # 매칭된 oauth_identity가 withdrawn 유저를 가리키면 재가입 플로우 진입
        # (oauth_identity 레코드는 Story 1.7에서 삭제 처리)

    # 분기 2: 이메일 매칭 — 자체 가입자(password_hash NOT NULL + oauth 미연동)?
    email_row = await db.execute(
        select(User).where(User.email == email, User.withdrawn_at.is_(None))
    )
    email_user = email_row.scalar_one_or_none()
    if email_user is not None:
        if email_user.password_hash is not None:
            logger.info(
                "auth.oauth.email_collision",
                provider=provider_name,
                email=mask_email(email),
                sub_hash=_sub_hash(provider_sub),
                trace_id="",
            )
            return {"action": "email_collision"}
        # 소셜 전용 유저(같은 이메일, 다른 provider로 이미 가입) → oauth_identity만 추가하고 로그인
        now = datetime.now(tz=timezone.utc)
        link = OAuthIdentity(
            user_id=email_user.id,
            provider=provider_name,
            provider_sub=provider_sub,
            linked_at=now,
        )
        db.add(link)
        await db.flush()
        logger.info(
            "auth.oauth.login_completed",
            provider=provider_name,
            user_id=email_user.id,
            sub_hash=_sub_hash(provider_sub),
            trace_id="",
            linked_new_provider=True,
        )
        return {"action": "login_completed", "user_id": email_user.id}

    # 분기 3·4: 신규 + provider phone 제공
    if phone:
        # 휴대폰 중복 검사
        phone_row = await db.execute(
            select(User).where(User.phone == phone, User.withdrawn_at.is_(None))
        )
        if phone_row.scalar_one_or_none() is not None:
            logger.info(
                "auth.oauth.phone_collision",
                provider=provider_name,
                phone=f"****{phone[-4:]}",
                sub_hash=_sub_hash(provider_sub),
                trace_id="",
            )
            return {"action": "phone_collision"}

        now = datetime.now(tz=timezone.utc)
        user = User(
            email=email,
            phone=phone,
            password_hash=None,
            phone_verified=True,
            subscription_status="free",
            created_at=now,
            updated_at=now,
        )
        db.add(user)
        await db.flush()
        link = OAuthIdentity(
            user_id=user.id,
            provider=provider_name,
            provider_sub=provider_sub,
            linked_at=now,
        )
        db.add(link)
        await db.flush()
        logger.info(
            "auth.oauth.signup_completed",
            provider=provider_name,
            user_id=user.id,
            sub_hash=_sub_hash(provider_sub),
            trace_id="",
        )
        return {"action": "signup_completed_full", "user_id": user.id}

    # 분기 5: 신규 + provider 휴대폰 미제공 → pending token 발급
    pending_token = secrets.token_urlsafe(32)
    key = _SIGNUP_PENDING_KEY.format(token=pending_token)
    payload = json.dumps(
        {
            "provider": provider_name,
            "provider_sub": provider_sub,
            "email": email,
        }
    )
    async with _make_redis(redis_url) as r:
        await r.set(key, payload, ex=_SIGNUP_PENDING_TTL)

    logger.info(
        "auth.oauth.signup_pending_phone",
        provider=provider_name,
        sub_hash=_sub_hash(provider_sub),
        trace_id="",
    )
    return {
        "action": "signup_pending_phone",
        "signup_pending_token": pending_token,
        "provider": provider_name,
    }


async def oauth_complete_phone_supplement(
    signup_pending_token: str,
    phone: str,
    phone_verification_token: str,
    redis_url: str,
    db: AsyncSession,
) -> User:
    """OAuth 신규 가입 — SMS 보충 마무리.

    Raises:
        400 OAUTH_PENDING_INVALID — signup_pending_token 만료·부재
        400 SMS_TOKEN_INVALID — phone_verification_token 불일치·부재
        409 OAUTH_PHONE_COLLISION / OAUTH_EMAIL_COLLISION_WITH_EMAIL_SIGNUP
    """
    pending_key = _SIGNUP_PENDING_KEY.format(token=signup_pending_token)
    async with _make_redis(redis_url) as r:
        pending_raw = await r.get(pending_key)
        if pending_raw is None:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "OAUTH_PENDING_INVALID",
                    "message": "소셜 가입 세션이 만료되었습니다. 다시 시도해주세요.",
                },
            )

        # phone_verification_token 검증 + 소진
        token_key = _TOKEN_KEY.format(token=phone_verification_token)
        stored_phone = await r.get(token_key)
        if stored_phone is None or stored_phone != phone:
            raise HTTPException(
                status_code=400,
                detail={"code": "SMS_TOKEN_INVALID", "message": "휴대폰 인증이 필요합니다."},
            )
        # 양쪽 토큰 즉시 소진
        await r.delete(token_key)
        await r.delete(pending_key)

    try:
        pending = json.loads(pending_raw)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail={"code": "OAUTH_PENDING_INVALID", "message": "소셜 가입 세션이 만료되었습니다."},
        )

    provider_name = pending["provider"]
    provider_sub = pending["provider_sub"]
    email = pending["email"]

    # 이메일 재검사 (OAuth 콜백 이후 race)
    email_row = await db.execute(
        select(User).where(User.email == email, User.withdrawn_at.is_(None))
    )
    email_user = email_row.scalar_one_or_none()
    if email_user is not None and email_user.password_hash is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "OAUTH_EMAIL_COLLISION_WITH_EMAIL_SIGNUP",
                "message": "이 이메일은 이메일 가입으로 등록되어 있습니다. 이메일 로그인을 이용해주세요.",
            },
        )

    # 휴대폰 중복 검사
    phone_row = await db.execute(
        select(User).where(User.phone == phone, User.withdrawn_at.is_(None))
    )
    if phone_row.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "OAUTH_PHONE_COLLISION",
                "message": "이 휴대폰은 이미 가입된 계정이 있습니다. 최초 가입 방식으로 로그인해주세요.",
            },
        )

    now = datetime.now(tz=timezone.utc)

    # 이메일 매칭 소셜 유저가 있으면 oauth_identity만 추가하고 해당 유저 반환
    if email_user is not None and email_user.password_hash is None:
        link = OAuthIdentity(
            user_id=email_user.id,
            provider=provider_name,
            provider_sub=provider_sub,
            linked_at=now,
        )
        db.add(link)
        await db.flush()
        logger.info(
            "auth.oauth.signup_completed",
            provider=provider_name,
            user_id=email_user.id,
            sub_hash=_sub_hash(provider_sub),
            trace_id="",
            linked_existing_social=True,
        )
        return email_user

    user = User(
        email=email,
        phone=phone,
        password_hash=None,
        phone_verified=True,
        subscription_status="free",
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    await db.flush()
    link = OAuthIdentity(
        user_id=user.id,
        provider=provider_name,
        provider_sub=provider_sub,
        linked_at=now,
    )
    db.add(link)
    await db.flush()

    logger.info(
        "auth.oauth.signup_completed",
        provider=provider_name,
        user_id=user.id,
        sub_hash=_sub_hash(provider_sub),
        trace_id="",
    )
    return user
