"""POST /api/v1/auth/find-password 통합 테스트."""

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch

from api.src.main import app


class TestFindPasswordEndpoint:
    async def test_일반가입자_200_linked_providers_빈배열(self):
        """일반 가입자/미일치는 linked_providers=[] — 계정 열거 방지 유지."""
        with patch(
            "api.src.routers.auth.request_password_reset",
            new=AsyncMock(return_value=[]),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post(
                    "/api/v1/auth/find-password",
                    json={"email": "doc@denvia.com", "phone": "01012345678"},
                )

        assert res.status_code == 200
        assert res.json() == {"ok": True, "linked_providers": []}

    async def test_소셜전용_200_linked_providers_노출(self):
        """소셜 전용 계정은 연결된 provider 목록을 응답에 담아 반환."""
        with patch(
            "api.src.routers.auth.request_password_reset",
            new=AsyncMock(return_value=["kakao"]),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post(
                    "/api/v1/auth/find-password",
                    json={"email": "social@denvia.com", "phone": "01099998888"},
                )

        assert res.status_code == 200
        assert res.json() == {"ok": True, "linked_providers": ["kakao"]}

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
