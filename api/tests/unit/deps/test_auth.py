"""require_admin / get_current_admin Depends 단위 테스트.

관리자 세션 분리 이후의 계약:
- 관리자 API는 denvia_admin_session 쿠키만 인정한다.
- 일반 denvia_session 쿠키는 admin role이라도 401 (admin 콘솔용 토큰이 아니므로).
"""

import time

import jwt as pyjwt
import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, MagicMock

from api.src.main import app
from api.src.models.base import get_session
from api.src.settings import settings


def _make_user_jwt(user_id: int = 1, role: str = "user", sub_status: str = "free") -> str:
    """일반 사이트용 JWT (denvia_session 쿠키 페이로드)."""
    payload = {
        "sub": str(user_id),
        "role": role,
        "sub_status": sub_status,
        "exp": int(time.time()) + 3600,
    }
    return pyjwt.encode(payload, settings.denvia_jwt_secret, algorithm=settings.denvia_jwt_algorithm)


def _make_admin_jwt(user_id: int = 99) -> str:
    """관리자 콘솔용 JWT (denvia_admin_session 쿠키 페이로드, aud=denvia-admin)."""
    payload = {
        "sub": str(user_id),
        "aud": "denvia-admin",
        "exp": int(time.time()) + 3600,
    }
    return pyjwt.encode(payload, settings.denvia_jwt_secret, algorithm=settings.denvia_jwt_algorithm)


def _make_user(role: str = "admin"):
    user = MagicMock()
    user.id = 99
    user.email = "admin@denvia.local"
    user.role = role
    user.subscription_status = "free"
    user.segment = None
    user.years_of_experience = None
    user.withdrawn_at = None
    user.must_reset_password = False
    return user


async def _mock_empty_db():
    """audit-logs 조회 — 빈 결과를 반환하는 mock 세션."""
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = 0
    mock_result.scalars.return_value.all.return_value = []

    session = MagicMock()
    session.execute = AsyncMock(return_value=mock_result)
    yield session


class TestRequireAdmin:
    async def test_쿠키_없음_401(self):
        """denvia_admin_session 쿠키 없음 → 401 ADMIN_AUTH_REQUIRED."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/admin/audit-logs")
        assert res.status_code == 401
        assert res.json()["code"] == "ADMIN_AUTH_REQUIRED"

    async def test_일반_세션쿠키만_있으면_401(self):
        """일반 denvia_session 쿠키만 있는 경우(admin role이라도) → 401.

        관리자 API는 별도 출입증(denvia_admin_session)만 인정하므로 일반 쿠키는 무시된다.
        """
        token = _make_user_jwt(user_id=99, role="admin")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get(
                "/api/v1/admin/audit-logs",
                cookies={"denvia_session": token},
            )
        assert res.status_code == 401
        assert res.json()["code"] == "ADMIN_AUTH_REQUIRED"

    async def test_admin_쿠키_있고_role도_admin_200(self):
        """denvia_admin_session 쿠키 + DB 사용자 role=admin → 200."""
        token = _make_admin_jwt(user_id=99)
        user = _make_user(role="admin")

        app.dependency_overrides[get_session] = _mock_empty_db
        from unittest.mock import patch
        try:
            with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.get(
                        "/api/v1/admin/audit-logs",
                        cookies={"denvia_admin_session": token},
                    )
        finally:
            app.dependency_overrides.pop(get_session, None)

        assert res.status_code == 200

    async def test_admin_쿠키_있어도_DB의_role이_admin_아니면_401(self):
        """role 박탈/탈퇴 등 admin 자격이 없어진 사용자는 즉시 거부."""
        token = _make_admin_jwt(user_id=99)
        user = _make_user(role="user")  # 더 이상 admin이 아님

        app.dependency_overrides[get_session] = _mock_empty_db
        from unittest.mock import patch
        try:
            with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.get(
                        "/api/v1/admin/audit-logs",
                        cookies={"denvia_admin_session": token},
                    )
        finally:
            app.dependency_overrides.pop(get_session, None)

        assert res.status_code == 401
        assert res.json()["code"] == "ADMIN_AUTH_REQUIRED"

    async def test_일반_유저_쿠키를_admin쿠키로_재사용_시도_401(self):
        """aud 클레임 없는 일반 토큰을 denvia_admin_session으로 보내면 거부."""
        token = _make_user_jwt(user_id=99, role="admin")  # aud 없음
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get(
                "/api/v1/admin/audit-logs",
                cookies={"denvia_admin_session": token},
            )
        assert res.status_code == 401
        assert res.json()["code"] == "ADMIN_AUTH_REQUIRED"


class TestGetCurrentUserBlocked:
    """get_current_user — blocked 계정 403 체크 (Issue 1 fix)."""

    async def test_blocked_user_gets_403_on_protected_endpoint(self):
        """subscription_status='blocked' 사용자가 일반 API(qa/stream이 아닌 간단한 엔드포인트) 접근 시 403."""
        token = _make_user_jwt(user_id=1)

        blocked_user = _make_user(role="user")
        blocked_user.subscription_status = "blocked"
        blocked_user.withdrawn_at = None

        app.dependency_overrides[get_session] = _mock_empty_db
        from unittest.mock import patch
        try:
            with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=blocked_user)):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.get(
                        "/api/v1/me/quota",
                        cookies={"denvia_session": token},
                    )
        finally:
            app.dependency_overrides.pop(get_session, None)

        assert res.status_code == 403
        assert res.json()["code"] == "ACCOUNT_BLOCKED"

    async def test_blocked_user_can_access_me_endpoint(self):
        """GET /api/v1/me는 blocked 사용자도 통과 — 프론트가 상태를 감지해 /blocked로 redirect."""
        token = _make_user_jwt(user_id=1)

        blocked_user = _make_user(role="user")
        blocked_user.subscription_status = "blocked"
        blocked_user.withdrawn_at = None

        app.dependency_overrides[get_session] = _mock_empty_db
        from unittest.mock import patch
        try:
            with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=blocked_user)):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.get(
                        "/api/v1/me",
                        cookies={"denvia_session": token},
                    )
        finally:
            app.dependency_overrides.pop(get_session, None)

        assert res.status_code == 200
        assert res.json()["subscription_status"] == "blocked"

    async def test_non_blocked_user_passes_normally(self):
        """subscription_status='free' 사용자는 정상 통과."""
        token = _make_user_jwt(user_id=1)

        free_user = _make_user(role="user")
        free_user.subscription_status = "free"
        free_user.withdrawn_at = None
        # me 엔드포인트 필요 필드
        free_user.segment = None
        free_user.years_of_experience = None
        free_user.must_reset_password = False

        app.dependency_overrides[get_session] = _mock_empty_db
        from unittest.mock import patch
        try:
            with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=free_user)):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.get(
                        "/api/v1/me",
                        cookies={"denvia_session": token},
                    )
        finally:
            app.dependency_overrides.pop(get_session, None)

        assert res.status_code == 200
