"""Admin 예산 API 통합 테스트 — Story 5.2 (AC-3, RBAC, no-store)."""

from __future__ import annotations

import time
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest
from httpx import ASGITransport, AsyncClient

from api.src.deps.redis import get_redis_runtime
from api.src.main import app
from api.src.models.base import get_session
from api.src.settings import settings


async def _fake_redis_runtime():
    """get_redis_runtime override — .get(KEY) → None → DEFAULT_USD_TO_KRW(1400) 폴백 경로."""
    mock = MagicMock()
    mock.get = AsyncMock(return_value=None)
    yield mock


def _make_jwt(role: str = "admin", sub_status: str = "free") -> str:
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
            "sub_status": sub_status,
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


def _make_user(role: str = "admin"):
    user = MagicMock()
    user.id = 1
    user.email = "admin@denvia.local"
    user.role = role
    user.subscription_status = "free"
    user.segment = None
    user.withdrawn_at = None
    user.must_reset_password = False
    user.current_session_id = None
    user.admin_grade = "master"
    return user


def _mock_db_with_budget(spent: Decimal = Decimal("10.00"), limit: Decimal = Decimal("100.00"), modes: list = None):
    """budget 엔드포인트 응답용 DB session mock."""
    from api.src.models.budget_threshold import BudgetThreshold
    from api.src.models.killswitch_state import KillswitchState

    threshold = MagicMock(spec=BudgetThreshold)
    threshold.year_month = "2026-04"
    threshold.monthly_limit_usd = limit

    call_count = 0

    async def execute(stmt):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            # SUM(cost_usd)
            result.scalar_one.return_value = spent
        elif call_count == 2:
            # SELECT BudgetThreshold
            result.scalar_one_or_none.return_value = threshold
        else:
            # SELECT KillswitchState.mode
            result.scalars.return_value.all.return_value = modes or []
        return result

    session = MagicMock()
    session.execute = AsyncMock(side_effect=execute)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    async def gen():
        yield session

    return gen


@pytest.mark.asyncio
class TestBudgetCurrentMonthEndpoint:
    async def test_비인증_401(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/admin/budget/current-month")
        assert res.status_code == 401

    async def test_일반유저_403(self):
        token = _make_jwt(role="user")
        user = _make_user(role="user")
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get(
                    "/api/v1/admin/budget/current-month",
                    cookies={"denvia_admin_session": token},
                )
        assert res.status_code == 401

    async def test_관리자_200_응답_형태(self):
        token = _make_admin_jwt()
        user = _make_user(role="admin")
        gen = _mock_db_with_budget(spent=Decimal("12.34"), limit=Decimal("100.00"), modes=[])
        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)),
            patch.object(app, "dependency_overrides", {get_session: gen}),
        ):
            app.dependency_overrides[get_session] = gen
            app.dependency_overrides[get_redis_runtime] = _fake_redis_runtime
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get(
                    "/api/v1/admin/budget/current-month",
                    cookies={"denvia_admin_session": token},
                )
            app.dependency_overrides.clear()

        assert res.status_code == 200
        data = res.json()
        assert "year_month" in data
        assert "spent_usd" in data
        assert "monthly_limit_usd" in data
        assert "percent" in data
        assert "status" in data
        assert "killswitch_active" in data
        assert data["killswitch_active"] is False

    async def test_cache_control_no_store(self):
        token = _make_admin_jwt()
        user = _make_user(role="admin")
        gen = _mock_db_with_budget(modes=[])
        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)),
        ):
            app.dependency_overrides[get_session] = gen
            app.dependency_overrides[get_redis_runtime] = _fake_redis_runtime
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get(
                    "/api/v1/admin/budget/current-month",
                    cookies={"denvia_admin_session": token},
                )
            app.dependency_overrides.clear()

        assert "no-store" in res.headers.get("cache-control", "").lower()

    async def test_killswitch_활성_시_killswitch_mode_반환(self):
        token = _make_admin_jwt()
        user = _make_user(role="admin")
        gen = _mock_db_with_budget(modes=["auto_free_only"])
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)):
            app.dependency_overrides[get_session] = gen
            app.dependency_overrides[get_redis_runtime] = _fake_redis_runtime
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get(
                    "/api/v1/admin/budget/current-month",
                    cookies={"denvia_admin_session": token},
                )
            app.dependency_overrides.clear()

        data = res.json()
        assert data["killswitch_active"] is True
        assert data["killswitch_mode"] == "auto_free_only"

    async def test_manual_total이_auto_보다_우선(self):
        token = _make_admin_jwt()
        user = _make_user(role="admin")
        gen = _mock_db_with_budget(modes=["auto_free_only", "manual_total"])
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)):
            app.dependency_overrides[get_session] = gen
            app.dependency_overrides[get_redis_runtime] = _fake_redis_runtime
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get(
                    "/api/v1/admin/budget/current-month",
                    cookies={"denvia_admin_session": token},
                )
            app.dependency_overrides.clear()

        data = res.json()
        assert data["killswitch_mode"] == "manual_total"

    async def test_status_분류_정상(self):
        token = _make_admin_jwt()
        user = _make_user(role="admin")
        # 12.34 / 100.00 = 12.34% → normal
        gen = _mock_db_with_budget(spent=Decimal("12.34"), limit=Decimal("100.00"), modes=[])
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)):
            app.dependency_overrides[get_session] = gen
            app.dependency_overrides[get_redis_runtime] = _fake_redis_runtime
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get(
                    "/api/v1/admin/budget/current-month",
                    cookies={"denvia_admin_session": token},
                )
            app.dependency_overrides.clear()

        data = res.json()
        assert data["status"] == "normal"
        assert data["percent"] == pytest.approx(12.34, abs=0.01)
