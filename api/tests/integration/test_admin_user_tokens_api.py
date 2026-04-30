"""Admin 사용자별 토큰 API 통합 테스트 — Story 5.2 (AC-4)."""

from __future__ import annotations

import time
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest
from httpx import ASGITransport, AsyncClient

from api.src.main import app
from api.src.models.base import get_session
from api.src.settings import settings


def _make_jwt(role: str = "admin") -> str:
    if role == "admin":
        payload = {
            "sub": "1",
            "aud": "denvia-admin",
            "exp": int(time.time()) + 3600,
        }
    else:
        payload = {
            "sub": "1",
            "role": role,
            "sub_status": "free",
            "exp": int(time.time()) + 3600,
        }
    return pyjwt.encode(payload, settings.denvia_jwt_secret, algorithm=settings.denvia_jwt_algorithm)


def _make_admin_jwt(user_id: int = 99) -> str:
    """관리자 콘솔용 JWT (denvia_admin_session, aud=denvia-admin)."""
    payload = {
        "sub": str(user_id),
        "aud": "denvia-admin",
        "exp": int(time.time()) + 3600,
    }
    return pyjwt.encode(payload, settings.denvia_jwt_secret, algorithm=settings.denvia_jwt_algorithm)


def _make_admin():
    user = MagicMock()
    user.id = 1
    user.email = "admin@denvia.local"
    user.role = "admin"
    user.subscription_status = "free"
    user.segment = None
    user.withdrawn_at = None
    user.must_reset_password = False
    return user


def _build_row(user_id: int = 42, in_t: int = 1000, out_t: int = 500, cost: Decimal = Decimal("0.5"), q_cnt: int = 5):
    row = MagicMock()
    row.user_id = user_id
    row.in_t = in_t
    row.out_t = out_t
    row.cost = cost
    row.q_cnt = q_cnt
    return row


def _make_user_obj(user_id: int, email: str, segment: str | None = None, withdrawn: bool = False):
    u = MagicMock()
    u.id = user_id
    u.email = email
    u.segment = segment
    u.withdrawn_at = MagicMock() if withdrawn else None
    return u


def _mock_db(rows: list, total: int, users: list):
    call_count = 0

    async def execute(stmt):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            # total count
            result.scalar_one.return_value = total
        elif call_count == 2:
            # rows
            result.all.return_value = rows
        else:
            # users
            result.scalars.return_value.all.return_value = users
        return result

    session = MagicMock()
    session.execute = AsyncMock(side_effect=execute)
    session.commit = AsyncMock()

    async def gen():
        yield session

    return gen


@pytest.mark.asyncio
class TestUserTokensEndpoint:
    async def test_비인증_401(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/admin/analytics/user-tokens")
        assert res.status_code == 401

    async def test_일반유저_403(self):
        token = _make_jwt(role="user")
        user = _make_admin()
        user.role = "user"
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get(
                    "/api/v1/admin/analytics/user-tokens",
                    cookies={"denvia_admin_session": token},
                )
        assert res.status_code == 401

    async def test_기본_month_range_200(self):
        token = _make_admin_jwt()
        admin = _make_admin()
        row = _build_row()
        u = _make_user_obj(42, "user42@example.com", segment="dental_student")
        gen = _mock_db([row], total=1, users=[u])

        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
            app.dependency_overrides[get_session] = gen
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get(
                    "/api/v1/admin/analytics/user-tokens",
                    cookies={"denvia_admin_session": token},
                )
            app.dependency_overrides.clear()

        assert res.status_code == 200
        data = res.json()
        assert data["range"] == "month"
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["email"] == "user42@example.com"

    async def test_range_day_returns_no_year_month(self):
        token = _make_admin_jwt()
        admin = _make_admin()
        gen = _mock_db([], total=0, users=[])

        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
            app.dependency_overrides[get_session] = gen
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get(
                    "/api/v1/admin/analytics/user-tokens?range=day",
                    cookies={"denvia_admin_session": token},
                )
            app.dependency_overrides.clear()

        assert res.status_code == 200
        assert res.json()["year_month"] is None

    async def test_탈퇴_사용자_email_접미_표시(self):
        token = _make_admin_jwt()
        admin = _make_admin()
        row = _build_row(user_id=99)
        u = _make_user_obj(99, "gone@example.com", withdrawn=True)
        gen = _mock_db([row], total=1, users=[u])

        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
            app.dependency_overrides[get_session] = gen
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get(
                    "/api/v1/admin/analytics/user-tokens",
                    cookies={"denvia_admin_session": token},
                )
            app.dependency_overrides.clear()

        item = res.json()["items"][0]
        assert "(탈퇴)" in item["email"]

    async def test_per_page_200_최대(self):
        token = _make_admin_jwt()
        admin = _make_admin()
        gen = _mock_db([], total=0, users=[])

        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
            app.dependency_overrides[get_session] = gen
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get(
                    "/api/v1/admin/analytics/user-tokens?per_page=200",
                    cookies={"denvia_admin_session": token},
                )
            app.dependency_overrides.clear()

        assert res.status_code == 200

    async def test_per_page_201_422(self):
        token = _make_admin_jwt()
        admin = _make_admin()
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get(
                    "/api/v1/admin/analytics/user-tokens?per_page=201",
                    cookies={"denvia_admin_session": token},
                )
        assert res.status_code == 422
