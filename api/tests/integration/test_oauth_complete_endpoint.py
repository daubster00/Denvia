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
