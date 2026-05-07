"""Story 5.5 — runtime_config_service.get_usd_to_krw 단위 테스트 (AC-4)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from api.src.services import runtime_config_service


def _make_redis(value):
    r = MagicMock()
    r.get = AsyncMock(return_value=value)
    return r


@pytest.mark.asyncio
async def test_get_usd_to_krw_default_when_unset():
    r = _make_redis(None)
    result = await runtime_config_service.get_usd_to_krw(r)
    assert result == runtime_config_service.DEFAULT_USD_TO_KRW
    assert result == 1400


@pytest.mark.asyncio
async def test_get_usd_to_krw_valid():
    r = _make_redis("1500")
    result = await runtime_config_service.get_usd_to_krw(r)
    assert result == 1500


@pytest.mark.asyncio
async def test_get_usd_to_krw_min_boundary():
    r = _make_redis("1000")
    assert await runtime_config_service.get_usd_to_krw(r) == 1000


@pytest.mark.asyncio
async def test_get_usd_to_krw_max_boundary():
    r = _make_redis("3000")
    assert await runtime_config_service.get_usd_to_krw(r) == 3000


@pytest.mark.asyncio
async def test_get_usd_to_krw_invalid_string_fallback():
    r = _make_redis("not-a-number")
    assert await runtime_config_service.get_usd_to_krw(r) == 1400


@pytest.mark.asyncio
async def test_get_usd_to_krw_below_min_fallback():
    r = _make_redis("999")
    assert await runtime_config_service.get_usd_to_krw(r) == 1400


@pytest.mark.asyncio
async def test_get_usd_to_krw_above_max_fallback():
    r = _make_redis("3001")
    assert await runtime_config_service.get_usd_to_krw(r) == 1400


@pytest.mark.asyncio
async def test_get_usd_to_krw_negative_fallback():
    r = _make_redis("-100")
    assert await runtime_config_service.get_usd_to_krw(r) == 1400
