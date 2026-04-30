"""세션 JWT 디코드 Depends — 일반 세션과 관리자 세션 분리.

일반 사이트:  denvia_session 쿠키 → get_current_user / get_current_user_optional
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


async def get_current_user(
    denvia_session: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_session),
) -> User:
    """denvia_session 쿠키가 없거나 무효하면 401을 던진다."""
    if not denvia_session:
        raise HTTPException(
            status_code=401,
            detail={"code": "AUTH_NOT_AUTHENTICATED", "message": "로그인이 필요합니다."},
        )
    try:
        payload = decode_session_jwt(denvia_session)
    except SessionExpired:
        raise HTTPException(
            status_code=401,
            detail={"code": "AUTH_SESSION_EXPIRED", "message": "세션이 만료되었습니다. 다시 로그인해주세요."},
        )
    except JWTDecodeError:
        # 서명·포맷 오류는 상세 미공개 (보안)
        raise HTTPException(
            status_code=401,
            detail={"code": "AUTH_INVALID_TOKEN", "message": "로그인이 필요합니다."},
        )

    user = await get_user_by_id(db, payload["sub"])
    if user is None or user.withdrawn_at is not None:
        raise HTTPException(
            status_code=401,
            detail={"code": "AUTH_NOT_AUTHENTICATED", "message": "로그인이 필요합니다."},
        )
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
