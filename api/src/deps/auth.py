"""세션 JWT 디코드 Depends — 일반 세션과 관리자 세션 분리.

일반 사이트:  denvia_session 쿠키 → get_current_user / get_current_user_allow_blocked / get_current_user_optional
관리자 콘솔: denvia_admin_session 쿠키 → get_current_admin / require_admin
RBAC (Story 10.1) : require_admin_grade(*allowed_grades) / require_admin_page(page_route)

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


# 이 예외의 detail.code == "AUTH_SESSION_SUPERSEDED" 면 main.py 의 HTTPException 핸들러가
# 응답에 죽은 쿠키 만료 Set-Cookie 헤더를 자동으로 동봉한다(무한 루프 차단).
# FastAPI 의존성에서 Response.set_cookie 후 raise 하면 헤더가 응답에 반영되지 않는 한계 때문에
# 만료 처리는 의존성 안이 아니라 exception handler 단에서 일괄 수행한다.
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
    # Story 10.1 — pending 등급은 가입 신청 완료 상태일 뿐 활성 관리자가 아니므로 즉시 차단.
    # admin_grade 가 NULL 인 경우(마이그레이션 0054 백필 누락·신규 admin 시드 미적용) 통과시킨다 —
    # 본 컬럼은 role=='admin' 인 행에만 의미가 있으나, 운영 안전을 위해 NULL 은 정상 admin 으로 간주.
    if getattr(user, "admin_grade", None) == "pending":
        raise HTTPException(
            status_code=401,
            detail={
                "code": "ADMIN_PENDING_APPROVAL",
                "message": "관리자 승인 대기 중입니다.",
            },
        )
    return user


async def require_admin(
    admin: User = Depends(get_current_admin),
) -> User:
    """관리자 라우터 진입 가드 — denvia_admin_session 쿠키 전용."""
    return admin


def require_admin_grade(*allowed_grades: str):
    """Story 10.1 — 특정 등급(들)만 통과시키는 의존성 팩토리.

    사용 예:
        @router.post("/admin/admins/{id}/approve",
                     dependencies=[Depends(require_admin_grade("master", "operator"))])

    admin_grade 가 NULL 인 경우는 백필 누락된 레거시 admin 으로 간주하여 일단 허용한다.
    (NULL → 백필 누락은 Story 10.3 일괄 교체 시점에 정리됨)
    """

    async def _checker(admin: User = Depends(get_current_admin)) -> User:
        grade = getattr(admin, "admin_grade", None)
        if grade is None:
            # 백필 누락 admin — 일단 통과 (Story 10.3에서 정리)
            return admin
        if grade not in allowed_grades:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "ADMIN_FORBIDDEN_GRADE",
                    "message": "권한이 부족합니다.",
                },
            )
        return admin

    return _checker


def require_admin_page(page_route: str):
    """Story 10.5 — 등급 × 페이지 매트릭스 기반 접근 권한 검증.

    매트릭스(FR61 갱신):
    - master           : 항상 통과
    - operator         : admin_grade_page_permissions(operator, page_route)=true 이면 통과 (default true)
    - sub_operator     : admin_grade_page_permissions(sub_operator, page_route)=true 이면 통과 (default false)
    - pending          : get_current_admin 단계에서 이미 401로 차단됨
    - NULL (백필 누락) : 일단 통과 (operator 와 동일 취급)

    page_route 는 ADMIN_PAGE_ROUTES(admin_grade_permission_service)의 1차 라우트.
    """

    async def _checker(
        admin: User = Depends(get_current_admin),
        db: AsyncSession = Depends(get_session),
    ) -> User:
        # 지연 import — 순환 import 방지(service → deps 단방향 보장) + 테스트 monkeypatch 호환.
        from api.src.services import admin_grade_permission_service

        grade = getattr(admin, "admin_grade", None)
        if grade is None or grade == "master":
            return admin
        allowed = await admin_grade_permission_service.is_page_allowed(
            db, admin_grade=grade, page_route=page_route
        )
        if not allowed:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "ADMIN_FORBIDDEN_PAGE",
                    "message": "이 페이지 접근 권한이 없습니다.",
                },
            )
        return admin

    return _checker
