"""인증 서비스 — SMS OTP, 회원가입, 로그인 비즈니스 로직."""

import hashlib
import json
import random
import secrets
import string
import uuid
from datetime import date, datetime, timezone
from typing import Literal, TypedDict

import sentry_sdk
import structlog
from fastapi import HTTPException
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.integrations.auth_providers.base import (
    OAuthProvider,
    OAuthProviderUnavailable,
    ProviderName,
)
from api.src.integrations.messaging.port import MessagingProvider
from api.src.middleware.audit_actions import AUDIT_USER_WITHDRAW
from api.src.models.anomaly_event import AnomalyEvent
from api.src.models.audit_log import AuditLog
from api.src.models.oauth_identity import OAuthIdentity
from api.src.models.qa_log import QALog
from api.src.models.user import User
from api.src.services import anomaly_service
from api.src.settings import REDIS_DB_OTP, REDIS_DB_RATE_LIMIT, REDIS_DB_RUNTIME_CONFIG
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

# ── SMS 이상탐지 (봇/공격 패턴) ─────────────────────────────────────────────────
# /auth/sms/send 호출이 1시간 안에 10회 이상이면 동일 번호의 send/verify 를 24시간 거절한다.
# 카운터는 purpose 무관 — 같은 번호로 purpose 만 바꿔가며 두드리는 패턴까지 잡기 위해.
# cooldown(60s)·시간당 한도(3회)에 막힌 요청도 카운트에 포함 — 거절 후에도 계속 두드리는
# 자동화된 접근을 식별하는 게 본 임계의 목적이다.
_SMS_ATTEMPT_KEY = "sms_attempt:{phone}"
_SMS_BLOCK_KEY = "sms_block:{phone}"
_SMS_ATTEMPT_WINDOW = 3600       # 1시간
_SMS_BLOCK_TTL = 86400           # 24시간
_SMS_ANOMALY_THRESHOLD = 10
_SMS_ANOMALY_MESSAGE = (
    "비정상적인 인증 시도가 감지되어 24시간 동안 휴대폰 인증이 제한됩니다. "
    "자동화된 접근으로 의심되는 경우 차단되며, 본인이 맞다면 잠시 후 다시 시도해 주세요."
)


def _mask_phone_for_anomaly(phone: str) -> str:
    """이상탐지 details 저장용 — 가운데 4자리 마스킹."""
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) < 8:
        return "***"
    return f"{digits[:3]}****{digits[-4:]}"


def _make_redis(base_url: str) -> Redis:
    return Redis.from_url(f"{base_url}/{REDIS_DB_OTP}", decode_responses=True)


def _make_redis_rl(base_url: str) -> Redis:
    """Rate Limit DB (DB 2) — 브루트포스 카운터·락아웃."""
    return Redis.from_url(f"{base_url}/{REDIS_DB_RATE_LIMIT}", decode_responses=True)


def _make_redis_runtime(base_url: str) -> Redis:
    """Runtime Config DB (DB 3) — 관리자 편집 런타임 값(로그인 실패 임계 등)."""
    return Redis.from_url(f"{base_url}/{REDIS_DB_RUNTIME_CONFIG}", decode_responses=True)


# Recovery 관련 Redis 키 (DB 2 공유)
_RECOVERY_KEY = "recovery_attempts:{phone}"
_RECOVERY_TTL = 3600
_RECOVERY_ABUSE_THRESHOLD = 4

# 타이밍 균일화용 dummy 해시 (argon2id verify 1회 소모)
_DUMMY_HASH = "$argon2id$v=19$m=65536,t=3,p=4$dummyhash0000000000000000$dummyhash0000000000000000000000000000000000"

# 브루트포스 Redis 키
_LOGIN_FAIL_KEY = "login_fail:{email}"
_LOGIN_LOCKOUT_KEY = "login_lockout:{email}"
# 1차 락아웃을 한 번이라도 거친 이메일을 표식 — 락 TTL 만료 후 단 1회의 재시도가
# 또 실패하면 stage=2 로 escalate. lockout(10m) 보다 훨씬 길게 유지해야 의미가 있음.
_LOGIN_STAGE_KEY = "login_stage:{email}"
# 2차 escalation 발생 시 세팅 — 비밀번호 찾기로 임시 비번이 발송되기 전까지 풀리지 않음.
_LOGIN_HARD_LOCK_KEY = "login_hard_lock:{email}"
_LOGIN_LOCKOUT_TTL = 600     # 10분
_LOGIN_FAIL_WINDOW = 600     # 카운터 TTL도 10분 (성공 시 초기화)
_LOGIN_STAGE_TTL = 86400     # 24h — 1차 락 이후 stage 표식 유지 기간
_LOGIN_HARD_LOCK_TTL = 2592000  # 30일 — 비번찾기 전까지 사실상 영구 (안전망)
_LOGIN_BRUTE_THRESHOLD = 3   # 기본 3회 — 관리자가 runtime:login_brute_threshold 로 1~20 사이 조정 가능
                             # (Redis 미설정·연결실패 시 fail-safe 폴백 값)


async def _resolve_login_brute_threshold(redis_url: str) -> int:
    """현재 로그인 실패 이상탐지 임계값을 Runtime Config(DB 3)에서 읽는다.

    fail-safe: Redis 가 죽었거나 값이 깨져 있으면 코드 기본값(``_LOGIN_BRUTE_THRESHOLD``)
    으로 폴백 — 인증 경로가 런타임 설정 가용성에 의존하지 않도록 한다.
    클램프 범위(1~20)는 ``runtime_config_service`` 의 정의를 단일 SSOT 로 위임.
    """
    try:
        # 지연 import — circular import 회피 (auth_service ↔ runtime_config_service 양방 참조 차단).
        from api.src.services import runtime_config_service

        async with _make_redis_runtime(redis_url) as r:
            return await runtime_config_service.get_login_brute_threshold(r)
    except Exception:
        return _LOGIN_BRUTE_THRESHOLD

# OAuth provider → 한국어 라벨 매핑 (AC-1, AC-6)
_PROVIDER_LABEL_KO: dict[str, str] = {
    "kakao": "카카오",
    "google": "구글",
    "naver": "네이버",
}


def _otp_keys(purpose: str, phone: str) -> tuple[str, str, str]:
    return (
        _OTP_KEY.format(purpose=purpose, phone=phone),
        _COOLDOWN_KEY.format(purpose=purpose, phone=phone),
        _RETRY_COUNT_KEY.format(purpose=purpose, phone=phone),
    )


async def _record_sms_abuse_anomaly(
    *,
    phone: str,
    purpose: str,
    attempt_count: int,
    db: AsyncSession | None,
    ip: str | None = None,
) -> None:
    """SMS 이상탐지 발동 시 AnomalyEvent 1건 INSERT.

    db 가 None 이면 (테스트·드물게 라우터가 세션을 전달 못한 경우) DB 기록은 skip 하고
    구조 로그만 남긴다 — 차단(24h)·거절(429)은 어떤 경우에도 적용된다.
    멱등 — Redis block_key SET 직후에만 호출되므로 24h 안에 같은 번호로 중복 INSERT 되지 않는다.
    target_user_id 는 phone 으로 활성 사용자를 조회해 채우고, 없으면 NULL (signup 단계).

    ip 는 라우터에서 추출한 클라이언트 IP. 차단 정책은 변경되지 않지만 이상탐지 리스트에서
    추적 가능하도록 기록만 한다.
    """
    masked = _mask_phone_for_anomaly(phone)
    logger.warning(
        "auth.sms_abuse.detected",
        phone_masked=masked,
        purpose=purpose,
        attempt_count=attempt_count,
    )
    if db is None:
        return

    try:
        # 지연 import — auth_service 의 모듈 상단 import 사이클 회피.
        from api.src.models.anomaly_event import AnomalyEvent as _AnomalyEvent

        existing_user_id: int | None = None
        try:
            row = (
                await db.execute(
                    select(User.id).where(User.phone == phone, User.withdrawn_at.is_(None))
                )
            ).scalar_one_or_none()
            existing_user_id = row if row is not None else None
        except Exception:
            logger.error("auth.sms_abuse.user_lookup_failed", exc_info=True)
            existing_user_id = None

        now_dt = datetime.now(tz=timezone.utc)
        event = _AnomalyEvent(
            type="sms_abuse",
            target_user_id=existing_user_id,
            ip=ip,
            ua=None,
            details={
                "phone_masked": masked,
                "purpose": purpose,
                "attempt_count": int(attempt_count),
                "window_seconds": _SMS_ATTEMPT_WINDOW,
                "block_seconds": _SMS_BLOCK_TTL,
                "auto_actioned": True,
            },
            status="actioned",
            reviewed_by_admin_id=None,
            reviewed_at=now_dt,
            created_at=now_dt,
        )
        db.add(event)
        try:
            await db.flush()
            # 이후 send_sms_otp_flow 가 HTTPException(429) 으로 빠지므로 라우터 commit 이
            # 실행되지 않는다. 이상탐지 row 가 유실되지 않도록 여기서 명시 commit.
            await db.commit()
        except Exception:
            await db.rollback()
            logger.error("auth.sms_abuse.insert_failed", exc_info=True)
    except Exception:
        logger.error("auth.sms_abuse.hook_failed", exc_info=True)


async def send_sms_otp_flow(
    phone: str,
    purpose: str,
    redis_url: str,
    messaging: MessagingProvider,
    expose_code: bool = False,
    db: AsyncSession | None = None,
    ip: str | None = None,
) -> dict:
    """SMS OTP 발송 플로우.

    Returns:
        {"sent_at": iso_str, "cooldown_seconds": 60, "max_retries": 3}

    Raises:
        HTTPException 429 SMS_ANOMALY_BLOCKED — 1시간 내 10회 이상 시도로 24시간 차단 중
        HTTPException 429 SMS_COOLDOWN_ACTIVE — 60초 쿨다운 중
        HTTPException 429 SMS_MAX_RETRIES_EXCEEDED — 시간당 4회 초과
    """
    otp_key, cooldown_key, retry_key = _otp_keys(purpose, phone)
    attempt_key = _SMS_ATTEMPT_KEY.format(phone=phone)
    block_key = _SMS_BLOCK_KEY.format(phone=phone)

    async with _make_redis(redis_url) as r:
        # 0) 24h 차단 키 우선 확인 — 어떤 카운터/쿨다운보다 먼저.
        block_ttl = await r.ttl(block_key)
        if isinstance(block_ttl, int) and block_ttl > 0:
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "SMS_ANOMALY_BLOCKED",
                    "message": _SMS_ANOMALY_MESSAGE,
                    "retry_after_seconds": block_ttl,
                },
            )

        # 1) 시도 카운터 INCR — purpose 무관·성공/실패 무관. 10회 도달 시 24h 차단으로 전이.
        attempt_count = await r.incr(attempt_key)
        if attempt_count == 1:
            await r.expire(attempt_key, _SMS_ATTEMPT_WINDOW)
        if attempt_count >= _SMS_ANOMALY_THRESHOLD:
            await r.set(block_key, "1", ex=_SMS_BLOCK_TTL)
            await _record_sms_abuse_anomaly(
                phone=phone,
                purpose=purpose,
                attempt_count=int(attempt_count),
                db=db,
                ip=ip,
            )
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "SMS_ANOMALY_BLOCKED",
                    "message": _SMS_ANOMALY_MESSAGE,
                    "retry_after_seconds": _SMS_BLOCK_TTL,
                },
            )

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

    result = {
        "sent_at": sent_at,
        "cooldown_seconds": _COOLDOWN_TTL,
        "max_retries": _MAX_RETRIES,
    }
    if expose_code:
        result["debug_code"] = otp
    return result


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
        HTTPException 429 SMS_ANOMALY_BLOCKED — 1시간 내 10회 이상 시도로 24시간 차단 중
        HTTPException 400 SMS_CODE_INVALID — OTP 불일치
        HTTPException 400 SMS_SESSION_EXPIRED — OTP 없음/만료
        HTTPException 400 SMS_MAX_WRONG_ATTEMPTS — 3회 오류 후 무효화
    """
    otp_key, _, _ = _otp_keys(purpose, phone)
    wrong_key = f"otp_wrong:{purpose}:{phone}"
    block_key = _SMS_BLOCK_KEY.format(phone=phone)

    async with _make_redis(redis_url) as r:
        # 24h 차단 키 우선 확인 — send 단계에서 이미 OTP 가 발급됐어도 검증 단계에서 거절.
        block_ttl = await r.ttl(block_key)
        if isinstance(block_ttl, int) and block_ttl > 0:
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "SMS_ANOMALY_BLOCKED",
                    "message": _SMS_ANOMALY_MESSAGE,
                    "retry_after_seconds": block_ttl,
                },
            )

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
    *,
    name: str | None = None,
    birthdate: date | None = None,
    gender: Literal["male", "female"] | None = None,
    postcode: str | None = None,
    address_road: str | None = None,
    address_detail: str | None = None,
) -> User:
    """회원가입 처리.

    선택 입력(name/birthdate/gender/postcode/address_road/address_detail)은 None이면
    저장하지 않는다. 검증·정규화는 호출 측 Pydantic 스키마에서 수행.

    Returns:
        생성된 User 객체

    Raises:
        HTTPException 400 SMS_TOKEN_INVALID — phone_verification_token 검증 실패
        HTTPException 409 ACCOUNT_EMAIL_DUPLICATE / ACCOUNT_PHONE_DUPLICATE
    """
    # 이메일 정규화 — OAuth provider의 `.lower().strip()` 정규화와 일관성 유지
    # (대소문자 섞인 가입 이메일과 소문자로 정규화된 provider 이메일이 AC-6 충돌 검사에서 불일치하는 버그 방지)
    email = email.lower().strip()

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
        # 가입 직후 자동 로그인 — 단일 세션 nonce 박제(라우터의 JWT 발급도 동일 값 사용).
        current_session_id=secrets.token_urlsafe(24),
        # 선택 입력 — None이면 컬럼은 NULL로 남는다.
        name=name,
        birthdate=birthdate,
        gender=gender,
        postcode=postcode,
        address_road=address_road,
        address_detail=address_detail,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    await db.flush()  # id 획득

    sentry_sdk.add_breadcrumb(
        message="auth.signup.completed",
        data={"user_id": user.id},
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
    *,
    rotate_session: bool = True,
) -> User:
    """이메일 로그인 처리.

    Args:
        rotate_session: True면 users.current_session_id 를 새 nonce 로 회전(=일반 사이트 로그인의
            "later wins" 단일 세션 정책 적용). False면 회전하지 않는다 — 관리자 콘솔 로그인처럼
            별도 쿠키(denvia_admin_session)로 진입하는 케이스가 이 옵션을 쓴다. 동일 계정으로
            같은 브라우저에 일반 사이트 로그인 쿠키(denvia_session)가 남아 있는 상태에서
            관리자 로그인이 user nonce 를 갈아엎으면 사용자의 일반 쿠키가 즉시 SUPERSEDED 되어
            루트 SessionBootstrap 의 /api/v1/me 호출이 401 로 튕기는 회귀가 발생한다.

    Returns:
        인증된 User 객체

    Raises:
        HTTPException 429 AUTH_TEMPORARILY_LOCKED — 1차 10분 락아웃 중
        HTTPException 423 AUTH_MUST_RESET_PASSWORD — 2차 escalation(락 해제 후 재시도도 실패) — 비번찾기로만 해제
        HTTPException 401 AUTH_INVALID_CREDENTIALS — 인증 실패 (이메일 존재 여부 비노출)
        HTTPException 403 ACCOUNT_BLOCKED — 관리자에 의해 차단된 계정 (admin role 제외)
    """
    fail_key = _LOGIN_FAIL_KEY.format(email=email)
    lockout_key = _LOGIN_LOCKOUT_KEY.format(email=email)
    stage_key = _LOGIN_STAGE_KEY.format(email=email)
    hard_lock_key = _LOGIN_HARD_LOCK_KEY.format(email=email)
    # 관리자가 편집한 임계값(기본 3회). Runtime DB 장애 시 코드 기본값으로 폴백.
    brute_threshold = await _resolve_login_brute_threshold(redis_url)

    # 락아웃 체크 — hard_lock(2차) 이 lockout(1차)보다 강함이므로 먼저 확인.
    async with _make_redis_rl(redis_url) as r:
        if await r.exists(hard_lock_key):
            raise HTTPException(
                status_code=423,
                detail={
                    "code": "AUTH_MUST_RESET_PASSWORD",
                    "message": "비밀번호 오류가 반복되어 더 이상 로그인할 수 없습니다. 비밀번호 찾기로 재설정해 주세요.",
                },
            )
        if await r.exists(lockout_key):
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "AUTH_TEMPORARILY_LOCKED",
                    "message": "비밀번호 오류가 반복되어 10분간 로그인이 잠겼습니다. 잠시 후 다시 시도하거나 비밀번호 찾기를 이용하세요.",
                },
            )

    # 사용자 조회 (이메일 미존재 시에도 동일 에러 반환 — timing-safe)
    result = await db.execute(
        select(User).where(User.email == email, User.withdrawn_at.is_(None))
    )
    user = result.scalar_one_or_none()

    # AC-1: OAuth-only 사용자 분기
    # AC-2 락아웃 우선은 위 락아웃 체크에서 이미 처리됨.
    # AC-5 탈퇴 사용자는 위 withdrawn_at.is_(None) 필터로 자동 제외.
    if user is not None and user.password_hash is None:
        oi_rows = await db.execute(
            select(OAuthIdentity.provider)
            .where(OAuthIdentity.user_id == user.id)
            .order_by(OAuthIdentity.linked_at.asc())
        )
        providers_raw = oi_rows.scalars().all()
        seen: set[str] = set()
        linked_providers: list[str] = []
        for p in providers_raw:
            if p in _PROVIDER_LABEL_KO and p not in seen:
                linked_providers.append(p)
                seen.add(p)

        if linked_providers:
            label_text = ", ".join(_PROVIDER_LABEL_KO[p] for p in linked_providers)
            if len(linked_providers) == 1:
                msg = f"이 계정은 {label_text}로 가입되어 있습니다. {label_text}로 로그인해 주세요."
            else:
                msg = f"이 계정은 {label_text}로 가입되어 있습니다. 가입한 채널로 로그인해 주세요."

            # AC-7: 운영 관측 이벤트 (audit_logs INSERT 아님)
            logger.info(
                "auth.login.oauth_only_hint",
                user_id=user.id,
                email=mask_email(user.email),
                providers=linked_providers,
                ip=ip,
            )

            # AC-12: enumeration throttle — 기존 로그인 실패 카운터 재사용
            async with _make_redis_rl(redis_url) as r:
                count_raw = await r.get(fail_key)
                count = int(count_raw) + 1 if count_raw else 1
                await r.set(fail_key, str(count), ex=_LOGIN_FAIL_WINDOW)

                if count >= brute_threshold:
                    now = datetime.now(tz=timezone.utc)
                    event = AnomalyEvent(
                        type="login_brute_force",
                        target_user_id=user.id,
                        ip=ip,
                        ua=ua,
                        details={
                            "stage": 1,
                            "severity": "medium",
                            "attempt_count": count,
                            "reason": "oauth_only_hint",
                        },
                        status="new",
                        created_at=now,
                    )
                    db.add(event)
                    try:
                        await db.commit()
                    except Exception:
                        await db.rollback()

                    # OAuth-only enumeration 은 stage_key 를 세팅하지 않는다 —
                    # password verify 경로가 없으므로 stage-2 escalation 이 발생할 수 없음.
                    await r.set(lockout_key, "1", ex=_LOGIN_LOCKOUT_TTL)

            raise HTTPException(
                status_code=409,
                detail={
                    "code": "AUTH_ACCOUNT_OAUTH_ONLY",
                    "message": msg,
                    "linked_providers": linked_providers,
                },
            )
        # password_hash IS NULL + oauth 0개 비정상 상태 → 기존 401 경로 fall-through

    # 비밀번호 검증 (미존재 시 dummy 검증으로 timing 균일화)
    password_correct = False
    if user is not None and user.password_hash is not None:
        password_correct = verify_password(password, user.password_hash)
    else:
        # dummy 검증 — timing attack 방지
        verify_password(password, "$argon2id$v=19$m=65536,t=3,p=4$dummyhash0000000000000000$dummyhash0000000000000000000000000000000000")

    if not password_correct:
        async with _make_redis_rl(redis_url) as r:
            # 이전에 이미 1차 락(10분)을 한 번 거친 이메일인지 확인.
            # 거쳤다면 — 락 해제 후의 단 1회 재시도가 또 실패한 것이므로 2차 escalation.
            stage_raw = await r.get(stage_key)
            if stage_raw == "1":
                now = datetime.now(tz=timezone.utc)
                event = AnomalyEvent(
                    type="login_brute_force",
                    target_user_id=user.id if user else None,
                    ip=ip,
                    ua=ua,
                    details={
                        "stage": 2,
                        "severity": "high",
                        "reason": "retry_after_lockout_failed",
                    },
                    status="new",
                    created_at=now,
                )
                db.add(event)
                try:
                    await db.commit()
                except Exception:
                    await db.rollback()

                # hard_lock — 비번찾기로 임시 비번이 발송될 때까지 풀리지 않음.
                await r.set(hard_lock_key, "1", ex=_LOGIN_HARD_LOCK_TTL)
                # fail counter / stage / 임시 lockout 정리 (의미 상실)
                await r.delete(fail_key)
                await r.delete(stage_key)
                await r.delete(lockout_key)

                logger.warning(
                    "auth.login.brute_force.stage2",
                    email=f"****{email[-4:]}",
                    ip=ip,
                )

                raise HTTPException(
                    status_code=423,
                    detail={
                        "code": "AUTH_MUST_RESET_PASSWORD",
                        "message": "비밀번호 오류가 반복되어 더 이상 로그인할 수 없습니다. 비밀번호 찾기로 재설정해 주세요.",
                    },
                )

            # 1차 단계 — 실패 카운터 증가
            count_raw = await r.get(fail_key)
            count = int(count_raw) + 1 if count_raw else 1
            await r.set(fail_key, str(count), ex=_LOGIN_FAIL_WINDOW)

            if count >= brute_threshold:
                # 1차 anomaly INSERT
                now = datetime.now(tz=timezone.utc)
                event = AnomalyEvent(
                    type="login_brute_force",
                    target_user_id=user.id if user else None,
                    ip=ip,
                    ua=ua,
                    details={
                        "stage": 1,
                        "severity": "medium",
                        "attempt_count": count,
                    },
                    status="new",
                    created_at=now,
                )
                db.add(event)
                try:
                    await db.commit()
                except Exception:
                    await db.rollback()

                # 10분 lockout + 24h stage 표식
                await r.set(lockout_key, "1", ex=_LOGIN_LOCKOUT_TTL)
                await r.set(stage_key, "1", ex=_LOGIN_STAGE_TTL)
                await r.delete(fail_key)

                logger.warning(
                    "auth.login.brute_force.stage1",
                    email=f"****{email[-4:]}",
                    attempt_count=count,
                    ip=ip,
                )

                # 임계 도달 즉시 락 안내 (4번째 요청을 기다리지 않고).
                raise HTTPException(
                    status_code=429,
                    detail={
                        "code": "AUTH_TEMPORARILY_LOCKED",
                        "message": "비밀번호 오류가 반복되어 10분간 로그인이 잠겼습니다. 잠시 후 다시 시도하거나 비밀번호 찾기를 이용하세요.",
                    },
                )

        raise HTTPException(
            status_code=401,
            detail={
                "code": "AUTH_INVALID_CREDENTIALS",
                "message": "이메일 또는 비밀번호가 일치하지 않습니다.",
            },
        )

    # 비밀번호는 맞았지만 관리자에 의해 차단된 계정이면 세션을 발급하지 않는다.
    # role=='admin' 은 차단 대상이 아니다 — 관리자 콘솔 진입을 막지 않도록 분기.
    # (admin 라우터는 별도 쿠키이지만, login_user 자체는 일반/관리자 공용이라 여기서 안전망.)
    if user.role != "admin" and user.subscription_status == "blocked":
        # 실패 카운터/락 키는 정리한다 — 비밀번호 자체는 맞았으므로 브루트포스 누적 의미 없음.
        async with _make_redis_rl(redis_url) as r:
            await r.delete(fail_key)
            await r.delete(stage_key)
            await r.delete(lockout_key)
            await r.delete(hard_lock_key)
        logger.info(
            "auth.login.blocked_account",
            user_id=user.id,
            ip=ip,
        )
        raise HTTPException(
            status_code=403,
            detail={
                "code": "ACCOUNT_BLOCKED",
                "message": "차단된 계정입니다. 관리자에게 문의하세요.",
            },
        )

    # 로그인 성공 — 실패 카운터/락 키 일괄 초기화
    async with _make_redis_rl(redis_url) as r:
        await r.delete(fail_key)
        await r.delete(stage_key)
        await r.delete(lockout_key)
        await r.delete(hard_lock_key)

    # Story 6.2: 로그인 성공 시 last_login_at 업데이트 (편차 2)
    user.last_login_at = datetime.now(tz=timezone.utc)
    # 단일 세션(later wins) — 새 nonce 발급. 이전 쿠키는 sid mismatch 로 자동 무효화된다.
    # rotate_session=False 면 회전을 건너뛴다(관리자 콘솔 로그인은 별도 쿠키 사용 — 일반 쿠키 무효화 방지).
    if rotate_session:
        user.current_session_id = secrets.token_urlsafe(24)
    # 접속 통계용 login_events 적재 (관리자 콘솔 로그인은 제외 — 일반 회원 접속 지표).
    if user.role != "admin":
        from api.src.models.login_event import LoginEvent
        db.add(
            LoginEvent(
                user_id=user.id,
                ip=ip,
                ua=ua,
                method="password",
                created_at=datetime.now(tz=timezone.utc),
            )
        )
    try:
        await db.commit()
    except Exception:
        await db.rollback()

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

        # 브루트포스 락 키 일괄 정리 — 임시 비번이 발송된 시점부터 사용자가
        # 그 비번으로 즉시 로그인할 수 있어야 한다(hard_lock 이 걸려 있으면 무한 루프).
        try:
            async with _make_redis_rl(redis_url) as r:
                matched_email = user.email
                await r.delete(_LOGIN_FAIL_KEY.format(email=matched_email))
                await r.delete(_LOGIN_LOCKOUT_KEY.format(email=matched_email))
                await r.delete(_LOGIN_STAGE_KEY.format(email=matched_email))
                await r.delete(_LOGIN_HARD_LOCK_KEY.format(email=matched_email))
        except RedisError:
            # 락 키 정리 실패는 silent — 다음 임시 비번 발송이나 30일 TTL 만료로 자연 해제.
            logger.exception("auth.password_reset.lock_cleanup_failed")

        logger.info(
            "auth.password_reset.requested",
            phone=f"****{phone[-4:]}",
            matched=True,
        )
    elif matched and user.password_hash is None:
        # 소셜 전용 계정 — dummy argon2 타이밍 균일화
        verify_password("dummy", _DUMMY_HASH)
        logger.info(
            "auth.password_reset.skipped_social",
            phone=f"****{phone[-4:]}",
        )
        logger.info(
            "auth.password_reset.requested",
            phone=f"****{phone[-4:]}",
            matched=False,
        )
    else:
        # 불일치 — dummy argon2 타이밍 균일화
        verify_password("dummy", _DUMMY_HASH)
        logger.info(
            "auth.password_reset.requested",
            phone=f"****{phone[-4:]}",
            matched=False,
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
    next_path: str  # AC-3: login_completed 성공 시 라우터에서 사용할 리다이렉트 경로 (없으면 "")


def _sub_hash(sub: str) -> str:
    return hashlib.sha256(sub.encode("utf-8")).hexdigest()[:16]


async def oauth_start(
    provider_name: ProviderName,
    mode: Literal["login", "signup"],
    provider: OAuthProvider,
    redis_url: str,
    next_path: str = "",
) -> str:
    """OAuth authorize URL 생성 — state 32B nonce를 Redis DB 2에 기록.

    next_path: 콜백 후 프론트 리다이렉트 경로(allowlist에 통과된 값만 전달됨).
    """
    state = secrets.token_urlsafe(32)
    key = _OAUTH_STATE_KEY.format(state=state)
    payload = json.dumps(
        {"provider": provider_name, "mode": mode, "next": next_path or ""}
    )
    try:
        async with _make_redis_rl(redis_url) as r:
            await r.set(key, payload, ex=_OAUTH_STATE_TTL)
    except RedisError:
        logger.exception("auth.oauth.redis_error", phase="start")
        raise HTTPException(
            status_code=503,
            detail={"code": "OAUTH_PROVIDER_UNAVAILABLE", "message": "소셜 로그인이 일시 지연됩니다."},
        )
    return provider.get_authorization_url(state=state)


def _state_invalid_error() -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={"code": "OAUTH_STATE_INVALID", "message": "소셜 로그인 세션이 만료되었습니다."},
    )


async def _consume_oauth_state(state: str, provider_name: str, redis_url: str) -> dict:
    """state 검증 + 즉시 삭제(원자). 실패 시 `auth.oauth.state_invalid` 이벤트 로깅 후 HTTPException.

    원자성: Redis 6.2+ `GETDEL`로 GET+DEL을 단일 명령으로 처리하여 동시 콜백에서의 state 재사용을 방지.
    """
    key = _OAUTH_STATE_KEY.format(state=state)
    try:
        async with _make_redis_rl(redis_url) as r:
            raw = await r.getdel(key)
    except RedisError:
        logger.exception("auth.oauth.redis_error", phase="state_consume", provider=provider_name)
        raise HTTPException(
            status_code=503,
            detail={"code": "OAUTH_PROVIDER_UNAVAILABLE", "message": "소셜 로그인이 일시 지연됩니다."},
        )

    if raw is None:
        logger.warning("auth.oauth.state_invalid", provider=provider_name, reason="not_found")
        raise _state_invalid_error()

    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("auth.oauth.state_parse_error", provider=provider_name)
        raise _state_invalid_error()

    if payload.get("provider") != provider_name:
        logger.warning("auth.oauth.state_invalid", provider=provider_name, reason="provider_mismatch")
        raise _state_invalid_error()
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
    state_payload = await _consume_oauth_state(state, provider_name, redis_url)
    mode: str = state_payload.get("mode", "login")
    next_path: str = state_payload.get("next", "") or ""

    # Naver는 token endpoint에서도 state를 요구하므로 반드시 전달.
    token_body = await provider.exchange_code(code, state)
    access_token = token_body["access_token"]
    profile = await provider.fetch_profile(access_token)

    provider_sub = profile["provider_sub"]
    email = profile["email"]
    phone = profile["phone"]

    # 분기 1: oauth_identity JOIN users with withdrawn_at IS NULL — AC-13 정합
    # (withdrawn user의 stale oauth_identity 레코드가 있어도 여기서 fall-through 되어
    #  아래 INSERT 시 UNIQUE(provider, provider_sub) 충돌을 일으키는 버그 방어)
    oi_row = await db.execute(
        select(OAuthIdentity, User)
        .join(User, User.id == OAuthIdentity.user_id)
        .where(
            OAuthIdentity.provider == provider_name,
            OAuthIdentity.provider_sub == provider_sub,
            User.withdrawn_at.is_(None),
        )
    )
    oi_row_result = oi_row.first()
    if oi_row_result is not None:
        _, matched_user = oi_row_result
        logger.info(
            "auth.oauth.login_completed",
            provider=provider_name,
            user_id=matched_user.id,
            sub_hash=_sub_hash(provider_sub),
        )
        return {"action": "login_completed", "user_id": matched_user.id, "next_path": next_path}

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
        try:
            await db.flush()
        except IntegrityError:
            # 동시 콜백으로 UNIQUE(provider, provider_sub) 또는 user_id 조합 충돌 — 재조회 후 로그인 처리
            await db.rollback()
            oi_row_r = await db.execute(
                select(OAuthIdentity).where(
                    OAuthIdentity.provider == provider_name,
                    OAuthIdentity.provider_sub == provider_sub,
                )
            )
            oi_r = oi_row_r.scalar_one_or_none()
            if oi_r is not None:
                logger.info(
                    "auth.oauth.login_completed",
                    provider=provider_name,
                    user_id=oi_r.user_id,
                    sub_hash=_sub_hash(provider_sub),
                    race_recovered=True,
                )
                return {"action": "login_completed", "user_id": oi_r.user_id, "next_path": next_path}
            raise  # 예상치 못한 무결성 위반 — 상위 핸들러로 전파
        logger.info(
            "auth.oauth.login_completed",
            provider=provider_name,
            user_id=email_user.id,
            sub_hash=_sub_hash(provider_sub),
            linked_new_provider=True,
        )
        return {"action": "login_completed", "user_id": email_user.id, "next_path": next_path}

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
        try:
            await db.flush()
            link = OAuthIdentity(
                user_id=user.id,
                provider=provider_name,
                provider_sub=provider_sub,
                linked_at=now,
            )
            db.add(link)
            await db.flush()
        except IntegrityError:
            # 동시 콜백·가입으로 UNIQUE(email/phone/provider_sub) 충돌 — phone_collision으로 안전하게 응답
            await db.rollback()
            logger.warning(
                "auth.oauth.phone_collision",
                provider=provider_name,
                phone=f"****{phone[-4:]}",
                sub_hash=_sub_hash(provider_sub),
                race_recovered=True,
            )
            return {"action": "phone_collision"}
        logger.info(
            "auth.oauth.signup_completed",
            provider=provider_name,
            user_id=user.id,
            sub_hash=_sub_hash(provider_sub),
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
            "mode": mode,
        }
    )
    try:
        async with _make_redis(redis_url) as r:
            await r.set(key, payload, ex=_SIGNUP_PENDING_TTL)
    except RedisError:
        logger.exception("auth.oauth.redis_error", phase="pending_set", provider=provider_name)
        raise HTTPException(
            status_code=503,
            detail={"code": "OAUTH_PROVIDER_UNAVAILABLE", "message": "소셜 로그인이 일시 지연됩니다."},
        )

    logger.info(
        "auth.oauth.signup_pending_phone",
        provider=provider_name,
        sub_hash=_sub_hash(provider_sub),
    )
    return {
        "action": "signup_pending_phone",
        "signup_pending_token": pending_token,
        "provider": provider_name,
    }


# ── Story 1.7: 회원 탈퇴 ─────────────────────────────────────────────────────


async def verify_withdraw_token(
    phone_verification_token: str,
    expected_phone: str,
    redis_url: str,
) -> None:
    """소셜 가입자 탈퇴용 phone_verification_token 검증 + 1회용 소진.

    `signup_user`/`oauth_complete_phone_supplement`와 동일한 phone_token 키 패턴을 재사용.

    Raises:
        400 SMS_TOKEN_INVALID — 토큰이 없거나 휴대폰이 일치하지 않음
    """
    token_key = _TOKEN_KEY.format(token=phone_verification_token)
    async with _make_redis(redis_url) as r:
        stored_phone = await r.get(token_key)
        if stored_phone is None or stored_phone != expected_phone:
            raise HTTPException(
                status_code=400,
                detail={"code": "SMS_TOKEN_INVALID", "message": "휴대폰 인증이 필요합니다."},
            )
        await r.delete(token_key)


async def verify_phone_change_token(
    phone_verification_token: str,
    expected_phone: str,
    redis_url: str,
) -> None:
    """마이페이지 휴대폰 변경용 phone_verification_token 검증 + 1회용 소진.

    `verify_withdraw_token`과 동일한 `phone_token:{token}` Redis 키 패턴을 공유한다
    (purpose는 OTP 발송/검증 단계에서만 분리되며, 발급된 token은 purpose-agnostic).

    Raises:
        400 SMS_TOKEN_INVALID — 토큰이 없거나 새 휴대폰 번호가 일치하지 않음
    """
    token_key = _TOKEN_KEY.format(token=phone_verification_token)
    async with _make_redis(redis_url) as r:
        stored_phone = await r.get(token_key)
        if stored_phone is None or stored_phone != expected_phone:
            raise HTTPException(
                status_code=400,
                detail={"code": "SMS_TOKEN_INVALID", "message": "휴대폰 인증이 필요합니다."},
            )
        await r.delete(token_key)


async def withdraw(
    user: User,
    ip: str | None,
    ua: str | None,
    db: AsyncSession,
    trace_id: str | uuid.UUID | None = None,
) -> None:
    """본인 계정 탈퇴 — PII 즉시 파기 + oauth_identity 삭제 + qa_logs 익명화 + audit log INSERT.

    단일 트랜잭션 내에서 처리한다. `subscription_status == "pro"`이면 409로 차단한다.

    AuditMiddleware는 `/api/v1/admin/*` 경로만 감사하므로 여기서 inline INSERT한다.
    `audit_logs.actor_user_id`는 ON DELETE RESTRICT지만 본 스토리는 소프트 삭제이므로
    `user.id`를 그대로 보존해도 FK 제약을 위반하지 않는다.

    Raises:
        409 SUBSCRIPTION_ACTIVE_MUST_CANCEL_FIRST — 활성 Pro 구독자
    """
    if user.subscription_status == "pro":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "SUBSCRIPTION_ACTIVE_MUST_CANCEL_FIRST",
                "message": "구독을 먼저 해지해주세요. 다음 결제일 이후 탈퇴가 가능합니다",
            },
        )

    # TraceMiddleware는 X-Trace-Id 헤더 값을 그대로 str로 보존하므로 비-UUID 입력이
    # audit_logs.trace_id(UUID 컬럼) INSERT 시 DataError를 일으켜 탈퇴 트랜잭션 전체를
    # 롤백시킬 수 있다. 안전 파싱 후 실패 시 None 처리.
    if isinstance(trace_id, uuid.UUID):
        trace_uuid: uuid.UUID | None = trace_id
    elif isinstance(trace_id, str):
        try:
            trace_uuid = uuid.UUID(trace_id)
        except ValueError:
            trace_uuid = None
    else:
        trace_uuid = None

    now = datetime.now(tz=timezone.utc)
    sub_before = user.subscription_status
    user_id = user.id

    # 1) PII 필드 덮어쓰기 — partial UNIQUE index(WHERE withdrawn_at IS NULL)에서 자동 해제됨
    user.email = f"withdrawn_{user_id}_{secrets.token_hex(8)}"
    user.phone = None
    user.phone_verified = False
    user.password_hash = None
    user.withdrawn_at = now
    user.updated_at = now

    # 2) oauth_identity 명시적 삭제 — 소프트 삭제이므로 FK CASCADE는 자동 트리거되지 않음
    await db.execute(delete(OAuthIdentity).where(OAuthIdentity.user_id == user_id))

    # 3) qa_logs 명시적 익명화 — 동일 사유로 FK SET NULL도 수동 처리 필요
    await db.execute(
        update(QALog).where(QALog.user_id == user_id).values(user_id=None)
    )

    # 4) audit_logs INSERT (NFR-S7) — payments 테이블은 변경하지 않음(NFR-C3, 5년 보관)
    db.add(
        AuditLog(
            actor_user_id=user_id,
            action=AUDIT_USER_WITHDRAW,
            target_type="user",
            target_id=user_id,
            diff_json={
                "subscription_status_before": sub_before,
                "withdrawn_at": now.isoformat(),
            },
            ip=ip,
            ua=ua,
            trace_id=trace_uuid,
        )
    )

    await db.commit()

    logger.info(
        "user.withdraw.completed",
        user_id=user_id,
        subscription_status_before=sub_before,
        trace_id=str(trace_uuid) if trace_uuid else None,
    )


async def oauth_complete_phone_supplement(
    signup_pending_token: str,
    phone: str,
    phone_verification_token: str,
    redis_url: str,
    db: AsyncSession,
) -> User:
    """OAuth 신규 가입 — SMS 보충 마무리.

    Raises:
        400 OAUTH_PENDING_INVALID — signup_pending_token 만료·부재·스키마 오류
        400 SMS_TOKEN_INVALID — phone_verification_token 불일치·부재
        409 OAUTH_PHONE_COLLISION / OAUTH_EMAIL_COLLISION_WITH_EMAIL_SIGNUP
    """
    pending_key = _SIGNUP_PENDING_KEY.format(token=signup_pending_token)
    token_key = _TOKEN_KEY.format(token=phone_verification_token)

    # 1) pending을 먼저 조회·검증·파싱 — 파싱 실패 시 phone 토큰은 아직 건드리지 않음 (UX: SMS 재사용 가능)
    try:
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

            # pending JSON 파싱·필수 키·provider 값 검증(삭제 전)
            try:
                pending = json.loads(pending_raw)
            except (TypeError, ValueError):
                # 잘못된 pending 데이터는 소진 후 거부 (재시도 방어)
                await r.delete(pending_key)
                raise HTTPException(
                    status_code=400,
                    detail={"code": "OAUTH_PENDING_INVALID", "message": "소셜 가입 세션이 만료되었습니다."},
                )

            provider_name = pending.get("provider")
            provider_sub = pending.get("provider_sub")
            email = pending.get("email")
            if not provider_name or not provider_sub or not email:
                await r.delete(pending_key)
                raise HTTPException(
                    status_code=400,
                    detail={"code": "OAUTH_PENDING_INVALID", "message": "소셜 가입 세션이 만료되었습니다."},
                )
            if provider_name not in {"kakao", "google", "naver"}:
                await r.delete(pending_key)
                raise HTTPException(
                    status_code=400,
                    detail={"code": "OAUTH_PENDING_INVALID", "message": "소셜 가입 세션이 만료되었습니다."},
                )

            # 2) phone 검증 토큰 확인 — 불일치면 토큰을 소진하지 않아 사용자가 재시도 가능
            stored_phone = await r.get(token_key)
            if stored_phone is None or stored_phone != phone:
                raise HTTPException(
                    status_code=400,
                    detail={"code": "SMS_TOKEN_INVALID", "message": "휴대폰 인증이 필요합니다."},
                )

            # 3) 성공 경로 — 양쪽 토큰 원자적 소진
            await r.delete(token_key)
            await r.delete(pending_key)
    except RedisError:
        logger.exception("auth.oauth.redis_error", phase="oauth_complete")
        raise HTTPException(
            status_code=503,
            detail={"code": "OAUTH_PROVIDER_UNAVAILABLE", "message": "소셜 로그인이 일시 지연됩니다."},
        )

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

    # 이메일 매칭 소셜 유저가 있으면 oauth_identity 추가 + phone 보충 데이터 반영
    if email_user is not None and email_user.password_hash is None:
        # SMS 인증으로 확정한 phone/phone_verified를 기존 유저 레코드에도 반영 (보충 데이터 폐기 방지)
        if not email_user.phone:
            email_user.phone = phone
        if not email_user.phone_verified:
            email_user.phone_verified = True
        email_user.updated_at = now

        link = OAuthIdentity(
            user_id=email_user.id,
            provider=provider_name,
            provider_sub=provider_sub,
            linked_at=now,
        )
        db.add(link)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            # 동일 (provider, provider_sub)가 이미 다른 user와 연결된 극단 케이스 — phone_collision으로 응답
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "OAUTH_PHONE_COLLISION",
                    "message": "이 휴대폰은 이미 가입된 계정이 있습니다. 최초 가입 방식으로 로그인해주세요.",
                },
            )
        logger.info(
            "auth.oauth.signup_completed",
            provider=provider_name,
            user_id=email_user.id,
            sub_hash=_sub_hash(provider_sub),
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
    try:
        await db.flush()
        link = OAuthIdentity(
            user_id=user.id,
            provider=provider_name,
            provider_sub=provider_sub,
            linked_at=now,
        )
        db.add(link)
        await db.flush()
    except IntegrityError:
        await db.rollback()
        # 동시 가입 race — 휴대폰/이메일/provider_sub 중 하나가 이미 사용됨
        raise HTTPException(
            status_code=409,
            detail={
                "code": "OAUTH_PHONE_COLLISION",
                "message": "이 휴대폰은 이미 가입된 계정이 있습니다. 최초 가입 방식으로 로그인해주세요.",
            },
        )

    logger.info(
        "auth.oauth.signup_completed",
        provider=provider_name,
        user_id=user.id,
        sub_hash=_sub_hash(provider_sub),
    )
    return user
