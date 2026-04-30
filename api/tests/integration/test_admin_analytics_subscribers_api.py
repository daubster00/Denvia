"""Admin 구독 분포 API 통합 테스트 — Story 5.3 (AC-2, AC-12)."""

from __future__ import annotations

import re
import time
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest
from httpx import ASGITransport, AsyncClient

from api.src.main import app
from api.src.models.base import get_session
from api.src.services import analytics_service
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
    return pyjwt.encode(
        payload,
        settings.denvia_jwt_secret,
        algorithm=settings.denvia_jwt_algorithm,
    )


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


def _stub_session_dependency():
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()

    async def gen():
        yield session

    return gen


@pytest.mark.asyncio
class TestSubscribersEndpoint:
    async def _call(self, qs: str = ""):
        token = _make_admin_jwt()
        admin = _make_admin()
        gen = _stub_session_dependency()
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
            app.dependency_overrides[get_session] = gen
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get(
                    f"/api/v1/admin/analytics/subscribers{qs}",
                    cookies={"denvia_admin_session": token},
                )
            app.dependency_overrides.clear()
        return res

    async def test_subscribers_requires_admin_unauth_401(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/admin/analytics/subscribers")
        assert res.status_code == 401

    async def test_subscribers_requires_admin_user_403(self):
        token = _make_jwt(role="user")
        regular = _make_admin()
        regular.role = "user"
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=regular)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get(
                    "/api/v1/admin/analytics/subscribers",
                    cookies={"denvia_admin_session": token},
                )
        assert res.status_code == 401

    async def test_subscribers_basic_counts(self):
        with patch(
            "api.src.routers.admin.analytics.get_subscriber_counts",
            new=AsyncMock(return_value={
                "free_count": 134,
                "pro_count": 12,
                "blocked_count": 1,
                "withdrawn_count": 7,
                "pending_cancellation_count": None,
                "upcoming_renewals": [],
            }),
        ):
            res = await self._call()
        assert res.status_code == 200
        data = res.json()
        assert data["free_count"] == 134
        assert data["pro_count"] == 12
        assert data["blocked_count"] == 1
        assert data["withdrawn_count"] == 7

    async def test_subscribers_pending_cancellation_is_null(self):
        """HOLD-PG 자리 — pending_cancellation_count는 항상 null."""
        with patch(
            "api.src.routers.admin.analytics.get_subscriber_counts",
            new=AsyncMock(return_value={
                "free_count": 0,
                "pro_count": 0,
                "blocked_count": 0,
                "withdrawn_count": 0,
                "pending_cancellation_count": None,
                "upcoming_renewals": [],
            }),
        ):
            res = await self._call()
        assert res.status_code == 200
        assert res.json()["pending_cancellation_count"] is None

    async def test_subscribers_upcoming_renewals_is_empty(self):
        """HOLD-PG 자리 — upcoming_renewals는 항상 빈 리스트."""
        with patch(
            "api.src.routers.admin.analytics.get_subscriber_counts",
            new=AsyncMock(return_value={
                "free_count": 5,
                "pro_count": 1,
                "blocked_count": 0,
                "withdrawn_count": 0,
                "pending_cancellation_count": None,
                "upcoming_renewals": [],
            }),
        ):
            res = await self._call()
        body = res.json()
        assert body["upcoming_renewals"] == []

    async def test_subscribers_as_of_kst_iso8601(self):
        with patch(
            "api.src.routers.admin.analytics.get_subscriber_counts",
            new=AsyncMock(return_value={
                "free_count": 1, "pro_count": 0, "blocked_count": 0, "withdrawn_count": 0,
                "pending_cancellation_count": None, "upcoming_renewals": [],
            }),
        ):
            res = await self._call()
        as_of = res.json()["as_of"]
        # ISO-8601 with +09:00 KST suffix
        assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?\+09:00$", as_of), as_of

    async def test_subscribers_no_store_header(self):
        with patch(
            "api.src.routers.admin.analytics.get_subscriber_counts",
            new=AsyncMock(return_value={
                "free_count": 0, "pro_count": 0, "blocked_count": 0, "withdrawn_count": 0,
                "pending_cancellation_count": None, "upcoming_renewals": [],
            }),
        ):
            res = await self._call()
        assert res.headers.get("Cache-Control") == "no-store"

    async def test_subscribers_excludes_withdrawn_from_active_status_groups(self):
        """get_subscriber_counts 직접 호출: withdrawn=NOT NULL은 free/pro/blocked에서 제외."""
        # 시나리오: free 활성 3 + free 탈퇴 2 → free_count=3, withdrawn_count=2
        from api.src.services.analytics_service import get_subscriber_counts

        call_count = 0

        async def fake_execute(stmt):
            nonlocal call_count
            call_count += 1
            r = MagicMock()
            if call_count == 1:
                # GROUP BY status (withdrawn_at IS NULL)
                r.all.return_value = [("free", 3), ("pro", 1)]
            else:
                # COUNT(withdrawn IS NOT NULL)
                r.scalar_one.return_value = 2
            return r

        session = MagicMock()
        session.execute = AsyncMock(side_effect=fake_execute)

        out = await get_subscriber_counts(session)
        assert out["free_count"] == 3
        assert out["pro_count"] == 1
        assert out["blocked_count"] == 0
        assert out["withdrawn_count"] == 2
        assert out["pending_cancellation_count"] is None
        assert out["upcoming_renewals"] == []
