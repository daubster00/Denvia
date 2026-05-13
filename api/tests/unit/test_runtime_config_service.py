"""runtime_config_service 유닛 테스트 — get_night_block_settings (Story 4.2)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from api.src.services.runtime_config_service import (
    NightBlockSettings,
    get_night_block_settings,
)


def _make_redis(enabled_raw: str | None, active_raw: str | None) -> AsyncMock:
    """Redis mock — get() 호출 시 enabled_raw, active_raw 순서로 반환."""
    redis = AsyncMock()
    redis.get.side_effect = [enabled_raw, active_raw]
    return redis


class TestGetNightBlockSettings:
    @pytest.mark.asyncio
    async def test_toggle_on_active_true_returns_enabled_active(self):
        """토글 ON + active=true → NightBlockSettings(enabled=True, active=True)."""
        redis = _make_redis("true", "true")
        result = await get_night_block_settings(redis)
        assert result == NightBlockSettings(enabled=True, active=True)

    @pytest.mark.asyncio
    async def test_toggle_off_returns_disabled(self):
        """토글 OFF → NightBlockSettings(enabled=False, active=...)."""
        redis = _make_redis("false", "true")
        result = await get_night_block_settings(redis)
        assert result.enabled is False

    @pytest.mark.asyncio
    async def test_active_key_null_returns_active_none(self):
        """active 키 NULL → NightBlockSettings(enabled=True, active=None) — 호출자 시각 폴백."""
        redis = _make_redis("true", None)
        result = await get_night_block_settings(redis)
        assert result == NightBlockSettings(enabled=True, active=None)

    @pytest.mark.asyncio
    async def test_redis_exception_returns_fail_closed(self):
        """Redis 호출 예외 → fail-closed NightBlockSettings(enabled=True, active=None)."""
        redis = AsyncMock()
        redis.get.side_effect = Exception("redis 연결 실패")
        result = await get_night_block_settings(redis)
        assert result == NightBlockSettings(enabled=True, active=None)

    @pytest.mark.asyncio
    async def test_active_raw_value_variations(self):
        """active 다양한 truthy 값("1", "True", "on", "yes") → active=True."""
        for truthy in ("1", "True", "on", "yes"):
            redis = _make_redis("true", truthy)
            result = await get_night_block_settings(redis)
            assert result.active is True, f"'{truthy}'는 True로 해석되어야 함"

    @pytest.mark.asyncio
    async def test_active_raw_falsy_values(self):
        """active falsy 값("0", "false", "off") → active=False."""
        for falsy in ("0", "false", "off"):
            redis = _make_redis("true", falsy)
            result = await get_night_block_settings(redis)
            assert result.active is False, f"'{falsy}'는 False로 해석되어야 함"
