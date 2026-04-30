"""GET /api/v1/me/usage-summary 핸들러 단위 테스트 — Story 4.3 (AC-3, AC-4, AC-5).

라우터 핸들러를 직접 호출해 분기별 응답을 검증한다.
- pro / free / admin / segment is null 4분기
- show_subscribe_button True/False 분기 (FR48)
- month_count 0건 케이스
qa_service 헬퍼 재사용을 검증하기 위해 패치 없이 _resolve_bool/_resolve_daily_limit를
실 함수 그대로 사용하고 redis는 AsyncMock으로 시뮬레이션한다.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from api.src.routers.me import get_my_usage_summary
from api.src.services.qa_service import ADMIN_UNLIMITED_LIMIT


def _make_user(
    user_id: int = 1,
    subscription_status: str = "free",
    segment: str | None = "doctor",
    years_of_experience: int | None = 5,
    daily_quota_override: int | None = None,
) -> MagicMock:
    u = MagicMock()
    u.id = user_id
    u.subscription_status = subscription_status
    u.segment = segment
    u.years_of_experience = years_of_experience
    u.daily_quota_override = daily_quota_override
    u.free_delay_override = None
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


def _make_db(month_count: int = 0) -> AsyncMock:
    """SELECT COUNT(*) → scalar_one() = month_count."""
    result = MagicMock()
    result.scalar_one = MagicMock(return_value=month_count)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    return db


@pytest.mark.asyncio
class TestGetMyUsageSummaryHandler:
    async def test_free_user_with_usage_returns_full_payload(self):
        """무료 사용자 + Redis 키 존재 + show_subscribe_button True (default)."""
        user = _make_user(subscription_status="free", segment="doctor", years_of_experience=7)
        db = _make_db(month_count=42)
        rq = _make_redis_quota("5")
        rt = _make_redis_runtime({})  # 모든 토글 default(True) 또는 default 한도(10)

        res = await get_my_usage_summary(
            current_user=user, db=db, redis_quota=rq, redis_runtime=rt
        )

        assert res.month_question_count == 42
        assert res.daily_used == 5
        assert res.daily_limit == 10
        assert res.daily_remaining == 5
        assert res.subscription_status == "free"
        assert res.segment == "doctor"
        assert res.years_of_experience == 7
        assert res.show_subscribe_button is True
        assert "+09:00" in res.daily_reset_at

    async def test_free_user_zero_month_and_zero_used(self):
        """월 카운트 0건 + Redis miss."""
        user = _make_user(subscription_status="free")
        db = _make_db(month_count=0)
        rq = _make_redis_quota(None)
        rt = _make_redis_runtime({})

        res = await get_my_usage_summary(
            current_user=user, db=db, redis_quota=rq, redis_runtime=rt
        )

        assert res.month_question_count == 0
        assert res.daily_used == 0
        assert res.daily_remaining == res.daily_limit

    async def test_pro_user_zero_quota_and_no_subscribe_button(self):
        """Pro — daily_used=0, daily_limit=0, show_subscribe_button=False (이미 구독 중)."""
        user = _make_user(subscription_status="pro", segment="doctor", years_of_experience=10)
        db = _make_db(month_count=300)
        rq = _make_redis_quota("999")  # Pro 분기에서 Redis 미조회 — 무시되어야 함
        rt = _make_redis_runtime({"runtime:show_subscribe_button": "true"})

        res = await get_my_usage_summary(
            current_user=user, db=db, redis_quota=rq, redis_runtime=rt
        )

        assert res.subscription_status == "pro"
        assert res.month_question_count == 300
        assert res.daily_used == 0
        assert res.daily_limit == 0
        assert res.daily_remaining == 0
        assert res.show_subscribe_button is False

    async def test_admin_user_returns_unlimited_sentinel(self):
        """Admin — daily_limit=ADMIN_UNLIMITED_LIMIT, show_subscribe_button=False."""
        user = _make_user(subscription_status="admin", segment=None, years_of_experience=None)
        db = _make_db(month_count=12)
        rq = _make_redis_quota("10")  # admin 분기에서 무시
        rt = _make_redis_runtime({"runtime:show_subscribe_button": "true"})

        res = await get_my_usage_summary(
            current_user=user, db=db, redis_quota=rq, redis_runtime=rt
        )

        assert res.subscription_status == "admin"
        assert res.daily_used == 0
        assert res.daily_limit == ADMIN_UNLIMITED_LIMIT
        assert res.show_subscribe_button is False
        assert res.segment is None
        assert res.years_of_experience is None

    async def test_segment_null_is_passed_through(self):
        """segment is null + years_of_experience is null 분기 — 신규 가입 직후."""
        user = _make_user(subscription_status="free", segment=None, years_of_experience=None)
        db = _make_db(month_count=0)
        rq = _make_redis_quota(None)
        rt = _make_redis_runtime({})

        res = await get_my_usage_summary(
            current_user=user, db=db, redis_quota=rq, redis_runtime=rt
        )

        assert res.segment is None
        assert res.years_of_experience is None

    async def test_show_subscribe_button_false_when_runtime_off(self):
        """A-303 OFF (runtime:show_subscribe_button=false) → free 사용자도 False."""
        user = _make_user(subscription_status="free")
        db = _make_db(month_count=0)
        rq = _make_redis_quota(None)
        rt = _make_redis_runtime({"runtime:show_subscribe_button": "false"})

        res = await get_my_usage_summary(
            current_user=user, db=db, redis_quota=rq, redis_runtime=rt
        )

        assert res.show_subscribe_button is False

    async def test_user_override_quota_priority(self):
        """qa_service._resolve_daily_limit 재사용 검증 — user override > runtime."""
        user = _make_user(
            subscription_status="free",
            daily_quota_override=3,
        )
        db = _make_db(month_count=1)
        rq = _make_redis_quota("2")
        rt = _make_redis_runtime({"runtime:free_daily_quota": "100"})

        res = await get_my_usage_summary(
            current_user=user, db=db, redis_quota=rq, redis_runtime=rt
        )

        # user_override=3 우선 (runtime 100 무시)
        assert res.daily_limit == 3
        assert res.daily_used == 2
        assert res.daily_remaining == 1
