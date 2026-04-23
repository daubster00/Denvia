"""로그인/로그아웃 엔드포인트 통합 테스트 — httpx TestClient + mock."""

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch

from api.src.main import app
from api.src.utils.argon2 import hash_password


def _make_user(sub_status: str = "free") -> MagicMock:
    user = MagicMock()
    user.id = 1
    user.email = "doc@denvia.com"
    user.role = "user"
    user.subscription_status = sub_status
    user.password_hash = hash_password("password123")
    user.withdrawn_at = None
    return user


class TestLoginEndpoint:
    async def test_로그인_성공_200_쿠키_발급(self):
        user = _make_user()
        with (
            patch("api.src.services.auth_service._make_redis_rl") as mock_rl,
            patch("api.src.routers.auth.login_user", new=AsyncMock(return_value=user)),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post(
                    "/api/v1/auth/login",
                    json={"email": "doc@denvia.com", "password": "password123", "persist_session": False},
                )

        assert res.status_code == 200
        body = res.json()
        assert body["user_id"] == 1
        assert body["email"] == "doc@denvia.com"
        assert "denvia_session" in res.cookies or "set-cookie" in str(res.headers).lower()

    async def test_로그인_성공_persist_true_max_age_86400(self):
        user = _make_user()
        with patch("api.src.routers.auth.login_user", new=AsyncMock(return_value=user)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post(
                    "/api/v1/auth/login",
                    json={"email": "doc@denvia.com", "password": "password123", "persist_session": True},
                )

        assert res.status_code == 200
        set_cookie_header = res.headers.get("set-cookie", "")
        assert "max-age=86400" in set_cookie_header.lower()

    async def test_로그인_실패_401(self):
        from fastapi import HTTPException
        with patch(
            "api.src.routers.auth.login_user",
            new=AsyncMock(side_effect=HTTPException(
                status_code=401,
                detail={"code": "AUTH_INVALID_CREDENTIALS", "message": "이메일 또는 비밀번호가 일치하지 않습니다."},
            )),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post(
                    "/api/v1/auth/login",
                    json={"email": "doc@denvia.com", "password": "wrong", "persist_session": False},
                )

        assert res.status_code == 401
        assert res.json()["code"] == "AUTH_INVALID_CREDENTIALS"

    async def test_락아웃_중_429(self):
        from fastapi import HTTPException
        with patch(
            "api.src.routers.auth.login_user",
            new=AsyncMock(side_effect=HTTPException(
                status_code=429,
                detail={"code": "AUTH_TEMPORARILY_LOCKED", "message": "잠시 후 다시 시도해주세요."},
            )),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post(
                    "/api/v1/auth/login",
                    json={"email": "brute@denvia.com", "password": "anything", "persist_session": False},
                )

        assert res.status_code == 429
        assert res.json()["code"] == "AUTH_TEMPORARILY_LOCKED"

    async def test_차단_사용자_로그인_sub_status_blocked(self):
        user = _make_user(sub_status="blocked")
        with patch("api.src.routers.auth.login_user", new=AsyncMock(return_value=user)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post(
                    "/api/v1/auth/login",
                    json={"email": "blocked@denvia.com", "password": "password123", "persist_session": False},
                )

        assert res.status_code == 200
        assert res.json()["subscription_status"] == "blocked"

    async def test_로그아웃_200_쿠키_삭제(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.post("/api/v1/auth/logout")

        assert res.status_code == 200
        set_cookie = res.headers.get("set-cookie", "")
        assert "max-age=0" in set_cookie.lower()
