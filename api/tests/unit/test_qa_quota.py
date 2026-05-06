"""_resolve_daily_limit / _resolve_delay / _today_key_kst 단위 테스트 — Story 2.3."""

import pytest
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

from api.src.services.qa_service import (
    _resolve_daily_limit,
    _resolve_delay,
    _today_key_kst,
    DEFAULT_FREE_DAILY_QUOTA,
    DEFAULT_PRO_INTERNAL_CAP,
    DEFAULT_FREE_DELAY_SECONDS,
    KST,
)


def _make_user(
    subscription_status: str = "free",
    daily_quota_override: int | None = None,
    free_delay_override: Decimal | int | None = None,
) -> MagicMock:
    u = MagicMock()
    u.id = 42
    u.subscription_status = subscription_status
    u.daily_quota_override = daily_quota_override
    u.free_delay_override = free_delay_override
    return u


def _make_runtime(values: dict) -> AsyncMock:
    """fakeredis 대신 AsyncMock으로 단순 runtime GET 시뮬레이션."""
    redis = AsyncMock()

    async def _get(key: str) -> str | None:
        return values.get(key)

    redis.get = _get
    return redis


# ── _today_key_kst ────────────────────────────────────────────────────────────

class TestTodayKeyKst:
    def test_key_format_contains_user_id_and_kst_date(self):
        key = _today_key_kst(99)
        today_kst = datetime.now(tz=KST).strftime("%Y-%m-%d")
        assert key == f"quota:user:99:{today_kst}"

    def test_key_uses_kst_not_utc(self):
        """KST(Asia/Seoul) 날짜 문자열이 포함된다 — UTC와 최대 9시간 차이."""
        key = _today_key_kst(1)
        kst_date = datetime.now(tz=ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d")
        assert kst_date in key


# ── _resolve_daily_limit ──────────────────────────────────────────────────────

class TestResolveDailyLimit:
    @pytest.mark.asyncio
    async def test_pro_returns_pro_internal_cap_from_redis(self):
        user = _make_user("pro")
        rt = _make_runtime({"runtime:pro_internal_cap": "200"})
        limit, src = await _resolve_daily_limit(user, rt)
        assert limit == 200
        assert src == "pro_internal"

    @pytest.mark.asyncio
    async def test_pro_uses_default_cap_when_redis_missing(self):
        user = _make_user("pro")
        rt = _make_runtime({})
        limit, src = await _resolve_daily_limit(user, rt)
        assert limit == DEFAULT_PRO_INTERNAL_CAP
        assert src == "pro_internal"

    @pytest.mark.asyncio
    async def test_user_override_takes_priority_over_runtime(self):
        user = _make_user("free", daily_quota_override=3)
        rt = _make_runtime({"runtime:free_daily_quota": "50"})
        limit, src = await _resolve_daily_limit(user, rt)
        assert limit == 3
        assert src == "user_override"

    @pytest.mark.asyncio
    async def test_user_override_zero_means_instant_block(self):
        """0은 즉시 차단 — NULL과 명확 구분 (AC-2)."""
        user = _make_user("free", daily_quota_override=0)
        rt = _make_runtime({"runtime:free_daily_quota": "10"})
        limit, src = await _resolve_daily_limit(user, rt)
        assert limit == 0
        assert src == "user_override"

    @pytest.mark.asyncio
    async def test_runtime_value_used_when_no_override(self):
        user = _make_user("free", daily_quota_override=None)
        rt = _make_runtime({"runtime:free_daily_quota": "7"})
        limit, src = await _resolve_daily_limit(user, rt)
        assert limit == 7
        assert src == "runtime"

    @pytest.mark.asyncio
    async def test_default_fallback(self):
        user = _make_user("free", daily_quota_override=None)
        rt = _make_runtime({})
        limit, src = await _resolve_daily_limit(user, rt)
        assert limit == DEFAULT_FREE_DAILY_QUOTA
        assert src == "default"


# ── _resolve_delay ────────────────────────────────────────────────────────────

class TestResolveDelay:
    @pytest.mark.asyncio
    async def test_pro_always_zero(self):
        user = _make_user("pro")
        rt = _make_runtime({"runtime:free_delay": "5"})
        delay, src = await _resolve_delay(user, rt)
        assert delay == 0
        assert src == "paid_skip"

    @pytest.mark.asyncio
    async def test_admin_always_zero(self):
        user = _make_user("admin")
        rt = _make_runtime({"runtime:free_delay": "5"})
        delay, src = await _resolve_delay(user, rt)
        assert delay == 0
        assert src == "paid_skip"

    @pytest.mark.asyncio
    async def test_user_override_takes_priority(self):
        user = _make_user("free", free_delay_override=7)
        rt = _make_runtime({"runtime:free_delay": "3", "runtime:free_delay_enabled": "true"})
        delay, src = await _resolve_delay(user, rt)
        assert delay == 7
        assert src == "user_override"

    @pytest.mark.asyncio
    async def test_user_override_zero_means_no_delay(self):
        """0은 개별 지연 OFF — NULL과 명확 구분 (AC-3)."""
        user = _make_user("free", free_delay_override=0)
        rt = _make_runtime({"runtime:free_delay": "3", "runtime:free_delay_enabled": "true"})
        delay, src = await _resolve_delay(user, rt)
        assert delay == 0
        assert src == "user_override"

    @pytest.mark.asyncio
    async def test_runtime_disabled_returns_zero(self):
        user = _make_user("free", free_delay_override=None)
        rt = _make_runtime({"runtime:free_delay_enabled": "false", "runtime:free_delay": "3"})
        delay, src = await _resolve_delay(user, rt)
        assert delay == 0
        assert src == "runtime_disabled"

    @pytest.mark.asyncio
    async def test_runtime_delay_used(self):
        user = _make_user("free", free_delay_override=None)
        rt = _make_runtime({"runtime:free_delay_enabled": "true", "runtime:free_delay": "5"})
        delay, src = await _resolve_delay(user, rt)
        assert delay == 5
        assert src == "runtime"

    @pytest.mark.asyncio
    async def test_default_fallback(self):
        user = _make_user("free", free_delay_override=None)
        rt = _make_runtime({})
        delay, src = await _resolve_delay(user, rt)
        assert delay == DEFAULT_FREE_DELAY_SECONDS
        assert src == "default"

    # Story 6.3 — Decimal 호환 확장 회귀
    @pytest.mark.asyncio
    async def test_user_override_decimal_preserved(self):
        """ORM에서 Decimal로 들어오는 free_delay_override가 그대로 반환된다."""
        user = _make_user("free", free_delay_override=Decimal("1.5"))
        rt = _make_runtime({"runtime:free_delay": "3"})
        delay, src = await _resolve_delay(user, rt)
        assert delay == Decimal("1.5")
        assert isinstance(delay, Decimal)
        assert src == "user_override"

    @pytest.mark.asyncio
    async def test_default_returns_decimal_zero(self):
        user = _make_user("free", free_delay_override=None)
        rt = _make_runtime({})
        delay, _src = await _resolve_delay(user, rt)
        assert isinstance(delay, Decimal)

    @pytest.mark.asyncio
    async def test_runtime_value_promoted_to_decimal(self):
        user = _make_user("free", free_delay_override=None)
        rt = _make_runtime({"runtime:free_delay_enabled": "true", "runtime:free_delay": "5"})
        delay, _src = await _resolve_delay(user, rt)
        assert isinstance(delay, Decimal)
        assert delay == Decimal("5")
