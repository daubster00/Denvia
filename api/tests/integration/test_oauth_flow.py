"""OAuth 3종 콜백 통합 테스트 — Story 1.6.

oauth_callback 서비스를 monkeypatch로 mock 처리하여 라우터 분기별로
302 리다이렉트 · 쿠키 설정 · oauth_error 쿼리 파라미터를 검증한다.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from api.src.integrations.auth_providers.base import OAuthProviderUnavailable
from api.src.main import app
from api.src.models.base import get_session


def _user_mock(id=7, email="oa@example.com"):
    u = MagicMock()
    u.id = id
    u.email = email
    u.role = "user"
    u.subscription_status = "free"
    u.withdrawn_at = None
    return u


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


class TestAuthorizeEndpoint:
    async def test_authorize_302_provider_redirect(self):
        with patch(
            "api.src.routers.auth.oauth_start",
            new=AsyncMock(return_value="https://kauth.kakao.com/oauth/authorize?state=ABC"),
        ):
            async with await _client() as client:
                res = await client.get(
                    "/api/v1/auth/oauth/kakao/authorize?mode=login",
                    follow_redirects=False,
                )
        assert res.status_code == 302
        assert res.headers["location"].startswith("https://kauth.kakao.com/")

    async def test_authorize_unknown_provider_404(self):
        async with await _client() as client:
            res = await client.get(
                "/api/v1/auth/oauth/bogus/authorize",
                follow_redirects=False,
            )
        assert res.status_code == 404


class TestCallbackEndpoint:
    async def test_callback_cancelled_redirects_error(self):
        async with await _client() as client:
            res = await client.get(
                "/api/v1/auth/oauth/kakao/callback?error=access_denied",
                follow_redirects=False,
            )
        assert res.status_code == 302
        assert "oauth_error=OAUTH_CANCELLED" in res.headers["location"]

    async def test_callback_missing_state_redirects_error(self):
        async with await _client() as client:
            res = await client.get(
                "/api/v1/auth/oauth/kakao/callback?code=c",
                follow_redirects=False,
            )
        assert res.status_code == 302
        assert "oauth_error=OAUTH_STATE_INVALID" in res.headers["location"]

    async def test_callback_login_completed_sets_cookies(self):
        user = _user_mock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = user

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=result_mock)
        mock_session.commit = AsyncMock()

        async def _session_override():
            yield mock_session

        app.dependency_overrides[get_session] = _session_override
        try:
            with (
                patch(
                    "api.src.routers.auth.oauth_callback",
                    new=AsyncMock(return_value={"action": "login_completed", "user_id": 7}),
                ),
                patch("api.src.routers.auth.get_provider", new=lambda name: MagicMock()),
            ):
                async with await _client() as client:
                    res = await client.get(
                        "/api/v1/auth/oauth/kakao/callback?code=c&state=s",
                        follow_redirects=False,
                    )
        finally:
            app.dependency_overrides.pop(get_session, None)

        assert res.status_code == 302
        assert res.headers["location"].endswith("/")
        set_cookie = res.headers.get("set-cookie", "")
        assert "denvia_session" in set_cookie

    async def test_callback_signup_completed_full_redirects_segment(self):
        user = _user_mock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = user

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=result_mock)
        mock_session.commit = AsyncMock()

        async def _session_override():
            yield mock_session

        app.dependency_overrides[get_session] = _session_override
        try:
            with (
                patch(
                    "api.src.routers.auth.oauth_callback",
                    new=AsyncMock(
                        return_value={"action": "signup_completed_full", "user_id": 7}
                    ),
                ),
                patch("api.src.routers.auth.get_provider", new=lambda name: MagicMock()),
            ):
                async with await _client() as client:
                    res = await client.get(
                        "/api/v1/auth/oauth/naver/callback?code=c&state=s",
                        follow_redirects=False,
                    )
        finally:
            app.dependency_overrides.pop(get_session, None)

        assert res.status_code == 302
        assert "/signup/segment" in res.headers["location"]

    async def test_callback_signup_pending_phone_redirects_with_token(self):
        with (
            patch(
                "api.src.routers.auth.oauth_callback",
                new=AsyncMock(
                    return_value={
                        "action": "signup_pending_phone",
                        "signup_pending_token": "tok",
                        "provider": "google",
                    }
                ),
            ),
            patch("api.src.routers.auth.get_provider", new=lambda name: MagicMock()),
        ):
            async with await _client() as client:
                res = await client.get(
                    "/api/v1/auth/oauth/google/callback?code=c&state=s",
                    follow_redirects=False,
                )
        assert res.status_code == 302
        assert "/signup/phone-verify?token=tok" in res.headers["location"]

    async def test_callback_email_collision(self):
        with (
            patch(
                "api.src.routers.auth.oauth_callback",
                new=AsyncMock(return_value={"action": "email_collision"}),
            ),
            patch("api.src.routers.auth.get_provider", new=lambda name: MagicMock()),
        ):
            async with await _client() as client:
                res = await client.get(
                    "/api/v1/auth/oauth/kakao/callback?code=c&state=s",
                    follow_redirects=False,
                )
        assert res.status_code == 302
        assert "OAUTH_EMAIL_COLLISION_WITH_EMAIL_SIGNUP" in res.headers["location"]

    async def test_callback_phone_collision(self):
        with (
            patch(
                "api.src.routers.auth.oauth_callback",
                new=AsyncMock(return_value={"action": "phone_collision"}),
            ),
            patch("api.src.routers.auth.get_provider", new=lambda name: MagicMock()),
        ):
            async with await _client() as client:
                res = await client.get(
                    "/api/v1/auth/oauth/naver/callback?code=c&state=s",
                    follow_redirects=False,
                )
        assert res.status_code == 302
        assert "OAUTH_PHONE_COLLISION" in res.headers["location"]

    async def test_callback_provider_unavailable(self):
        with (
            patch(
                "api.src.routers.auth.oauth_callback",
                new=AsyncMock(side_effect=OAuthProviderUnavailable("kakao", "timeout")),
            ),
            patch("api.src.routers.auth.get_provider", new=lambda name: MagicMock()),
        ):
            async with await _client() as client:
                res = await client.get(
                    "/api/v1/auth/oauth/kakao/callback?code=c&state=s",
                    follow_redirects=False,
                )
        assert res.status_code == 302
        assert "OAUTH_PROVIDER_UNAVAILABLE" in res.headers["location"]

    async def test_callback_state_invalid(self):
        with (
            patch(
                "api.src.routers.auth.oauth_callback",
                new=AsyncMock(
                    side_effect=HTTPException(
                        status_code=400,
                        detail={"code": "OAUTH_STATE_INVALID", "message": "expired"},
                    )
                ),
            ),
            patch("api.src.routers.auth.get_provider", new=lambda name: MagicMock()),
        ):
            async with await _client() as client:
                res = await client.get(
                    "/api/v1/auth/oauth/kakao/callback?code=c&state=s",
                    follow_redirects=False,
                )
        assert res.status_code == 302
        assert "OAUTH_STATE_INVALID" in res.headers["location"]
