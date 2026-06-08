"""Admin 가입자 추세 API 통합 테스트 — Story 5.3 (AC-1, AC-3, AC-12)."""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest
from httpx import ASGITransport, AsyncClient

from api.src.main import app
from api.src.models.base import get_session
from api.src.services import analytics_service
from api.src.services.analytics_service import SignupsBucket
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
    user.current_session_id = None
    user.admin_grade = "master"
    return user


def _stub_session_dependency():
    """get_session override — 어차피 service 함수가 patch되므로 빈 session."""
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()

    async def gen():
        yield session

    return gen


@pytest.mark.asyncio
class TestSignupsEndpointAuth:
    async def test_signups_requires_admin_unauth_401(self):
        """미인증은 401."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/admin/analytics/signups")
        assert res.status_code == 401

    async def test_signups_requires_admin_user_403(self):
        """일반 user는 ADMIN_FORBIDDEN 401."""
        token = _make_jwt(role="user")
        regular = _make_admin()
        regular.role = "user"
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=regular)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get(
                    "/api/v1/admin/analytics/signups",
                    cookies={"denvia_admin_session": token},
                )
        assert res.status_code == 401


@pytest.mark.asyncio
class TestSignupsEndpoint:
    async def _call(self, qs: str = ""):
        token = _make_admin_jwt()
        admin = _make_admin()
        gen = _stub_session_dependency()
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
            app.dependency_overrides[get_session] = gen
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get(
                    f"/api/v1/admin/analytics/signups{qs}",
                    cookies={"denvia_admin_session": token},
                )
            app.dependency_overrides.clear()
        return res

    async def test_signups_default_month_range(self):
        """기본 unit=month 12 버킷."""
        buckets = [
            SignupsBucket(bucket_start=date(2025, 5, 1), cumulative=1, active=1, withdrawn=0),
            SignupsBucket(bucket_start=date(2025, 6, 1), cumulative=2, active=2, withdrawn=0),
        ]
        with patch(
            "api.src.routers.admin.analytics.get_signups_buckets",
            new=AsyncMock(return_value=(buckets, date(2025, 5, 1), date(2026, 4, 30))),
        ):
            res = await self._call()
        assert res.status_code == 200
        data = res.json()
        assert data["unit"] == "month"
        assert data["from"] == "2025-05-01"
        assert data["to"] == "2026-04-30"
        assert len(data["buckets"]) == 2
        assert data["buckets"][0]["bucket_start"] == "2025-05-01"
        assert data["buckets"][0]["cumulative"] == 1

    async def test_signups_unit_day(self):
        """unit=day."""
        buckets = [
            SignupsBucket(bucket_start=date(2026, 4, 27), cumulative=10, active=9, withdrawn=1),
        ]
        with patch(
            "api.src.routers.admin.analytics.get_signups_buckets",
            new=AsyncMock(return_value=(buckets, date(2026, 3, 30), date(2026, 4, 29))),
        ):
            res = await self._call("?unit=day")
        assert res.status_code == 200
        body = res.json()
        assert body["unit"] == "day"

    async def test_signups_unit_week(self):
        with patch(
            "api.src.routers.admin.analytics.get_signups_buckets",
            new=AsyncMock(return_value=([], date(2026, 2, 1), date(2026, 4, 29))),
        ):
            res = await self._call("?unit=week")
        assert res.status_code == 200
        assert res.json()["unit"] == "week"

    async def test_signups_unit_year(self):
        with patch(
            "api.src.routers.admin.analytics.get_signups_buckets",
            new=AsyncMock(return_value=([], date(2022, 1, 1), date(2026, 4, 29))),
        ):
            res = await self._call("?unit=year")
        assert res.status_code == 200
        assert res.json()["unit"] == "year"

    async def test_signups_no_store_header(self):
        with patch(
            "api.src.routers.admin.analytics.get_signups_buckets",
            new=AsyncMock(return_value=([], date(2026, 1, 1), date(2026, 4, 29))),
        ):
            res = await self._call()
        assert res.headers.get("Cache-Control") == "no-store"

    async def test_signups_invalid_unit_422(self):
        """unit=hour 같이 enum 외 값은 422."""
        res = await self._call("?unit=hour")
        # Auth fail가 아니라 validation fail이어야 함 — admin auth는 세팅됨
        assert res.status_code == 422

    async def test_signups_explicit_from_to(self):
        """from/to 명시 시 그대로 응답."""
        buckets = [
            SignupsBucket(bucket_start=date(2026, 1, 1), cumulative=5, active=4, withdrawn=1),
        ]
        with patch(
            "api.src.routers.admin.analytics.get_signups_buckets",
            new=AsyncMock(return_value=(buckets, date(2026, 1, 1), date(2026, 4, 1))),
        ):
            res = await self._call("?unit=month&from=2026-01-01&to=2026-04-01")
        assert res.status_code == 200
        assert res.json()["from"] == "2026-01-01"
        assert res.json()["to"] == "2026-04-01"


@pytest.mark.asyncio
class TestSignupsBucketLogic:
    """analytics_service 핵심 로직 단위 검증."""

    async def test_kst_bucketing_helpers(self):
        from api.src.services.analytics_service import _truncate_to_unit, _next_bucket
        # 2026-04-29 (수) → 일요일 시작 주: 2026-04-26
        assert _truncate_to_unit(date(2026, 4, 29), "week") == date(2026, 4, 26)
        # 일요일 자체는 그대로
        assert _truncate_to_unit(date(2026, 4, 26), "week") == date(2026, 4, 26)
        # month start
        assert _truncate_to_unit(date(2026, 4, 29), "month") == date(2026, 4, 1)
        # year start
        assert _truncate_to_unit(date(2026, 4, 29), "year") == date(2026, 1, 1)
        # _next_bucket
        assert _next_bucket(date(2026, 12, 1), "month") == date(2027, 1, 1)
        assert _next_bucket(date(2026, 4, 26), "week") == date(2026, 5, 3)
        assert _next_bucket(date(2026, 4, 29), "day") == date(2026, 4, 30)
        assert _next_bucket(date(2026, 1, 1), "year") == date(2027, 1, 1)

    async def test_signups_cumulative_monotonic_via_service(self):
        """daily 가입/탈퇴 dict + blocked=0 stub으로 prefix-sum 단조성 검증."""
        from api.src.services.analytics_service import (
            get_signups_buckets,
            _daily_counts_kst,
        )

        # 가짜 session: _daily_counts_kst 두 번 + blocked count 1번 호출됨
        # mocked dict: 2026-01-15 가입 1명, 2026-02-10 가입 2명, 2026-03-01 탈퇴 1명
        signups = {date(2026, 1, 15): 1, date(2026, 2, 10): 2}
        withdrawals = {date(2026, 3, 1): 1}

        async def fake_daily(session, column, extra_where=None):
            # column 식별: User.created_at vs User.withdrawn_at
            from api.src.models.user import User as _U
            if column is _U.created_at:
                return dict(signups)
            return dict(withdrawals)

        # blocked count = 0
        scalar_result = MagicMock()
        scalar_result.scalar_one.return_value = 0
        session = MagicMock()
        session.execute = AsyncMock(return_value=scalar_result)

        with patch.object(analytics_service, "_daily_counts_kst", new=fake_daily):
            buckets, frm, to = await get_signups_buckets(
                session, "month", date(2026, 1, 1), date(2026, 4, 1)
            )

        # 4개 버킷: 1월/2월/3월/4월
        assert [b.bucket_start for b in buckets] == [
            date(2026, 1, 1),
            date(2026, 2, 1),
            date(2026, 3, 1),
            date(2026, 4, 1),
        ]
        # cumulative: 1, 3, 3, 3 (단조 증가)
        cumulative_values = [b.cumulative for b in buckets]
        assert cumulative_values == sorted(cumulative_values)
        assert cumulative_values == [1, 3, 3, 3]
        # withdrawn: 0, 0, 1, 1
        assert [b.withdrawn for b in buckets] == [0, 0, 1, 1]
        # active = cumulative - withdrawn (blocked=0)
        assert [b.active for b in buckets] == [1, 3, 2, 2]

    async def test_signups_empty_bucket_zero_filled(self):
        """가입 데이터 없는 버킷도 0으로 채워서 응답에 포함."""
        from api.src.services.analytics_service import get_signups_buckets

        async def fake_daily(session, column, extra_where=None):
            return {}

        scalar_result = MagicMock()
        scalar_result.scalar_one.return_value = 0
        session = MagicMock()
        session.execute = AsyncMock(return_value=scalar_result)

        with patch.object(analytics_service, "_daily_counts_kst", new=fake_daily):
            buckets, _, _ = await get_signups_buckets(
                session, "month", date(2026, 1, 1), date(2026, 4, 1)
            )
        assert len(buckets) == 4
        for b in buckets:
            assert b.cumulative == 0
            assert b.active == 0
            assert b.withdrawn == 0

    async def test_signups_active_excludes_blocked_in_last_bucket(self):
        """blocked는 마지막 버킷 active에서만 차감."""
        from api.src.services.analytics_service import get_signups_buckets

        async def fake_daily(session, column, extra_where=None):
            from api.src.models.user import User as _U
            if column is _U.created_at:
                return {date(2026, 1, 15): 5}
            return {}

        scalar_result = MagicMock()
        scalar_result.scalar_one.return_value = 1  # blocked 1명
        session = MagicMock()
        session.execute = AsyncMock(return_value=scalar_result)

        with patch.object(analytics_service, "_daily_counts_kst", new=fake_daily):
            buckets, _, _ = await get_signups_buckets(
                session, "month", date(2026, 1, 1), date(2026, 3, 1)
            )
        # 마지막 버킷(2026-03)에서만 active = cumulative - withdrawn - blocked
        assert buckets[-1].cumulative == 5
        assert buckets[-1].withdrawn == 0
        assert buckets[-1].active == 4  # 5 - 0 - 1
        # 이전 버킷은 blocked 미반영
        assert buckets[0].active == 5
