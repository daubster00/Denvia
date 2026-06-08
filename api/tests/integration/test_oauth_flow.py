"""OAuth 3종 콜백 통합 테스트 — Story 1.6.

oauth_callback 서비스를 monkeypatch로 mock 처리하여 라우터 분기별로
302 리다이렉트 · 쿠키 설정 · oauth_error 쿼리 파라미터를 검증한다.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from api.src.integrations.auth_providers.base import (
    OAuthProviderInvalidResponse,
    OAuthProviderUnavailable,
)
from api.src.main import app
from api.src.models.base import get_session


def _user_mock(id=7, email="oa@example.com"):
    u = MagicMock()
    u.id = id
    u.email = email
    u.role = "user"
    u.subscription_status = "free"
    u.withdrawn_at = None
    u.current_session_id = None
    u.admin_grade = "master"
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

    # ── AC-8 error 코드 분기 ────────────────────────────────────────────────

    async def test_callback_non_access_denied_error_maps_to_unavailable(self):
        """AC-8: error=server_error 등은 OAUTH_CANCELLED이 아닌 OAUTH_PROVIDER_UNAVAILABLE."""
        async with await _client() as client:
            res = await client.get(
                "/api/v1/auth/oauth/kakao/callback?error=server_error",
                follow_redirects=False,
            )
        assert res.status_code == 302
        assert "OAUTH_PROVIDER_UNAVAILABLE" in res.headers["location"]
        assert "OAUTH_CANCELLED" not in res.headers["location"]

    async def test_callback_error_invalid_request_maps_to_unavailable(self):
        async with await _client() as client:
            res = await client.get(
                "/api/v1/auth/oauth/kakao/callback?error=invalid_request",
                follow_redirects=False,
            )
        assert "OAUTH_PROVIDER_UNAVAILABLE" in res.headers["location"]

    async def test_callback_error_description_crlf_sanitized(self):
        """error_description에 CRLF 등 제어문자가 있어도 로그/리다이렉트 인젝션 없이 처리."""
        async with await _client() as client:
            res = await client.get(
                "/api/v1/auth/oauth/kakao/callback?error=access_denied&error_description=foo%0D%0AX-Evil:+1",
                follow_redirects=False,
            )
        assert res.status_code == 302
        # 리다이렉트 Location에 CR/LF이 그대로 반영되면 안 됨
        assert "\r" not in res.headers["location"]
        assert "\n" not in res.headers["location"]

    # ── 길이 상한·미지원 provider ────────────────────────────────────────────

    async def test_callback_oversize_state_rejected(self):
        """state가 상한(512)을 초과하면 OAUTH_STATE_INVALID — provider 호출 낭비 방지."""
        long_state = "A" * 600
        async with await _client() as client:
            res = await client.get(
                f"/api/v1/auth/oauth/kakao/callback?code=c&state={long_state}",
                follow_redirects=False,
            )
        assert res.status_code == 302
        assert "OAUTH_STATE_INVALID" in res.headers["location"]

    async def test_callback_oversize_code_rejected(self):
        """code가 상한(2048)을 초과하면 OAUTH_STATE_INVALID."""
        long_code = "C" * 3000
        async with await _client() as client:
            res = await client.get(
                f"/api/v1/auth/oauth/kakao/callback?code={long_code}&state=s",
                follow_redirects=False,
            )
        assert res.status_code == 302
        assert "OAUTH_STATE_INVALID" in res.headers["location"]

    async def test_callback_unknown_provider_path_error_redirect(self):
        async with await _client() as client:
            res = await client.get(
                "/api/v1/auth/oauth/facebook/callback?code=c&state=s",
                follow_redirects=False,
            )
        assert res.status_code == 302
        assert "OAUTH_PROVIDER_UNKNOWN" in res.headers["location"]

    # ── 예외 매핑 ──────────────────────────────────────────────────────────

    async def test_callback_provider_invalid_response_maps_to_unavailable(self):
        """OAuthProviderInvalidResponse도 사용자 노출 코드는 OAUTH_PROVIDER_UNAVAILABLE로 통합."""
        with (
            patch(
                "api.src.routers.auth.oauth_callback",
                new=AsyncMock(
                    side_effect=OAuthProviderInvalidResponse("kakao", "no email")
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
        assert "OAUTH_PROVIDER_UNAVAILABLE" in res.headers["location"]

    async def test_callback_unexpected_exception_becomes_unavailable(self):
        """일반 Exception은 500 HTML 대신 302 OAUTH_PROVIDER_UNAVAILABLE로 귀결 + db.rollback."""
        mock_session = MagicMock()
        mock_session.rollback = AsyncMock()
        mock_session.commit = AsyncMock()

        async def _session_override():
            yield mock_session

        app.dependency_overrides[get_session] = _session_override
        try:
            with (
                patch(
                    "api.src.routers.auth.oauth_callback",
                    new=AsyncMock(side_effect=RuntimeError("boom")),
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
        assert "OAUTH_PROVIDER_UNAVAILABLE" in res.headers["location"]
        mock_session.rollback.assert_awaited()

    async def test_callback_user_refetch_none_redirects_state_invalid(self):
        """login_completed 반환 후 user 재조회 None이면 OAUTH_STATE_INVALID."""
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=result_mock)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        async def _session_override():
            yield mock_session

        app.dependency_overrides[get_session] = _session_override
        try:
            with (
                patch(
                    "api.src.routers.auth.oauth_callback",
                    new=AsyncMock(return_value={"action": "login_completed", "user_id": 99}),
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
        assert "OAUTH_STATE_INVALID" in res.headers["location"]

    # ── 쿠키 속성·redirect origin 검증 ──────────────────────────────────────

    async def test_callback_login_cookie_attributes(self):
        """로그인 성공 쿠키가 HttpOnly / SameSite=lax / Path=/ / Max-Age=3600 / denvia_csrf 동반."""
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
        # httpx는 여러 Set-Cookie를 ", "로 join해서 하나의 헤더 값으로 노출.
        # 보안 속성별 포함 여부를 개별 검증.
        cookies_raw = "".join(
            v for k, v in res.headers.multi_items() if k.lower() == "set-cookie"
        )
        assert "denvia_session" in cookies_raw
        assert "denvia_csrf" in cookies_raw
        assert "HttpOnly" in cookies_raw
        assert "samesite=lax" in cookies_raw.lower()
        assert "path=/" in cookies_raw.lower()
        assert "max-age=3600" in cookies_raw.lower()

    async def test_callback_redirect_origin_stays_internal(self):
        """리다이렉트 Location은 프론트 origin(localhost:3000)에 고정 — open-redirect 회귀 방지."""
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
        loc = res.headers["location"]
        # localhost:3000 기본값 — 외부 도메인 아님
        assert loc.startswith("http://localhost:3000/"), f"unexpected origin: {loc}"


class TestAuthorizeMode:
    async def test_authorize_mode_signup_allowed(self):
        with patch(
            "api.src.routers.auth.oauth_start",
            new=AsyncMock(return_value="https://kauth.kakao.com/oauth/authorize?state=ABC"),
        ):
            async with await _client() as client:
                res = await client.get(
                    "/api/v1/auth/oauth/kakao/authorize?mode=signup",
                    follow_redirects=False,
                )
        assert res.status_code == 302

    async def test_authorize_mode_invalid_422(self):
        async with await _client() as client:
            res = await client.get(
                "/api/v1/auth/oauth/kakao/authorize?mode=hacker",
                follow_redirects=False,
            )
        assert res.status_code == 422


class TestAuthorizeNextParam:
    """AC-3: ?next= allowlist 검증 + state에 저장."""

    async def test_authorize_next_allowlist_passes(self):
        captured: dict = {}

        async def fake_start(provider, mode, p, redis_url, next_path=""):
            captured["next_path"] = next_path
            return "https://kauth.kakao.com/oauth/authorize?state=ABC"

        with patch("api.src.routers.auth.oauth_start", new=fake_start):
            async with await _client() as client:
                res = await client.get(
                    "/api/v1/auth/oauth/kakao/authorize?next=/dashboard",
                    follow_redirects=False,
                )
        assert res.status_code == 302
        assert captured["next_path"] == "/dashboard"

    async def test_authorize_next_external_url_rejected(self):
        """외부 URL은 allowlist 거부 → next_path=''으로 대체(open-redirect 방지)."""
        captured: dict = {}

        async def fake_start(provider, mode, p, redis_url, next_path=""):
            captured["next_path"] = next_path
            return "https://kauth.kakao.com/oauth/authorize?state=ABC"

        with patch("api.src.routers.auth.oauth_start", new=fake_start):
            async with await _client() as client:
                res = await client.get(
                    "/api/v1/auth/oauth/kakao/authorize?next=https://evil.com/hack",
                    follow_redirects=False,
                )
        assert res.status_code == 302
        assert captured["next_path"] == ""  # 거부됨

    async def test_authorize_next_protocol_relative_rejected(self):
        """'//evil.com' 같은 프로토콜 상대 경로도 거부."""
        captured: dict = {}

        async def fake_start(provider, mode, p, redis_url, next_path=""):
            captured["next_path"] = next_path
            return "https://kauth.kakao.com/oauth/authorize?state=ABC"

        with patch("api.src.routers.auth.oauth_start", new=fake_start):
            async with await _client() as client:
                res = await client.get(
                    "/api/v1/auth/oauth/kakao/authorize?next=//evil.com/",
                    follow_redirects=False,
                )
        assert captured["next_path"] == ""


class TestCallbackNextRedirect:
    """AC-3: login_completed 시 state 저장 next_path로 리다이렉트."""

    async def test_callback_login_next_path_redirect(self):
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
                        return_value={
                            "action": "login_completed",
                            "user_id": 7,
                            "next_path": "/dashboard",
                        }
                    ),
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
        # origin + next_path
        assert res.headers["location"].endswith("/dashboard")

    async def test_callback_login_unsafe_next_falls_back_to_root(self):
        """서비스가 잘못된 next_path를 리턴해도 라우터는 allowlist로 다시 검증해 `/`로 fallback."""
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
                        return_value={
                            "action": "login_completed",
                            "user_id": 7,
                            "next_path": "https://evil.com/hack",
                        }
                    ),
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
        loc = res.headers["location"]
        # 외부 URL 차단 — localhost:3000/ 으로 fallback
        assert loc.endswith("/")
        assert "evil.com" not in loc
