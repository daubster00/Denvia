"""JWT 인코드/디코드 유틸리티 — denvia_session / denvia_admin_session 쿠키 발급·소비용."""

from datetime import datetime, timedelta, timezone

import jwt as pyjwt

from api.src.settings import settings


SESSION_TTL_SHORT = timedelta(hours=1)      # (레거시) 과거 persist=False 세션. 신규 발급엔 미사용.
SESSION_TTL_LONG = timedelta(days=1)        # 기본 세션 TTL — 로그인 유지 하루(#143 로그인 유지 통일)
ADMIN_SESSION_TTL = timedelta(hours=1)      # 관리자 세션 1시간 (활동 시 슬라이딩 연장)

_ADMIN_AUDIENCE = "denvia-admin"


def encode_session_jwt(
    user_id: int,
    role: str,
    subscription_status: str,
    *,
    persist: bool = True,
    session_id: str | None = None,
) -> str:
    """denvia_session 쿠키에 삽입할 JWT를 생성한다.

    persist=True(기본) → 1일 TTL. #143 "로그인 유지 통일"로 일반 사용자 세션은
    이메일·소셜 구분 없이 기본 하루 유지다. persist=False는 레거시 경로 호환용으로만 남긴다.
    persist 값은 payload에도 함께 저장돼서, 슬라이딩 미들웨어가 갱신 시 동일 TTL을 재적용한다.

    session_id: users.current_session_id 와 매칭하기 위한 nonce. 동일 계정의 새 로그인이
    발생하면 DB의 nonce만 갱신되고, 이전 쿠키의 sid는 자동으로 mismatch → deps.auth 에서
    401 AUTH_SESSION_SUPERSEDED 처리한다.
    """
    ttl = SESSION_TTL_LONG if persist else SESSION_TTL_SHORT
    now = datetime.now(tz=timezone.utc)
    payload: dict = {
        "sub": str(user_id),
        "role": role,
        "sub_status": subscription_status,
        "persist": bool(persist),
        "iat": now,
        "exp": now + ttl,
    }
    if session_id:
        payload["sid"] = session_id
    return pyjwt.encode(
        payload,
        settings.denvia_jwt_secret,
        algorithm=settings.denvia_jwt_algorithm,
    )


class JWTDecodeError(Exception):
    """JWT 서명 오류 또는 포맷 이상."""


class SessionExpired(Exception):
    """JWT exp 초과."""


def decode_session_jwt(token: str) -> dict:
    """denvia_session 쿠키 JWT를 디코드한다.

    반환: {"sub": user_id, "role": ..., "sub_status": ..., "exp": ...}
    만료 시 SessionExpired, 서명·포맷 오류 시 JWTDecodeError.

    aud 클레임이 있는 토큰(=admin 세션 토큰)은 거부한다 — 관리자 토큰을 일반 세션으로 재사용하는 것을 방지.
    """
    try:
        payload = pyjwt.decode(
            token,
            settings.denvia_jwt_secret,
            algorithms=[settings.denvia_jwt_algorithm],
            options={"require": ["sub", "role", "sub_status", "exp"]},
        )
    except pyjwt.ExpiredSignatureError:
        raise SessionExpired("JWT 만료")
    except pyjwt.PyJWTError as e:
        raise JWTDecodeError(f"JWT 디코드 실패: {e}") from e

    # 관리자 토큰(aud=denvia-admin)은 일반 세션으로 사용 불가
    if payload.get("aud") == _ADMIN_AUDIENCE:
        raise JWTDecodeError("admin 토큰을 일반 세션으로 사용할 수 없습니다")

    # JWT 표준: sub는 문자열. user_id 사용 시 int로 변환
    payload["sub"] = int(payload["sub"])
    return payload


def encode_admin_session_jwt(user_id: int) -> str:
    """관리자 세션 쿠키(denvia_admin_session)용 JWT.

    일반 세션 토큰과 aud 클레임("denvia-admin")으로 구분한다.
    TTL 1시간 고정 (persist 옵션 없음).
    """
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": str(user_id),
        "aud": _ADMIN_AUDIENCE,
        "iat": now,
        "exp": now + ADMIN_SESSION_TTL,
    }
    return pyjwt.encode(
        payload,
        settings.denvia_jwt_secret,
        algorithm=settings.denvia_jwt_algorithm,
    )


def decode_admin_session_jwt(token: str) -> dict:
    """denvia_admin_session 쿠키 JWT를 디코드한다.

    반환: {"sub": user_id (int), "aud": "denvia-admin", "exp": ...}
    aud 클레임이 일치하지 않으면 JWTDecodeError.
    """
    try:
        payload = pyjwt.decode(
            token,
            settings.denvia_jwt_secret,
            algorithms=[settings.denvia_jwt_algorithm],
            audience=_ADMIN_AUDIENCE,
            options={"require": ["sub", "aud", "exp"]},
        )
    except pyjwt.ExpiredSignatureError:
        raise SessionExpired("admin JWT 만료")
    except pyjwt.PyJWTError as e:
        raise JWTDecodeError(f"admin JWT 디코드 실패: {e}") from e

    payload["sub"] = int(payload["sub"])
    return payload
