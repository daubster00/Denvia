"""POST /api/v1/auth/oauth/complete 통합 테스트 — Story 1.6."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from api.src.main import app


def _user_mock(id=77):
    u = MagicMock()
    u.id = id
    u.email = "oauth@example.com"
    u.role = "user"
    u.subscription_status = "free"
    u.current_session_id = None
    u.admin_grade = "master"
    return u


class TestOAuthCompleteEndpoint:
    async def test_성공_200_쿠키_발급(self):
        user = _user_mock()
        with patch(
            "api.src.routers.auth.oauth_complete_phone_supplement",
            new=AsyncMock(return_value=user),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                res = await client.post(
                    "/api/v1/auth/oauth/complete",
                    json={
                        "signup_pending_token": "pt",
                        "phone": "01011112222",
                        "phone_verification_token": "pvt",
                    },
                )
        assert res.status_code == 200
        body = res.json()
        assert body["user_id"] == 77
        assert "denvia_session" in res.headers.get("set-cookie", "")

    async def test_pending_만료_400(self):
        with patch(
            "api.src.routers.auth.oauth_complete_phone_supplement",
            new=AsyncMock(
                side_effect=HTTPException(
                    status_code=400,
                    detail={"code": "OAUTH_PENDING_INVALID", "message": "expired"},
                )
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                res = await client.post(
                    "/api/v1/auth/oauth/complete",
                    json={
                        "signup_pending_token": "expired",
                        "phone": "01011112222",
                        "phone_verification_token": "pvt",
                    },
                )
        assert res.status_code == 400
        assert res.json()["code"] == "OAUTH_PENDING_INVALID"

    async def test_phone_충돌_409(self):
        with patch(
            "api.src.routers.auth.oauth_complete_phone_supplement",
            new=AsyncMock(
                side_effect=HTTPException(
                    status_code=409,
                    detail={"code": "OAUTH_PHONE_COLLISION", "message": "dup"},
                )
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                res = await client.post(
                    "/api/v1/auth/oauth/complete",
                    json={
                        "signup_pending_token": "pt",
                        "phone": "01011112222",
                        "phone_verification_token": "pvt",
                    },
                )
        assert res.status_code == 409
        assert res.json()["code"] == "OAUTH_PHONE_COLLISION"

    async def test_invalid_phone_422(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.post(
                "/api/v1/auth/oauth/complete",
                json={
                    "signup_pending_token": "pt",
                    "phone": "bad-phone",
                    "phone_verification_token": "pvt",
                },
            )
        assert res.status_code == 422

    async def test_empty_signup_pending_token_422(self):
        """signup_pending_token 빈 문자열은 min_length=1로 422."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.post(
                "/api/v1/auth/oauth/complete",
                json={
                    "signup_pending_token": "",
                    "phone": "01011112222",
                    "phone_verification_token": "pvt",
                },
            )
        assert res.status_code == 422

    async def test_oversize_token_422(self):
        """token max_length=128 초과 시 422."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.post(
                "/api/v1/auth/oauth/complete",
                json={
                    "signup_pending_token": "A" * 200,
                    "phone": "01011112222",
                    "phone_verification_token": "B" * 200,
                },
            )
        assert res.status_code == 422

    async def test_missing_required_field_422(self):
        """signup_pending_token 필드 누락 시 422."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.post(
                "/api/v1/auth/oauth/complete",
                json={
                    "phone": "01011112222",
                    "phone_verification_token": "pvt",
                },
            )
        assert res.status_code == 422

    async def test_sms_token_invalid_400(self):
        """서비스가 SMS_TOKEN_INVALID HTTPException → 400 매핑."""
        with patch(
            "api.src.routers.auth.oauth_complete_phone_supplement",
            new=AsyncMock(
                side_effect=HTTPException(
                    status_code=400,
                    detail={"code": "SMS_TOKEN_INVALID", "message": "bad sms token"},
                )
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                res = await client.post(
                    "/api/v1/auth/oauth/complete",
                    json={
                        "signup_pending_token": "pt",
                        "phone": "01011112222",
                        "phone_verification_token": "pvt",
                    },
                )
        assert res.status_code == 400
        assert res.json()["code"] == "SMS_TOKEN_INVALID"

    async def test_email_collision_409(self):
        with patch(
            "api.src.routers.auth.oauth_complete_phone_supplement",
            new=AsyncMock(
                side_effect=HTTPException(
                    status_code=409,
                    detail={
                        "code": "OAUTH_EMAIL_COLLISION_WITH_EMAIL_SIGNUP",
                        "message": "email signup exists",
                    },
                )
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                res = await client.post(
                    "/api/v1/auth/oauth/complete",
                    json={
                        "signup_pending_token": "pt",
                        "phone": "01011112222",
                        "phone_verification_token": "pvt",
                    },
                )
        assert res.status_code == 409
        assert res.json()["code"] == "OAUTH_EMAIL_COLLISION_WITH_EMAIL_SIGNUP"

    async def test_redis_error_503(self):
        """Redis 연결 실패 시 503 OAUTH_PROVIDER_UNAVAILABLE."""
        with patch(
            "api.src.routers.auth.oauth_complete_phone_supplement",
            new=AsyncMock(
                side_effect=HTTPException(
                    status_code=503,
                    detail={"code": "OAUTH_PROVIDER_UNAVAILABLE", "message": "redis down"},
                )
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                res = await client.post(
                    "/api/v1/auth/oauth/complete",
                    json={
                        "signup_pending_token": "pt",
                        "phone": "01011112222",
                        "phone_verification_token": "pvt",
                    },
                )
        assert res.status_code == 503
        assert res.json()["code"] == "OAUTH_PROVIDER_UNAVAILABLE"

    async def test_get_method_not_allowed(self):
        """GET /oauth/complete → 405 (POST 전용)."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.get("/api/v1/auth/oauth/complete")
        assert res.status_code == 405

    async def test_success_cookie_attributes(self):
        """성공 200 응답 쿠키가 HttpOnly / SameSite=lax / Path=/ / Max-Age=3600 / denvia_csrf 동반."""
        user = MagicMock()
        user.id = 77
        user.email = "oauth@example.com"
        user.role = "user"
        user.subscription_status = "free"
        with patch(
            "api.src.routers.auth.oauth_complete_phone_supplement",
            new=AsyncMock(return_value=user),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                res = await client.post(
                    "/api/v1/auth/oauth/complete",
                    json={
                        "signup_pending_token": "pt",
                        "phone": "01011112222",
                        "phone_verification_token": "pvt",
                    },
                )
        assert res.status_code == 200
        cookies_raw = "".join(
            v for k, v in res.headers.multi_items() if k.lower() == "set-cookie"
        )
        assert "denvia_session" in cookies_raw
        assert "denvia_csrf" in cookies_raw
        assert "HttpOnly" in cookies_raw
        assert "samesite=lax" in cookies_raw.lower()
        assert "path=/" in cookies_raw.lower()
        assert "max-age=3600" in cookies_raw.lower()
