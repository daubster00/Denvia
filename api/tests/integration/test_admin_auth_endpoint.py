"""관리자 전용 로그인 엔드포인트 통합 테스트.

- /api/v1/admin/auth/login: role==admin만 통과, 비-admin은 동일 401
- 발급 쿠키: denvia_admin_session (path=/api/v1/admin)
- /api/v1/admin/auth/me: 미인증 401 / 인증 200
"""

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch

from api.src.main import app
from api.src.utils.argon2 import hash_password


def _make_user(role: str = "admin") -> MagicMock:
    user = MagicMock()
    user.id = 99
    user.email = "admin@denvia.local"
    user.role = role
    user.subscription_status = "free"
    user.password_hash = hash_password("password123")
    user.withdrawn_at = None
    user.current_session_id = None
    user.admin_grade = "master"
    # 명시적 None — production User 모델의 디폴트와 동일. MagicMock 자동 속성으로
    # 떨어지면 admin_blocked_until 가드가 datetime 비교 시 TypeError 를 던진다.
    user.admin_blocked_until = None
    return user


class TestAdminAuthLogin:
    async def test_관리자_로그인_성공_admin_쿠키_발급(self):
        admin = _make_user(role="admin")
        with patch("api.src.routers.admin.auth.login_user", new=AsyncMock(return_value=admin)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post(
                    "/api/v1/admin/auth/login",
                    json={"email": "admin@denvia.local", "password": "password123"},
                )

        assert res.status_code == 200
        body = res.json()
        assert body["user_id"] == 99
        assert body["role"] == "admin"

        # set-cookie 헤더 검사 — denvia_admin_session 포함 + path=/api/v1/admin
        set_cookie_headers = res.headers.get_list("set-cookie")
        joined = " ".join(set_cookie_headers)
        assert "denvia_admin_session=" in joined
        assert "Path=/api/v1/admin" in joined

    async def test_비_관리자_계정으로_로그인_시도_401(self):
        """role!=admin인 사용자는 비밀번호가 맞아도 동일 401 (계정 열거 방지)."""
        normal = _make_user(role="user")
        with patch("api.src.routers.admin.auth.login_user", new=AsyncMock(return_value=normal)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post(
                    "/api/v1/admin/auth/login",
                    json={"email": "user@denvia.local", "password": "password123"},
                )

        assert res.status_code == 401
        assert res.json()["code"] == "AUTH_INVALID_CREDENTIALS"

    async def test_logout_쿠키_즉시_만료(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.post("/api/v1/admin/auth/logout")

        assert res.status_code == 200
        set_cookie_headers = res.headers.get_list("set-cookie")
        joined = " ".join(set_cookie_headers)
        assert "denvia_admin_session=" in joined
        assert "Max-Age=0" in joined or "max-age=0" in joined

    async def test_me_미인증_401(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/admin/auth/me")
        assert res.status_code == 401
        assert res.json()["code"] == "ADMIN_AUTH_REQUIRED"
