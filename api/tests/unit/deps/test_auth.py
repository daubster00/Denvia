"""require_admin Depends 단위 테스트."""

import time
import pytest
import jwt as pyjwt
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock

from api.src.main import app
from api.src.settings import settings
from api.src.models.base import get_session


def _make_jwt(user_id: int = 1, role: str = "user", sub_status: str = "free") -> str:
    payload = {
        "sub": str(user_id),
        "role": role,
        "sub_status": sub_status,
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
        """denvia_session 쿠키 없음 → 401 AUTH_NOT_AUTHENTICATED."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/admin/audit-logs")
        assert res.status_code == 401
        assert res.json()["code"] == "AUTH_NOT_AUTHENTICATED"

    async def test_일반_유저_403(self):
        """role=user 쿠키 → 403 ADMIN_ACCESS_REQUIRED."""
        token = _make_jwt(user_id=1, role="user")
        user = _make_user(role="user")

        from unittest.mock import patch
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get(
                    "/api/v1/admin/audit-logs",
                    cookies={"denvia_session": token},
                )
        assert res.status_code == 403
        assert res.json()["code"] == "ADMIN_ACCESS_REQUIRED"

    async def test_관리자_200(self):
        """role=admin 쿠키 → 200 (audit-logs 엔드포인트)."""
        token = _make_jwt(user_id=99, role="admin")
        user = _make_user(role="admin")

        app.dependency_overrides[get_session] = _mock_empty_db
        from unittest.mock import patch
        try:
            with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.get(
                        "/api/v1/admin/audit-logs",
                        cookies={"denvia_session": token},
                    )
        finally:
            app.dependency_overrides.pop(get_session, None)

        assert res.status_code == 200
