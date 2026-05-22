"""세션 JWT 디코드 Depends — 일반 세션과 관리자 세션 분리.

일반 사이트:  denvia_session 쿠키 → get_current_user / get_current_user_allow_blocked / get_current_user_optional
관리자 콘솔: denvia_admin_session 쿠키 → get_current_admin / require_admin

두 쿠키는 path가 분리되어 있으며, JWT의 aud 클레임으로 토큰 자체도 구분된다.
일반 세션 쿠키로는 절대 관리자 API를 통과할 수 없다.
"""

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.base import get_session
from api.src.models.user import User
from api.src.services.user_service import get_user_by_id
from api.src.utils.jwt import (
    JWTDecodeError,
    SessionExpired,
    decode_admin_session_jwt,
    decode_session_jwt,
)


_SESSION_SUPERSEDED = HTTPException(
    status_code=401,
    detail={
        "code": "AUTH_SESSION_SUPERSEDED",
        "message": "다른 장소에서 로그인되어 로그아웃되었습니다.",
    },
)


def _decode_session_cookie(denvia_session: str | None) -> dict:
    """JWT 디코딩 공통 로직 — 401 분기. 동기 함수."""
    if not denvia_session:
        raise HTTPException(
            status_code=401,
            detail={"code": "AUTH_NOT_AUTHENTICATED", "message": "로그인이 필요합니다."},
        )
    try:
        return decode_session_jwt(denvia_session)
    except SessionExpired:
        raise HTTPException(
            status_code=401,
            detail={"code": "AUTH_SESSION_EXPIRED", "message": "세션이 만료되었습니다. 다시 로그인해주세요."},
        )
    except JWTDecodeError:
        raise HTTPException(
            status_code=401,
            detail={"code": "AUTH_INVALID_TOKEN", "message": "로그인이 필요합니다."},
        )


def _enforce_session_match(payload: dict, user: User) -> None:
    """단일 세션(later wins) 매칭. 새 로그인이 일어나 user.current_session_id 가 갱신됐는데
    쿠키 쪽 sid 가 그것과 다르면 401 AUTH_SESSION_SUPERSEDED 로 거부한다.

    user.current_session_id 가 NULL 이면(레거시·로그아웃 직후) 매칭하지 않고 통과시킨다.
    payload 에 sid 가 없는 토큰(기존 발급분)도 sid 비교를 강제하지 않는다 — 이런 토큰들은
    자연 만료 후 새 로그인부터 sid 가 박힌다.
    """
    server_sid = user.current_session_id
    if server_sid is None:
        return
    cookie_sid = payload.get("sid")
    if cookie_sid is None:
        # 서버는 sid 를 갖고 있는데 쿠키에는 없다 → 이 쿠키는 더 이상의 활성 세션을 대표하지 않는다.
        raise _SESSION_SUPERSEDED
    if cookie_sid != server_sid:
        raise _SESSION_SUPERSEDED


async def get_current_user(
    denvia_session: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_session),
) -> User:
    """denvia_session 쿠키가 없거나 무효하면 401, blocked 계정이면 403."""
    payload = _decode_session_cookie(denvia_session)
    user = await get_user_by_id(db, payload["sub"])
    if user is None or user.withdrawn_at is not None:
        raise HTTPException(
            status_code=401,
            detail={"code": "AUTH_NOT_AUTHENTICATED", "message": "로그인이 필요합니다."},
        )
    _enforce_session_match(payload, user)
    if user.subscription_status == "blocked":
        raise HTTPException(
            status_code=403,
            detail={"code": "ACCOUNT_BLOCKED", "message": "차단된 계정입니다. 관리자에게 문의하세요."},
        )
    return user


async def get_current_user_allow_blocked(
    denvia_session: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_session),
) -> User:
    """/api/v1/me 전용 — blocked 사용자도 통과시켜 프론트가 차단 상태를 감지하고 /blocked로 이동할 수 있게 한다."""
    payload = _decode_session_cookie(denvia_session)
    user = await get_user_by_id(db, payload["sub"])
    if user is None or user.withdrawn_at is not None:
        raise HTTPException(
            status_code=401,
            detail={"code": "AUTH_NOT_AUTHENTICATED", "message": "로그인이 필요합니다."},
        )
    _enforce_session_match(payload, user)
    return user


async def get_current_user_optional(
    denvia_session: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_session),
) -> User | None:
    """쿠키가 없으면 None 반환. 무효한 쿠키만 401."""
    if not denvia_session:
        return None
    return await get_current_user(denvia_session=denvia_session, db=db)


async def get_current_admin(
    denvia_admin_session: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_session),
) -> User:
    """denvia_admin_session 쿠키 검증 → role==admin인 User 반환.

    일반 세션 쿠키(denvia_session)는 여기서 무시된다 — 관리자 콘솔은 별도 출입증.
    """
    if not denvia_admin_session:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "ADMIN_AUTH_REQUIRED",
                "message": "관리자 로그인이 필요합니다.",
            },
        )
    try:
        payload = decode_admin_session_jwt(denvia_admin_session)
    except SessionExpired:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "ADMIN_SESSION_EXPIRED",
                "message": "관리자 세션이 만료되었습니다. 다시 로그인해주세요.",
            },
        )
    except JWTDecodeError:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "ADMIN_AUTH_REQUIRED",
                "message": "관리자 로그인이 필요합니다.",
            },
        )

    user = await get_user_by_id(db, payload["sub"])
    if user is None or user.withdrawn_at is not None or user.role != "admin":
        # 토큰이 가리키는 사용자가 더 이상 admin이 아니면(role 박탈/탈퇴) 즉시 거부
        raise HTTPException(
            status_code=401,
            detail={
                "code": "ADMIN_AUTH_REQUIRED",
                "message": "관리자 로그인이 필요합니다.",
            },
        )
    return user


async def require_admin(
    admin: User = Depends(get_current_admin),
) -> User:
    """관리자 라우터 진입 가드 — denvia_admin_session 쿠키 전용."""
    return admin
