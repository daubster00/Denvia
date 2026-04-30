"""POST /api/v1/support/inquiries 통합 테스트 — Story 4.5 (T4.6)."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from api.src.deps.auth import get_current_user
from api.src.main import app
from api.src.models.base import get_session
from api.src.models.user import User


def _make_user(user_id: int = 1) -> MagicMock:
    u = MagicMock(spec=User)
    u.id = user_id
    u.email = "user@example.com"
    return u


def _stub_session():
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.refresh = AsyncMock()

    async def gen():
        yield session

    return gen


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
class TestSupportInquiryEndpoint:
    async def test_unauth_returns_401(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.post(
                "/api/v1/support/inquiries",
                json={"subject": "test", "body": "test"},
            )
        assert res.status_code == 401

    async def test_subject_blank_returns_422(self, monkeypatch):
        user = _make_user()
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = _stub_session()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.post(
                "/api/v1/support/inquiries",
                json={"subject": "", "body": "정상 본문"},
            )
        assert res.status_code == 422

    async def test_body_too_long_returns_422(self, monkeypatch):
        user = _make_user()
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = _stub_session()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.post(
                "/api/v1/support/inquiries",
                json={"subject": "OK", "body": "a" * 5001},
            )
        assert res.status_code == 422

    async def test_submit_success_returns_201(self, monkeypatch):
        user = _make_user()
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = _stub_session()

        async def _submit(db, user_id, subject, body):
            return 88

        monkeypatch.setattr(
            "api.src.routers.support.support_service.submit_inquiry", _submit
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.post(
                "/api/v1/support/inquiries",
                json={"subject": "결제 문의", "body": "두 번 청구되었습니다."},
            )
        assert res.status_code == 201, res.json()
        assert res.json() == {"inquiry_id": 88}
