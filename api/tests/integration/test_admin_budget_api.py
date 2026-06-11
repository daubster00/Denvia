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


@pytest.mark.asyncio
class TestBudgetCurrentMonthYmParam:
    """`/current-month?ym=YYYY-MM` — 과거 월 조회 옵션."""

    async def test_과거월_조회_성공_is_past_month_true(self):
        from api.src.services.budget_service import CurrentMonthSnapshot
        token = _make_admin_jwt()
        user = _make_user(role="admin")

        snap = CurrentMonthSnapshot(
            year_month="2026-05",
            monthly_limit_usd=Decimal("100.00"),
            spent_usd=Decimal("42.50"),
            percent=42.5,
            status="normal",
        )

        async def fake_snapshot(session, ym=None):
            assert ym == "2026-05"
            return snap

        async def fake_modes(session):
            return set()

        session = MagicMock()
        session.commit = AsyncMock()

        async def gen():
            yield session

        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)),
            patch("api.src.routers.admin.budget.get_current_month_snapshot", new=AsyncMock(side_effect=fake_snapshot)),
            patch("api.src.routers.admin.budget.get_active_modes", new=AsyncMock(side_effect=fake_modes)),
        ):
            app.dependency_overrides[get_session] = gen
            app.dependency_overrides[get_redis_runtime] = _fake_redis_runtime
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get(
                    "/api/v1/admin/budget/current-month?ym=2026-05",
                    cookies={"denvia_admin_session": token},
                )
            app.dependency_overrides.clear()

        assert res.status_code == 200
        data = res.json()
        assert data["year_month"] == "2026-05"
        assert data["is_past_month"] is True
        # 과거 월은 killswitch 마스킹 — 현재 상태 false로 응답.
        assert data["killswitch_active"] is False
        assert data["killswitch_mode"] is None
        # KRW 환산: 42.50 * 1400 = 59500
        assert data["spent_krw"] == 59500

    async def test_미래월_조회_422(self):
        token = _make_admin_jwt()
        user = _make_user(role="admin")
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                # 9999-12는 확실히 미래
                res = await client.get(
                    "/api/v1/admin/budget/current-month?ym=9999-12",
                    cookies={"denvia_admin_session": token},
                )
        assert res.status_code == 422

    async def test_ym_형식_불량_422(self):
        token = _make_admin_jwt()
        user = _make_user(role="admin")
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                # 13월
                res_bad_month = await client.get(
                    "/api/v1/admin/budget/current-month?ym=2026-13",
                    cookies={"denvia_admin_session": token},
                )
                # 자유 문자열
                res_garbage = await client.get(
                    "/api/v1/admin/budget/current-month?ym=hello",
                    cookies={"denvia_admin_session": token},
                )
        assert res_bad_month.status_code == 422
        assert res_garbage.status_code == 422

    async def test_ym_없으면_현재월_is_past_month_false(self):
        """ym 파라미터 없으면 기존 동작 — 현재 월, is_past_month=false."""
        token = _make_admin_jwt()
        user = _make_user(role="admin")
        gen = _mock_db_with_budget(modes=[])
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)):
            app.dependency_overrides[get_session] = gen
            app.dependency_overrides[get_redis_runtime] = _fake_redis_runtime
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get(
                    "/api/v1/admin/budget/current-month",
                    cookies={"denvia_admin_session": token},
                )
            app.dependency_overrides.clear()
        assert res.status_code == 200
        assert res.json()["is_past_month"] is False
