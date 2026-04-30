"""killswitch_service 단위 테스트 — Story 5.2."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from api.src.services.killswitch_service import (
    get_active_modes,
    is_auto_free_only_active,
    is_any_total_block_active,
)


def _mock_session(modes: list[str]):
    result = MagicMock()
    result.scalars.return_value.all.return_value = modes
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    return session


@pytest.mark.asyncio
async def test_get_active_modes_empty():
    session = _mock_session([])
    modes = await get_active_modes(session)
    assert modes == set()


@pytest.mark.asyncio
async def test_get_active_modes_auto_free_only():
    session = _mock_session(["auto_free_only"])
    modes = await get_active_modes(session)
    assert "auto_free_only" in modes


@pytest.mark.asyncio
async def test_get_active_modes_manual_total():
    session = _mock_session(["manual_total"])
    modes = await get_active_modes(session)
    assert "manual_total" in modes


@pytest.mark.asyncio
async def test_get_active_modes_both():
    session = _mock_session(["auto_free_only", "manual_total"])
    modes = await get_active_modes(session)
    assert modes == {"auto_free_only", "manual_total"}


@pytest.mark.asyncio
async def test_is_auto_free_only_active_true():
    session = _mock_session(["auto_free_only"])
    assert await is_auto_free_only_active(session) is True


@pytest.mark.asyncio
async def test_is_auto_free_only_active_false_when_manual_only():
    session = _mock_session(["manual_total"])
    assert await is_auto_free_only_active(session) is False


@pytest.mark.asyncio
async def test_is_any_total_block_active_true():
    session = _mock_session(["manual_total"])
    assert await is_any_total_block_active(session) is True


@pytest.mark.asyncio
async def test_is_any_total_block_active_false_when_auto_only():
    session = _mock_session(["auto_free_only"])
    assert await is_any_total_block_active(session) is False


@pytest.mark.asyncio
async def test_is_any_total_block_active_false_when_empty():
    session = _mock_session([])
    assert await is_any_total_block_active(session) is False
