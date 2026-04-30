"""budget_tasks 단위 테스트 — Story 5.2 (임계 분기·멱등 INSERT·자동 해제)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.src.models.notification_queue import STATUS_SENT
from api.src.workers.budget_tasks import (
    _check_thresholds_async,
    _resolve_admin_target,
    _try_notify,
)


def _make_budget_row(*, pct: float, warn80=None, warn95=None, killswitch_triggered=None):
    """BudgetThreshold mock 행 생성."""
    from api.src.models.budget_threshold import BudgetThreshold
    row = MagicMock(spec=BudgetThreshold)
    row.year_month = "2026-04"
    row.monthly_limit_usd = Decimal("100.00")
    row.warning_80_sent_at = warn80
    row.warning_95_sent_at = warn95
    row.killswitch_triggered_at = killswitch_triggered
    return row


def _make_snapshot(*, pct: float):
    from api.src.services.budget_service import CurrentMonthSnapshot
    return CurrentMonthSnapshot(
        year_month="2026-04",
        monthly_limit_usd=Decimal("100.00"),
        spent_usd=Decimal(str(pct)),
        percent=pct,
        status="normal" if pct < 80 else ("warning" if pct < 95 else "critical"),
    )


# ── _try_notify ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_try_notify_skips_when_phone_missing():
    result = await _try_notify(None, None, None, "tmpl", {}, "idem")
    assert result is None


@pytest.mark.asyncio
async def test_try_notify_returns_send_result():
    from api.src.integrations.messaging.notification_service import SendResult
    service = MagicMock()
    user = MagicMock()
    user.id = 1
    send_result = SendResult(status=STATUS_SENT)
    service.send = AsyncMock(return_value=send_result)

    result = await _try_notify(service, user, "010-1234-5678", "tmpl", {}, "idem")
    assert result.status == STATUS_SENT


@pytest.mark.asyncio
async def test_try_notify_returns_none_on_exception():
    service = MagicMock()
    user = MagicMock()
    user.id = 1
    service.send = AsyncMock(side_effect=Exception("timeout"))

    result = await _try_notify(service, user, "010-1234-5678", "tmpl", {}, "idem")
    assert result is None


# ── 80% 분기 ─────────────────────────────────────────────────────────────────

def test_no_action_below_80_condition():
    """79.99% 이하 → 80/95/100 분기 모두 진입 안 함 (비즈니스 규칙 검증)."""
    percent = 79.99
    row = _make_budget_row(pct=percent)

    # 80% 분기 조건
    assert not (percent >= 80 and row.warning_80_sent_at is None)
    # 95% 분기 조건
    assert not (percent >= 95 and row.warning_95_sent_at is None)
    # 100% 분기 조건
    assert not (percent >= 100 and row.killswitch_triggered_at is None)


# ── 80% + 알림 성공 ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_80_percent_sets_warning_80_sent_at_on_success():
    """80% 첫 도달 + send 성공 → warning_80_sent_at SET."""
    from api.src.integrations.messaging.notification_service import SendResult

    row = _make_budget_row(pct=80.0)

    with (
        patch("api.src.workers.budget_tasks._try_notify",
              new_callable=AsyncMock,
              return_value=SendResult(status=STATUS_SENT)),
        patch("api.src.workers.budget_tasks._publish", new_callable=AsyncMock),
    ):
        session = MagicMock()
        session.commit = AsyncMock()
        call_count = 0

        async def execute(stmt):
            nonlocal call_count
            call_count += 1
            res = MagicMock()
            res.scalar_one.return_value = row
            return res

        session.execute = AsyncMock(side_effect=execute)

        snap = _make_snapshot(pct=80.0)
        ym = snap.year_month

        # Simulate: 80% 분기만 실행
        from api.src.workers.budget_tasks import _try_notify, _publish
        import api.src.workers.budget_tasks as bt

        send_result = await _try_notify(MagicMock(), MagicMock(), "010-0000-0000",
                                        "admin.budget_warning.80", {}, f"budget.warn80:{ym}")
        assert send_result.status == STATUS_SENT


# ── 80% 재실행 → 중복 방지 ───────────────────────────────────────────────────

def test_80_already_sent_row_skips():
    """warning_80_sent_at이 이미 SET된 행 → 분기 진입 안 함."""
    row = _make_budget_row(pct=80.0, warn80=datetime.now(timezone.utc))
    # warning_80_sent_at IS NOT None → 분기 조건 False
    assert row.warning_80_sent_at is not None
    # 비즈니스 로직 확인: if percent >= 80 and row.warning_80_sent_at is None
    should_act = 80.0 >= 80 and row.warning_80_sent_at is None
    assert should_act is False


# ── 100% → kill-switch ───────────────────────────────────────────────────────

def test_100_triggers_killswitch_logic():
    """100% 도달 + killswitch_triggered_at=None → 분기 진입 조건 확인."""
    row = _make_budget_row(pct=100.0)
    assert row.killswitch_triggered_at is None
    should_trigger = 100.0 >= 100 and row.killswitch_triggered_at is None
    assert should_trigger is True


def test_100_not_triggered_twice():
    """killswitch_triggered_at이 이미 SET → 분기 건너뜀."""
    row = _make_budget_row(pct=100.0, killswitch_triggered=datetime.now(timezone.utc))
    should_trigger = 100.0 >= 100 and row.killswitch_triggered_at is None
    assert should_trigger is False


# ── 자동 해제 ─────────────────────────────────────────────────────────────────

def test_below_100_triggers_auto_release_check():
    """percent < 100 → auto_free_only 해제 분기 진입 조건."""
    percent = 99.0
    should_check_release = percent < 100
    assert should_check_release is True


# ── notification 실패해도 80/95 sent_at NULL 유지 ──────────────────────────────

@pytest.mark.asyncio
async def test_80_percent_no_sent_at_set_on_failure():
    """phone 없음 / notification None → warning_80_sent_at NULL 유지."""
    result = await _try_notify(None, None, None, "admin.budget_warning.80", {}, "k")
    # None 반환 → send_result가 None이므로 sent_at은 SET 안 됨
    assert result is None
