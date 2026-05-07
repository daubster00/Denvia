"""Story 5.5 — /api/v1/admin/analytics/revenue-variance/series 통합 테스트 (AC-2)."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest
from httpx import ASGITransport, AsyncClient

from api.src.main import app
from api.src.models.base import get_session
from api.src.deps.redis import get_redis_runtime
from api.src.settings import settings


def _admin_jwt() -> str:
    return pyjwt.encode(
        {"sub": "99", "aud": "denvia-admin", "exp": int(time.time()) + 3600},
        settings.denvia_jwt_secret,
        algorithm=settings.denvia_jwt_algorithm,
    )


def _admin_user() -> MagicMock:
    u = MagicMock()
    u.id = 99
    u.role = "admin"
    u.subscription_status = "free"
    u.segment = None
    u.withdrawn_at = None
    u.must_reset_password = False
    return u


def _stub_session():
    s = MagicMock()
    s.execute = AsyncMock()

    async def gen():
        yield s

    return gen


def _stub_redis():
    r = MagicMock()
    r.get = AsyncMock(return_value=None)

    async def gen():
        yield r

    return gen


def _series_payload(months: int = 12, to: str = "2026-05"):
    items = []
    # to_year_month부터 (months-1)개월 전까지 — 빈 월 0 채움
    y = int(to.split("-")[0])
    m = int(to.split("-")[1])
    cur_y, cur_m = y, m - (months - 1)
    while cur_m <= 0:
        cur_m += 12
        cur_y -= 1
    for _ in range(months):
        items.append(
            {
                "year_month": f"{cur_y:04d}-{cur_m:02d}",
                "revenue_krw": 0,
                "token_cost_krw": 0,
                "variance_krw": 0,
            }
        )
        cur_m += 1
        if cur_m > 12:
            cur_m = 1
            cur_y += 1

    return {
        "months": months,
        "to": to,
        "from": items[0]["year_month"],
        "usd_to_krw": 1400,
        "items": items,
    }


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
class TestRevenueSeriesEndpoint:
    async def _call(self, qs: str = ""):
        token = _admin_jwt()
        app.dependency_overrides[get_session] = _stub_session()
        app.dependency_overrides[get_redis_runtime] = _stub_redis()
        with patch(
            "api.src.deps.auth.get_user_by_id",
            new=AsyncMock(return_value=_admin_user()),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.get(
                    f"/api/v1/admin/analytics/revenue-variance/series{qs}",
                    cookies={"denvia_admin_session": token},
                )

    async def test_default_12_months(self):
        with patch(
            "api.src.routers.admin.analytics.get_revenue_variance_series",
            new=AsyncMock(return_value=_series_payload(12)),
        ) as p:
            res = await self._call()
        assert res.status_code == 200
        body = res.json()
        assert body["months"] == 12
        assert len(body["items"]) == 12
        assert body["usd_to_krw"] == 1400
        # alias `from` 직렬화 확인
        assert "from" in body
        assert p.call_args.kwargs["months"] == 12

    async def test_3_months(self):
        with patch(
            "api.src.routers.admin.analytics.get_revenue_variance_series",
            new=AsyncMock(return_value=_series_payload(3)),
        ):
            res = await self._call("?months=3")
        assert res.status_code == 200
        assert res.json()["months"] == 3
        assert len(res.json()["items"]) == 3

    async def test_24_months(self):
        with patch(
            "api.src.routers.admin.analytics.get_revenue_variance_series",
            new=AsyncMock(return_value=_series_payload(24)),
        ):
            res = await self._call("?months=24")
        assert res.status_code == 200
        assert res.json()["months"] == 24

    async def test_invalid_months_5_returns_422(self):
        res = await self._call("?months=5")
        assert res.status_code == 422

    async def test_invalid_months_0_returns_422(self):
        res = await self._call("?months=0")
        assert res.status_code == 422

    async def test_invalid_to_returns_422(self):
        res = await self._call("?to=2026-13")
        assert res.status_code == 422

    async def test_no_store_header(self):
        with patch(
            "api.src.routers.admin.analytics.get_revenue_variance_series",
            new=AsyncMock(return_value=_series_payload(12)),
        ):
            res = await self._call()
        assert res.headers.get("Cache-Control") == "no-store"

    async def test_empty_months_zero_filled(self):
        with patch(
            "api.src.routers.admin.analytics.get_revenue_variance_series",
            new=AsyncMock(return_value=_series_payload(12)),
        ):
            res = await self._call()
        for item in res.json()["items"]:
            assert item["revenue_krw"] == 0
            assert item["token_cost_krw"] == 0
            assert item["variance_krw"] == 0
