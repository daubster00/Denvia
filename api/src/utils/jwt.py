"""JWT 인코드/디코드 유틸리티 — denvia_session 쿠키 발급·소비용."""

from datetime import datetime, timedelta, timezone

import jwt as pyjwt

from api.src.settings import settings


_SESSION_TTL_SHORT = timedelta(hours=1)     # persist_session=False (브라우저 세션)
_SESSION_TTL_LONG = timedelta(days=1)       # persist_session=True (Story 1.4)


def encode_session_jwt(
    user_id: int,
    role: str,
    subscription_status: str,
    *,
    persist: bool = False,
) -> str:
    """denvia_session 쿠키에 삽입할 JWT를 생성한다.

    persist=True → 1일 TTL, persist=False → 1시간 TTL.
    """
    ttl = _SESSION_TTL_LONG if persist else _SESSION_TTL_SHORT
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "sub_status": subscription_status,
        "iat": now,
        "exp": now + ttl,
    }
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

    # JWT 표준: sub는 문자열. user_id 사용 시 int로 변환
    payload["sub"] = int(payload["sub"])
    return payload
