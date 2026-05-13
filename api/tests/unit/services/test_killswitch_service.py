"""killswitch_service 단위 테스트 — Story 5.2 + Story 9.2."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.src.services.killswitch_service import (
    KillSwitchAlreadyActive,
    KillSwitchNotActive,
    _mask_email,
    activate_manual,
    deactivate_manual,
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


# ── Story 9.2 신규 헬퍼 ──────────────────────────────────────────────────────


def test_mask_email_normal():
    assert _mask_email("admin@denvia.local") == "ad****@denvia.local"


def test_mask_email_short_local():
    assert _mask_email("ab@x.com") == "ab****@x.com"


def test_mask_email_none():
    assert _mask_email(None) is None


def test_mask_email_no_at():
    assert _mask_email("invalid") == "invalid"


def _existing_session(existing_row):
    """activate_manual용 — first SELECT가 활성 row 또는 None을 반환."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = existing_row
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_activate_manual_raises_when_already_active():
    existing = MagicMock()
    existing.id = 7
    session = _existing_session(existing)
    with pytest.raises(KillSwitchAlreadyActive):
        await activate_manual(session, admin_id=99, reason="test reason 12345")


@pytest.mark.asyncio
async def test_activate_manual_inserts_when_inactive():
    session = _existing_session(None)
    row = await activate_manual(session, admin_id=99, reason="test reason 12345")
    session.add.assert_called_once()
    session.flush.assert_awaited()
    assert row.mode == "manual_total"
    assert row.activated_by == 99
    assert row.reason == "test reason 12345"
    assert row.year_month is None


@pytest.mark.asyncio
async def test_deactivate_manual_raises_when_not_active():
    session = _existing_session(None)
    with pytest.raises(KillSwitchNotActive):
        await deactivate_manual(session, admin_id=99)


@pytest.mark.asyncio
async def test_deactivate_manual_updates_and_returns_duration():
    activated = datetime.now(timezone.utc) - timedelta(minutes=30)
    row = MagicMock()
    row.id = 42
    row.activated_at = activated
    row.deactivated_at = None
    row.deactivated_by = None
    session = _existing_session(row)
    result = await deactivate_manual(session, admin_id=99)
    assert result.killswitch_state_id == 42
    assert result.duration_seconds >= 1700  # ~30분
    assert row.deactivated_by == 99
    assert row.deactivated_at is not None
