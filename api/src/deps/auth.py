"""세션 JWT 디코드 Depends — 401 강제/허용 두 가지 모드."""

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.base import get_session
from api.src.models.user import User
from api.src.services.user_service import get_user_by_id
from api.src.utils.jwt import JWTDecodeError, SessionExpired, decode_session_jwt


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


async def require_admin(
    user: User = Depends(get_current_user),
) -> User:
    """관리자 role 검증 — 미인증은 get_current_user가 401, 일반 유저는 403."""
    if user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail={
                "code": "ADMIN_ACCESS_REQUIRED",
                "message": "관리자 권한이 필요합니다.",
            },
        )
    return user
