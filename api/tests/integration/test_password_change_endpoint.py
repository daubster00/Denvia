"""POST /api/v1/me/password 통합 테스트."""

import time
import pytest
import jwt as pyjwt
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch

from api.src.main import app
from api.src.settings import settings
from api.src.utils.argon2 import hash_password


def _make_jwt(user_id: int = 1, role: str = "user", sub_status: str = "free") -> str:
    payload = {
        "sub": str(user_id),
        "role": role,
        "sub_status": sub_status,
        "exp": int(time.time()) + 3600,
    }
    return pyjwt.encode(payload, settings.denvia_jwt_secret, algorithm=settings.denvia_jwt_algorithm)


@pytest.fixture
def mock_user():
    user = MagicMock()
    user.id = 1
    user.email = "doc@denvia.com"
    user.role = "user"
    user.subscription_status = "free"
    user.segment = None
    user.years_of_experience = None
    user.withdrawn_at = None
    user.password_hash = hash_password("temp1234")
    user.must_reset_password = True
    user.updated_at = None
    return user


class TestPasswordChangeEndpoint:
    async def test_성공_200_쿠키_재발급(self, mock_user):
        token = _make_jwt(user_id=1)

        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=mock_user)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post(
                    "/api/v1/me/password",
                    json={"new_password": "newpass99"},
                    cookies={"denvia_session": token},
                )

        assert res.status_code == 200
        assert res.json() == {"ok": True}
        assert "denvia_session" in res.cookies or "set-cookie" in str(res.headers).lower()

    async def test_미로그인_401(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.post(
                "/api/v1/me/password",
                json={"new_password": "newpass99"},
            )

        assert res.status_code == 401

    async def test_8자_미만_422(self, mock_user):
        token = _make_jwt(user_id=1)

        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=mock_user)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post(
                    "/api/v1/me/password",
                    json={"new_password": "short"},
                    cookies={"denvia_session": token},
                )

        assert res.status_code == 422
