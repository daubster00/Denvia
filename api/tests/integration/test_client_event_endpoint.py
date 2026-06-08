"""POST /api/v1/events/client 통합 테스트 — Story 2.5."""

import time
from unittest.mock import MagicMock

import jwt as pyjwt
import pytest
from httpx import ASGITransport, AsyncClient

from api.src.deps.auth import get_current_user
from api.src.main import app
from api.src.models.user import User
from api.src.settings import settings


def _make_jwt(user_id: int = 1, role: str = "user", sub_status: str = "free") -> str:
    payload = {
        "sub": str(user_id),
        "role": role,
        "sub_status": sub_status,
        "exp": int(time.time()) + 3600,
    }
    return pyjwt.encode(payload, settings.denvia_jwt_secret, algorithm=settings.denvia_jwt_algorithm)


def _make_user(user_id: int = 1) -> MagicMock:
    u = MagicMock(spec=User)
    u.id = user_id
    u.subscription_status = "free"
    u.current_session_id = None
    u.admin_grade = "master"
    return u


class TestClientEventEndpoint:
    async def test_인증_사용자_POST_204(self):
        """인증 사용자 → 204 No Content."""
        user = _make_user()
        app.dependency_overrides[get_current_user] = lambda: user

        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post(
                    "/api/v1/events/client",
                    json={"event": "qa.conversation.reset"},
                    cookies={"denvia_session": _make_jwt()},
                )
            assert res.status_code == 204
            assert res.content == b""
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    async def test_미인증_401(self):
        """denvia_session 쿠키 없음 → 401."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.post(
                "/api/v1/events/client",
                json={"event": "qa.conversation.reset"},
            )
        assert res.status_code == 401

    async def test_event_필드_없음_422(self):
        """event 필드 없음 → 422 Unprocessable Entity."""
        user = _make_user()
        app.dependency_overrides[get_current_user] = lambda: user

        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post(
                    "/api/v1/events/client",
                    json={"trace_id": "abc"},
                    cookies={"denvia_session": _make_jwt()},
                )
            assert res.status_code == 422
        finally:
            app.dependency_overrides.pop(get_current_user, None)
