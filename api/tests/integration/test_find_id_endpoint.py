"""POST /api/v1/auth/find-id 통합 테스트."""

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException

from api.src.main import app


class TestFindIdEndpoint:
    async def test_성공_200_이메일_마스킹(self):
        with patch(
            "api.src.routers.auth.lookup_id",
            new=AsyncMock(return_value={
                "email_masked": "d****@denvia.com",
                "signup_method": "email",
            }),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post(
                    "/api/v1/auth/find-id",
                    json={"phone_verification_token": "valid_token"},
                )

        assert res.status_code == 200
        body = res.json()
        assert body["email_masked"] == "d****@denvia.com"
        assert body["signup_method"] == "email"

    async def test_불일치_200_null_반환(self):
        with patch(
            "api.src.routers.auth.lookup_id",
            new=AsyncMock(return_value={"email_masked": None, "signup_method": None}),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post(
                    "/api/v1/auth/find-id",
                    json={"phone_verification_token": "no_match_token"},
                )

        assert res.status_code == 200
        body = res.json()
        assert body["email_masked"] is None
        assert body["signup_method"] is None

    async def test_토큰_재사용_400(self):
        with patch(
            "api.src.routers.auth.lookup_id",
            new=AsyncMock(side_effect=HTTPException(
                status_code=400,
                detail={"code": "SMS_TOKEN_INVALID", "message": "휴대폰 인증이 필요합니다."},
            )),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post(
                    "/api/v1/auth/find-id",
                    json={"phone_verification_token": "expired_token"},
                )

        assert res.status_code == 400
        assert res.json()["code"] == "SMS_TOKEN_INVALID"
