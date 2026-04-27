"""GET /api/v1/me/quota 통합 테스트 — Story 2.3 (AC-6)."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from api.src.deps.auth import get_current_user
from api.src.deps.redis import get_redis_quota, get_redis_runtime
from api.src.main import app
from api.src.models.user import User


def _make_user(
    user_id: int = 1,
    subscription_status: str = "free",
    daily_quota_override: int | None = None,
    free_delay_override: int | None = None,
) -> MagicMock:
    u = MagicMock(spec=User)
    u.id = user_id
    u.subscription_status = subscription_status
    u.daily_quota_override = daily_quota_override
    u.free_delay_override = free_delay_override
    return u


def _make_redis_quota(used_value: str | None = None) -> AsyncMock:
    r = AsyncMock()
    r.get = AsyncMock(return_value=used_value)
    return r


def _make_redis_runtime(values: dict | None = None) -> AsyncMock:
    vals = values or {}

    async def _get(key: str) -> str | None:
        return vals.get(key)

    r = AsyncMock()
    r.get = _get
    return r


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


class TestGetMyQuotaEndpoint:
    @pytest.mark.asyncio
    async def test_free_user_with_usage(self):
        """무료 사용자 — 7회 사용, 한도 10, remaining=3."""
        user = _make_user(subscription_status="free")
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_redis_quota] = lambda: _make_redis_quota("7")
        app.dependency_overrides[get_redis_runtime] = lambda: _make_redis_runtime({
            "runtime:free_daily_quota": "10",
            "runtime:free_delay_enabled": "true",
            "runtime:free_delay": "3",
            "runtime:show_upgrade_prompt": "true",
            "runtime:show_subscribe_button": "true",
        })

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/me/quota")

        assert res.status_code == 200
        body = res.json()
        assert body["subscription_status"] == "free"
        assert body["daily_limit"] == 10
        assert body["used_today"] == 7
        assert body["remaining"] == 3
        assert body["delay_seconds"] == 3
        assert body["show_upgrade_prompt"] is True
        assert body["show_subscribe_button"] is True
        assert "+09:00" in body["reset_at"]

    @pytest.mark.asyncio
    async def test_free_user_no_key_means_zero(self):
        """Redis 키 부재(오늘 0회) — used_today=0, remaining=daily_limit."""
        user = _make_user(subscription_status="free")
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_redis_quota] = lambda: _make_redis_quota(None)
        app.dependency_overrides[get_redis_runtime] = lambda: _make_redis_runtime({})

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/me/quota")

        assert res.status_code == 200
        body = res.json()
        assert body["used_today"] == 0
        assert body["remaining"] == body["daily_limit"]

    @pytest.mark.asyncio
    async def test_admin_user_bypasses_quota_consistent_with_preflight(self):
        """admin — preflight 우회와 일관: 큰 unlimited sentinel·used_today=0·delay 0·prompt 비노출.

        Redis에 잔존 quota 키가 있더라도 admin은 0으로 보고해야 한다.
        """
        from api.src.services.qa_service import ADMIN_UNLIMITED_LIMIT

        user = _make_user(subscription_status="admin")
        app.dependency_overrides[get_current_user] = lambda: user
        # 잔존 키가 있어도 admin 분기는 무시해야 한다.
        app.dependency_overrides[get_redis_quota] = lambda: _make_redis_quota("42")
        app.dependency_overrides[get_redis_runtime] = lambda: _make_redis_runtime({
            "runtime:free_daily_quota": "10",
            "runtime:free_delay": "3",
            "runtime:show_upgrade_prompt": "true",
            "runtime:show_subscribe_button": "true",
        })

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/me/quota")

        assert res.status_code == 200
        body = res.json()
        assert body["subscription_status"] == "admin"
        assert body["daily_limit"] == ADMIN_UNLIMITED_LIMIT
        assert body["remaining"] == ADMIN_UNLIMITED_LIMIT
        assert body["used_today"] == 0
        assert body["delay_seconds"] == 0
        assert body["show_upgrade_prompt"] is False
        assert body["show_subscribe_button"] is False

    @pytest.mark.asyncio
    async def test_pro_user_returns_cap_and_zero_delay(self):
        """유료 사용자 — daily_limit=500, delay_seconds=0, show_upgrade_prompt=false."""
        user = _make_user(subscription_status="pro")
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_redis_quota] = lambda: _make_redis_quota("0")
        app.dependency_overrides[get_redis_runtime] = lambda: _make_redis_runtime({
            "runtime:pro_internal_cap": "500",
            "runtime:free_delay": "3",
        })

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/me/quota")

        assert res.status_code == 200
        body = res.json()
        assert body["subscription_status"] == "pro"
        assert body["daily_limit"] == 500
        assert body["delay_seconds"] == 0
        assert body["show_upgrade_prompt"] is False
        assert body["show_subscribe_button"] is False
