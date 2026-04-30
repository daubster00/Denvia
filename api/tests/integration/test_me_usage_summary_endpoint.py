"""GET /api/v1/me/usage-summary 통합 테스트 — Story 4.3 (AC-3, AC-4).

라우터 레이어를 ASGI 스택으로 호출해 인증 가드 + 응답 스키마 + 분기를 검증한다.
DB는 _stub_session()으로 SELECT COUNT(*) 결과만 모킹.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from api.src.deps.auth import get_current_user
from api.src.deps.redis import get_redis_quota, get_redis_runtime
from api.src.main import app
from api.src.models.base import get_session
from api.src.models.user import User
from api.src.services.qa_service import ADMIN_UNLIMITED_LIMIT


def _make_user(
    user_id: int = 1,
    subscription_status: str = "free",
    segment: str | None = "doctor",
    years_of_experience: int | None = 5,
    daily_quota_override: int | None = None,
) -> MagicMock:
    u = MagicMock(spec=User)
    u.id = user_id
    u.subscription_status = subscription_status
    u.segment = segment
    u.years_of_experience = years_of_experience
    u.daily_quota_override = daily_quota_override
    u.free_delay_override = None
    return u


def _stub_session(month_count: int = 0):
    """SELECT COUNT(*) 응답만 모킹하는 단순 세션 generator."""
    result = MagicMock()
    result.scalar_one = MagicMock(return_value=month_count)
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()

    async def gen():
        yield session

    return gen


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


@pytest.mark.asyncio
class TestUsageSummaryEndpoint:
    async def test_unauth_returns_401(self):
        """쿠키 없음 → 401 (Depends(get_current_user) 자동 처리)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/me/usage-summary")
        assert res.status_code == 401
        assert res.json()["code"] == "AUTH_NOT_AUTHENTICATED"

    async def test_free_user_full_payload(self):
        """무료 사용자 — 응답 9필드 정합성 검증."""
        user = _make_user(subscription_status="free", segment="doctor", years_of_experience=7)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = _stub_session(month_count=42)
        app.dependency_overrides[get_redis_quota] = lambda: _make_redis_quota("5")
        app.dependency_overrides[get_redis_runtime] = lambda: _make_redis_runtime({
            "runtime:free_daily_quota": "10",
            "runtime:show_subscribe_button": "true",
        })

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/me/usage-summary")

        assert res.status_code == 200
        body = res.json()
        assert set(body.keys()) == {
            "month_question_count",
            "daily_used",
            "daily_limit",
            "daily_remaining",
            "daily_reset_at",
            "subscription_status",
            "segment",
            "years_of_experience",
            "show_subscribe_button",
        }
        assert body["month_question_count"] == 42
        assert body["daily_used"] == 5
        assert body["daily_limit"] == 10
        assert body["daily_remaining"] == 5
        assert body["subscription_status"] == "free"
        assert body["segment"] == "doctor"
        assert body["years_of_experience"] == 7
        assert body["show_subscribe_button"] is True
        assert "+09:00" in body["daily_reset_at"]

    async def test_pro_user_no_subscribe_button(self):
        """Pro — daily 0/0/0, show_subscribe_button=False, segment/연차 그대로 전달."""
        user = _make_user(subscription_status="pro", segment="hygienist", years_of_experience=3)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = _stub_session(month_count=120)
        app.dependency_overrides[get_redis_quota] = lambda: _make_redis_quota("999")
        app.dependency_overrides[get_redis_runtime] = lambda: _make_redis_runtime({
            "runtime:show_subscribe_button": "true",
        })

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/me/usage-summary")

        assert res.status_code == 200
        body = res.json()
        assert body["subscription_status"] == "pro"
        assert body["month_question_count"] == 120
        assert body["daily_used"] == 0
        assert body["daily_limit"] == 0
        assert body["daily_remaining"] == 0
        assert body["show_subscribe_button"] is False
        assert body["segment"] == "hygienist"
        assert body["years_of_experience"] == 3

    async def test_admin_user_unlimited(self):
        """Admin — daily_limit = ADMIN_UNLIMITED_LIMIT, show_subscribe_button=False."""
        user = _make_user(subscription_status="admin", segment=None, years_of_experience=None)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = _stub_session(month_count=0)
        app.dependency_overrides[get_redis_quota] = lambda: _make_redis_quota("42")
        app.dependency_overrides[get_redis_runtime] = lambda: _make_redis_runtime({
            "runtime:show_subscribe_button": "true",
        })

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/me/usage-summary")

        assert res.status_code == 200
        body = res.json()
        assert body["subscription_status"] == "admin"
        assert body["daily_limit"] == ADMIN_UNLIMITED_LIMIT
        assert body["daily_used"] == 0
        assert body["show_subscribe_button"] is False
        assert body["segment"] is None
        assert body["years_of_experience"] is None

    async def test_a303_toggle_off_hides_subscribe_button(self):
        """A-303 OFF — runtime:show_subscribe_button=false → False."""
        user = _make_user(subscription_status="free")
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = _stub_session(month_count=0)
        app.dependency_overrides[get_redis_quota] = lambda: _make_redis_quota(None)
        app.dependency_overrides[get_redis_runtime] = lambda: _make_redis_runtime({
            "runtime:show_subscribe_button": "false",
        })

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/me/usage-summary")

        assert res.status_code == 200
        assert res.json()["show_subscribe_button"] is False
