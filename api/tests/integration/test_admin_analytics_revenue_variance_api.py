"""Story 5.5 — /api/v1/admin/analytics/revenue-variance 단월 통합 테스트 (AC-1)."""

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


def _admin_jwt(user_id: int = 99) -> str:
    return pyjwt.encode(
        {"sub": str(user_id), "aud": "denvia-admin", "exp": int(time.time()) + 3600},
        settings.denvia_jwt_secret,
        algorithm=settings.denvia_jwt_algorithm,
    )


def _admin_user() -> MagicMock:
    u = MagicMock()
    u.id = 99
    u.email = "admin@denvia.local"
    u.role = "admin"
    u.subscription_status = "free"
    u.segment = None
    u.withdrawn_at = None
    u.must_reset_password = False
    u.current_session_id = None
    u.admin_grade = "master"
    return u


def _stub_session():
    s = MagicMock()
    s.execute = AsyncMock()
    s.commit = AsyncMock()

    async def gen():
        yield s

    return gen


def _stub_redis():
    r = MagicMock()
    r.get = AsyncMock(return_value=None)

    async def gen():
        yield r

    return gen


def _service_payload(year_month: str = "2026-05", **overrides):
    base = {
        "year_month": year_month,
        "revenue_krw": 1_485_000,
        "gross_revenue_krw": 1_485_000,
        "refund_krw": 0,
        "net_revenue_krw": 1_485_000,
        "token_cost_usd": "12.345600",
        "token_cost_krw": 17_284,
        "usd_to_krw": 1400,
        "variance_krw": 1_467_716,
        "error_count": 3,
        "anomaly_count": 12,
        "applied_filters": {
            "year_month": year_month,
            "kst_start": f"{year_month}-01T00:00:00+09:00",
            "kst_end_exclusive": "2026-06-01T00:00:00+09:00",
        },
    }
    base.update(overrides)
    # revenue_krw 만 override 한 테스트는 gross/net 도 함께 동기화 (환불 0 가정)
    if "revenue_krw" in overrides:
        base.setdefault("gross_revenue_krw", overrides["revenue_krw"])
        if "gross_revenue_krw" not in overrides:
            base["gross_revenue_krw"] = overrides["revenue_krw"]
        if "net_revenue_krw" not in overrides and "refund_krw" not in overrides:
            base["net_revenue_krw"] = overrides["revenue_krw"]
    return base


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
class TestRevenueVarianceAuth:
    async def test_unauthenticated_returns_401(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.get("/api/v1/admin/analytics/revenue-variance")
        assert res.status_code == 401

    async def test_non_admin_rejected(self):
        # require_admin은 non-admin도 401로 통일 거부 (Story 6.1 patch P12)
        non_admin = _admin_user()
        non_admin.role = "user"
        token = _admin_jwt()
        app.dependency_overrides[get_session] = _stub_session()
        app.dependency_overrides[get_redis_runtime] = _stub_redis()
        with patch(
            "api.src.deps.auth.get_user_by_id",
            new=AsyncMock(return_value=non_admin),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                res = await client.get(
                    "/api/v1/admin/analytics/revenue-variance",
                    cookies={"denvia_admin_session": token},
                )
        assert res.status_code in (401, 403)


@pytest.mark.asyncio
class TestRevenueVarianceEndpoint:
    async def _call(self, qs: str = ""):
        token = _admin_jwt()
        admin = _admin_user()
        app.dependency_overrides[get_session] = _stub_session()
        app.dependency_overrides[get_redis_runtime] = _stub_redis()
        with patch(
            "api.src.deps.auth.get_user_by_id",
            new=AsyncMock(return_value=admin),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.get(
                    f"/api/v1/admin/analytics/revenue-variance{qs}",
                    cookies={"denvia_admin_session": token},
                )

    async def test_default_current_month(self):
        with patch(
            "api.src.routers.admin.analytics.get_revenue_variance_month",
            new=AsyncMock(return_value=_service_payload()),
        ) as p:
            res = await self._call()
        assert res.status_code == 200
        assert res.headers.get("Cache-Control") == "no-store"
        body = res.json()
        assert body["year_month"] == "2026-05"
        assert body["revenue_krw"] == 1_485_000
        assert body["variance_krw"] == 1_467_716
        # 라우터가 _validate_year_month → kst_month_bounds 호출 (year_month 미지정 시)
        kwargs = p.call_args.kwargs
        assert "year_month" in kwargs

    async def test_specific_month(self):
        with patch(
            "api.src.routers.admin.analytics.get_revenue_variance_month",
            new=AsyncMock(return_value=_service_payload("2026-04")),
        ) as p:
            res = await self._call("?year_month=2026-04")
        assert res.status_code == 200
        assert res.json()["year_month"] == "2026-04"
        assert p.call_args.kwargs["year_month"] == "2026-04"

    async def test_year_month_invalid_format_422(self):
        res = await self._call("?year_month=2026-13")
        assert res.status_code == 422
        body = res.json()
        # FastAPI HTTPException detail wrapping
        detail = body.get("detail") if "detail" in body else body
        if isinstance(detail, dict):
            assert detail.get("code") == "INVALID_PARAM"

    async def test_year_month_invalid_string_422(self):
        res = await self._call("?year_month=abc")
        assert res.status_code == 422

    async def test_year_month_future_returns_zero(self):
        future_payload = _service_payload(
            "2099-01",
            revenue_krw=0,
            token_cost_usd="0.000000",
            token_cost_krw=0,
            variance_krw=0,
            error_count=0,
            anomaly_count=0,
        )
        with patch(
            "api.src.routers.admin.analytics.get_revenue_variance_month",
            new=AsyncMock(return_value=future_payload),
        ):
            res = await self._call("?year_month=2099-01")
        assert res.status_code == 200
        body = res.json()
        assert body["revenue_krw"] == 0
        assert body["token_cost_krw"] == 0
        assert body["variance_krw"] == 0

    async def test_negative_variance_passes_through(self):
        neg = _service_payload(
            revenue_krw=10_000,
            token_cost_krw=15_000,
            variance_krw=-5_000,
        )
        with patch(
            "api.src.routers.admin.analytics.get_revenue_variance_month",
            new=AsyncMock(return_value=neg),
        ):
            res = await self._call()
        assert res.status_code == 200
        assert res.json()["variance_krw"] == -5_000

    async def test_no_store_header_present(self):
        with patch(
            "api.src.routers.admin.analytics.get_revenue_variance_month",
            new=AsyncMock(return_value=_service_payload()),
        ):
            res = await self._call()
        assert res.headers.get("Cache-Control") == "no-store"

    async def test_response_schema_flat(self):
        with patch(
            "api.src.routers.admin.analytics.get_revenue_variance_month",
            new=AsyncMock(return_value=_service_payload()),
        ):
            res = await self._call()
        body = res.json()
        # AR27 flat — top-level keys + applied_filters (refund 분리 후 11 + applied_filters)
        for k in (
            "year_month",
            "revenue_krw",
            "gross_revenue_krw",
            "refund_krw",
            "net_revenue_krw",
            "token_cost_usd",
            "token_cost_krw",
            "usd_to_krw",
            "variance_krw",
            "error_count",
            "anomaly_count",
            "applied_filters",
        ):
            assert k in body
        assert "kst_start" in body["applied_filters"]
        assert "kst_end_exclusive" in body["applied_filters"]
