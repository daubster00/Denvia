"""POST /api/v1/auth/find-password 통합 테스트."""

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch

from api.src.main import app


class TestFindPasswordEndpoint:
    async def test_항상_200_ok_반환(self):
        """계정 열거 방지 — 일치/불일치 관계없이 200 + {ok: true}."""
        with patch(
            "api.src.routers.auth.request_password_reset",
            new=AsyncMock(return_value=None),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post(
                    "/api/v1/auth/find-password",
                    json={"email": "doc@denvia.com", "phone": "01012345678"},
                )

        assert res.status_code == 200
        assert res.json() == {"ok": True}

    async def test_이메일_포맷_오류_422(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.post(
                "/api/v1/auth/find-password",
                json={"email": "not_an_email", "phone": "01012345678"},
            )
        assert res.status_code == 422

    async def test_휴대폰_포맷_오류_422(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.post(
                "/api/v1/auth/find-password",
                json={"email": "a@b.com", "phone": "0201234567"},
            )
        assert res.status_code == 422
