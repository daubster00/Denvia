"""인증 서비스 — SMS OTP, 회원가입, 로그인 비즈니스 로직."""

import random
import secrets
import string
from datetime import datetime, timezone

import sentry_sdk
import structlog
from fastapi import HTTPException
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.integrations.messaging.port import MessagingProvider
from api.src.models.anomaly_event import AnomalyEvent
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
    # TODO Story 1.6: oauth_identity 테이블 추가 후 provider별 세분화 ("kakao"/"google"/"naver")
    signup_method = "email" if user.password_hash is not None else "social"
    return {"email_masked": email_masked, "signup_method": signup_method}
