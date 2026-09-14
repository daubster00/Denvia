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
    kst_month_bounds_for_ym,
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


# ── kst_month_bounds_for_ym ──────────────────────────────────────────────────

def test_bounds_for_ym_basic():
    start, end, ym = kst_month_bounds_for_ym("2026-05")
    assert ym == "2026-05"
    assert start == datetime(2026, 5, 1, tzinfo=KST)
    assert end == datetime(2026, 6, 1, tzinfo=KST)


def test_bounds_for_ym_december_wraps_year():
    start, end, ym = kst_month_bounds_for_ym("2025-12")
    assert ym == "2025-12"
    assert end == datetime(2026, 1, 1, tzinfo=KST)


@pytest.mark.parametrize("bad", ["2026-13", "abc", "2026", "2026-00", "2026-1", ""])
def test_bounds_for_ym_rejects_invalid(bad: str):
    with pytest.raises(ValueError):
        kst_month_bounds_for_ym(bad)


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
        elif call_count == 2:
            # #145 — SUM(rebuild_jobs.embedding_cost_usd). 이 시나리오들은 재구축 없음 → 0
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
        elif call_count == 2:
            # #145 — SUM(rebuild_jobs.embedding_cost_usd). 이 시나리오들은 재구축 없음 → 0
            result.scalar_one.return_value = Decimal("0")
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
        elif call_count == 2:
            # #145 — SUM(rebuild_jobs.embedding_cost_usd). 이 시나리오들은 재구축 없음 → 0
            result.scalar_one.return_value = Decimal("0")
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


# ── get_current_month_snapshot(ym=...) — 특정 월 조회 ────────────────────────

@pytest.mark.asyncio
async def test_snapshot_with_ym_returns_that_month():
    """ym 지정 시 그 달의 합계·한도를 그대로 반환."""
    from api.src.models.budget_threshold import BudgetThreshold

    threshold = MagicMock(spec=BudgetThreshold)
    threshold.monthly_limit_usd = Decimal("50.00")
    threshold.year_month = "2026-05"

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            result.scalar_one.return_value = Decimal("12.50")
        elif call_count == 2:
            # #145 — SUM(rebuild_jobs.embedding_cost_usd). 이 시나리오들은 재구축 없음 → 0
            result.scalar_one.return_value = Decimal("0")
        else:
            result.scalar_one_or_none.return_value = threshold
        return result

    session = MagicMock()
    session.execute = AsyncMock(side_effect=mock_execute)
    session.add = MagicMock()
    session.flush = AsyncMock()

    snap = await get_current_month_snapshot(session, ym="2026-05")
    assert snap.year_month == "2026-05"
    assert snap.spent_usd == Decimal("12.50")
    assert snap.monthly_limit_usd == Decimal("50.00")
    # 과거 월 조회 시에는 threshold 행을 새로 만들지 않는다.
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_snapshot_with_ym_no_threshold_uses_fallback_without_insert():
    """ym 지정 + 한도 행 없음 → 기본 한도 사용, INSERT 안 함."""
    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            result.scalar_one.return_value = Decimal("3.00")
        elif call_count == 2:
            # #145 — SUM(rebuild_jobs.embedding_cost_usd). 이 시나리오들은 재구축 없음 → 0
            result.scalar_one.return_value = Decimal("0")
        else:
            result.scalar_one_or_none.return_value = None
        return result

    session = MagicMock()
    session.execute = AsyncMock(side_effect=mock_execute)
    session.add = MagicMock()
    session.flush = AsyncMock()

    snap = await get_current_month_snapshot(session, ym="2026-05")
    session.add.assert_not_called()
    session.flush.assert_not_called()
    assert snap.year_month == "2026-05"
    assert snap.spent_usd == Decimal("3.00")
    # settings.denvia_initial_monthly_budget_usd = 100.00
    assert snap.monthly_limit_usd == Decimal("100.00")


@pytest.mark.asyncio
async def test_snapshot_with_invalid_ym_raises():
    session = MagicMock()
    session.execute = AsyncMock()
    with pytest.raises(ValueError):
        await get_current_month_snapshot(session, ym="2026-13")


# ── #145 지식 재구축(임베딩) 비용 합산 ────────────────────────────────────────
# 배경: 관리자 화면 지출은 qa_logs(챗봇 대화)만 합산해, 지식 재구축 때 나간
# 임베딩 비용이 어디에도 안 잡혔다. 이제 예산 기준값(spent_usd)에 함께 넣는다.


def _snapshot_session(qa_sum: Decimal, rebuild_sum: Decimal, limit: Decimal):
    """execute 호출 순서: 1) qa_logs SUM  2) rebuild_jobs SUM  3) threshold 조회."""
    from api.src.models.budget_threshold import BudgetThreshold

    threshold = MagicMock(spec=BudgetThreshold)
    threshold.monthly_limit_usd = limit
    threshold.year_month = "2026-09"

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            result.scalar_one.return_value = qa_sum
        elif call_count == 2:
            result.scalar_one.return_value = rebuild_sum
        else:
            result.scalar_one_or_none.return_value = threshold
        return result

    session = MagicMock()
    session.execute = AsyncMock(side_effect=mock_execute)
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_snapshot_adds_rebuild_cost_to_spent():
    """spent_usd = 챗봇 대화 비용 + 지식 재구축 비용."""
    session = _snapshot_session(Decimal("48.34"), Decimal("50.00"), Decimal("200.00"))
    snap = await get_current_month_snapshot(session, ym="2026-09")
    assert snap.qa_spent_usd == Decimal("48.34")
    assert snap.rebuild_spent_usd == Decimal("50.00")
    assert snap.spent_usd == Decimal("98.34")
    # 내역의 합은 항상 총계와 같아야 한다.
    assert snap.qa_spent_usd + snap.rebuild_spent_usd == snap.spent_usd


@pytest.mark.asyncio
async def test_snapshot_percent_uses_combined_spend():
    """재구축 비용이 더해지면 소진율도 그만큼 올라간다(자동 차단 기준값)."""
    session = _snapshot_session(Decimal("40.00"), Decimal("40.00"), Decimal("100.00"))
    snap = await get_current_month_snapshot(session, ym="2026-09")
    assert snap.percent == 80.0
    assert snap.status == "warning"


@pytest.mark.asyncio
async def test_snapshot_rebuild_cost_can_trip_killswitch_threshold():
    """챗봇 비용만으로는 95% 미만이어도, 재구축 비용까지 더하면 100%를 넘길 수 있다.

    classify() 로직은 그대로고 입력값만 커진다 — 자동 차단 판정 경로가 기존과 동일함을 확인.
    """
    session = _snapshot_session(Decimal("70.00"), Decimal("35.00"), Decimal("100.00"))
    snap = await get_current_month_snapshot(session, ym="2026-09")
    assert snap.spent_usd == Decimal("105.00")
    assert snap.percent == 105.0
    assert snap.status == "critical"
    # budget_tasks._check_thresholds_async 는 percent >= 100 에서 auto kill-switch 를 켠다.
    assert snap.percent >= 100


@pytest.mark.asyncio
async def test_snapshot_rebuild_null_sum_is_zero():
    """과거 재구축은 비용이 NULL — COALESCE 로 0이 오며 총계가 변하지 않는다."""
    session = _snapshot_session(Decimal("12.50"), Decimal("0"), Decimal("100.00"))
    snap = await get_current_month_snapshot(session, ym="2026-09")
    assert snap.spent_usd == Decimal("12.50")
    assert snap.rebuild_spent_usd == Decimal("0")
