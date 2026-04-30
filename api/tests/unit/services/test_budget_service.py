"""budget_service 단위 테스트 — Story 5.2."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.src.services.budget_service import (
    KST,
    classify,
    kst_month_bounds,
    get_current_month_snapshot,
)


# ── kst_month_bounds ─────────────────────────────────────────────────────────

def test_kst_month_bounds_january():
    now = datetime(2026, 1, 15, tzinfo=KST)
    start, end, ym = kst_month_bounds(now)
    assert ym == "2026-01"
    assert start == datetime(2026, 1, 1, tzinfo=KST)
    assert end == datetime(2026, 2, 1, tzinfo=KST)


def test_kst_month_bounds_december_wrap():
    now = datetime(2026, 12, 31, tzinfo=KST)
    start, end, ym = kst_month_bounds(now)
    assert ym == "2026-12"
    assert end == datetime(2027, 1, 1, tzinfo=KST)


def test_kst_month_bounds_april():
    now = datetime(2026, 4, 28, 10, 0, tzinfo=KST)
    start, end, ym = kst_month_bounds(now)
    assert ym == "2026-04"
    assert start.day == 1
    assert end.month == 5


# ── classify ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("percent,expected", [
    (0.0, "normal"),
    (79.99, "normal"),
    (80.0, "warning"),
    (94.99, "warning"),
    (95.0, "critical"),
    (100.0, "critical"),
])
def test_classify(percent: float, expected: str):
    assert classify(percent) == expected


# ── get_current_month_snapshot ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_snapshot_null_cost_treated_as_zero():
    from api.src.models.budget_threshold import BudgetThreshold

    threshold = MagicMock(spec=BudgetThreshold)
    threshold.monthly_limit_usd = Decimal("100.00")
    threshold.year_month = "2026-04"

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            # SUM(cost_usd) → 0 (NULL 없음)
            result.scalar_one.return_value = Decimal("0")
        else:
            result.scalar_one_or_none.return_value = threshold
        return result

    session = MagicMock()
    session.execute = AsyncMock(side_effect=mock_execute)
    session.add = MagicMock()
    session.flush = AsyncMock()

    snap = await get_current_month_snapshot(session)
    assert snap.spent_usd == Decimal("0")
    assert snap.percent == 0.0
    assert snap.status == "normal"


@pytest.mark.asyncio
async def test_snapshot_division_by_zero_when_limit_zero():
    from api.src.models.budget_threshold import BudgetThreshold

    threshold = MagicMock(spec=BudgetThreshold)
    threshold.monthly_limit_usd = Decimal("0")
    threshold.year_month = "2026-04"

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            result.scalar_one.return_value = Decimal("50.00")
        else:
            result.scalar_one_or_none.return_value = threshold
        return result

    session = MagicMock()
    session.execute = AsyncMock(side_effect=mock_execute)

    snap = await get_current_month_snapshot(session)
    assert snap.percent == 0.0


@pytest.mark.asyncio
async def test_snapshot_creates_threshold_row_when_missing():
    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            result.scalar_one.return_value = Decimal("10.00")
        else:
            result.scalar_one_or_none.return_value = None
        return result

    session = MagicMock()
    session.execute = AsyncMock(side_effect=mock_execute)
    session.add = MagicMock()
    session.flush = AsyncMock()

    snap = await get_current_month_snapshot(session)
    session.add.assert_called_once()
    session.flush.assert_called_once()
    assert snap.monthly_limit_usd == Decimal("100.00")
