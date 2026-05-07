"""Story 5.5 — analytics_service 매출 함수 단위 테스트 (AC-5)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.src.services import analytics_service
from api.src.services.budget_service import KST


def test_kst_month_bounds_from_str_basic():
    start, end = analytics_service._kst_month_bounds_from_str("2026-05")
    assert start == datetime(2026, 5, 1, tzinfo=KST)
    assert end == datetime(2026, 6, 1, tzinfo=KST)


def test_kst_month_bounds_from_str_jan():
    start, end = analytics_service._kst_month_bounds_from_str("2026-01")
    assert start == datetime(2026, 1, 1, tzinfo=KST)
    assert end == datetime(2026, 2, 1, tzinfo=KST)


def test_kst_month_bounds_from_str_dec_to_jan():
    """12월 → 다음 해 1월 연도 증가."""
    start, end = analytics_service._kst_month_bounds_from_str("2026-12")
    assert start == datetime(2026, 12, 1, tzinfo=KST)
    assert end == datetime(2027, 1, 1, tzinfo=KST)


def test_shift_month_forward():
    base = datetime(2026, 5, 1, tzinfo=KST)
    assert analytics_service._shift_month(base, 1) == datetime(2026, 6, 1, tzinfo=KST)
    assert analytics_service._shift_month(base, 7) == datetime(2026, 12, 1, tzinfo=KST)
    assert analytics_service._shift_month(base, 8) == datetime(2027, 1, 1, tzinfo=KST)


def test_shift_month_backward():
    base = datetime(2026, 5, 1, tzinfo=KST)
    assert analytics_service._shift_month(base, -1) == datetime(2026, 4, 1, tzinfo=KST)
    assert analytics_service._shift_month(base, -4) == datetime(2026, 1, 1, tzinfo=KST)
    assert analytics_service._shift_month(base, -5) == datetime(2025, 12, 1, tzinfo=KST)
    assert analytics_service._shift_month(base, -11) == datetime(2025, 6, 1, tzinfo=KST)


def test_year_month_re_valid():
    assert analytics_service.YEAR_MONTH_RE.match("2026-01")
    assert analytics_service.YEAR_MONTH_RE.match("2026-12")
    assert analytics_service.YEAR_MONTH_RE.match("1999-06")


def test_year_month_re_invalid():
    assert not analytics_service.YEAR_MONTH_RE.match("2026-13")
    assert not analytics_service.YEAR_MONTH_RE.match("2026-00")
    assert not analytics_service.YEAR_MONTH_RE.match("26-05")
    assert not analytics_service.YEAR_MONTH_RE.match("2026-5")
    assert not analytics_service.YEAR_MONTH_RE.match("abc-de")


def test_allowed_series_months():
    assert analytics_service.ALLOWED_SERIES_MONTHS == (3, 6, 12, 24)


def test_export_detail_limit_revenue():
    assert analytics_service.EXPORT_DETAIL_LIMIT_REVENUE == 10_000


def test_decimal_quantize_token_cost_krw():
    # token_cost_usd × usd_to_krw 정수 round 동작 검증
    cost_usd = Decimal("12.345600")
    rate = 1400
    result = int((cost_usd * Decimal(rate)).quantize(Decimal("1")))
    # 12.3456 * 1400 = 17283.84 → quantize 1 → 17284 (banker's rounding 가능)
    assert result in (17_283, 17_284)


def test_variance_negative_arithmetic():
    revenue = 10_000
    cost_krw = 15_000
    assert revenue - cost_krw == -5_000


# ---------------------------------------------------------------------------
# 매출 집계 기준 — payment_events.charge_success (refunded 결제 포함, payment_id dedupe)
# ---------------------------------------------------------------------------


def _stmt_to_sql(stmt) -> str:
    """SQLAlchemy Core/ORM 쿼리를 PostgreSQL 방언으로 컴파일해 SQL 문자열을 얻는다."""
    from sqlalchemy.dialects import postgresql

    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def _make_scalar_result(value):
    r = MagicMock()
    r.scalar_one = MagicMock(return_value=value)
    return r


def _make_rows_result(rows):
    r = MagicMock()
    r.all = MagicMock(return_value=rows)
    return r


@pytest.mark.asyncio
async def test_revenue_month_uses_charge_success_event_and_dedupes_by_payment_id():
    """summary 매출 쿼리는 status='success' 가 아닌 payment_events.charge_success 기반.

    이렇게 해야 환불되어 status='refunded' 가 된 결제도 그 달 매출에 포함되고,
    중복 charge_success 이벤트가 있어도 payment_id 단위로 dedupe 된다.
    """
    captured = []

    async def fake_execute(stmt):
        captured.append(stmt)
        # 호출 순서: revenue / cost / error / anomaly
        idx = len(captured)
        if idx == 1:
            return _make_scalar_result(9900)  # revenue_krw
        if idx == 2:
            return _make_scalar_result(Decimal("0"))  # token_cost_usd
        if idx == 3:
            return _make_scalar_result(0)  # error_count
        return _make_scalar_result(0)  # anomaly_count

    session = MagicMock()
    session.execute = fake_execute
    redis_runtime = MagicMock()

    with patch(
        "api.src.services.analytics_service.runtime_config_service.get_usd_to_krw",
        new=AsyncMock(return_value=1400),
    ):
        result = await analytics_service.get_revenue_variance_month(
            session, redis_runtime=redis_runtime, year_month="2026-05"
        )

    assert result["revenue_krw"] == 9900

    rev_sql = _stmt_to_sql(captured[0]).lower()
    assert "payment_events" in rev_sql
    assert "charge_success" in rev_sql
    # status='success' 단일 필터로 과거 방식과 다른 기준임이 보장되어야 함
    assert "payments.status" not in rev_sql or "in (" in rev_sql  # IN subquery 형태
    # payment_id 단위 중복 제거 (DISTINCT)
    assert "distinct" in rev_sql


@pytest.mark.asyncio
async def test_revenue_month_includes_refunded_payments():
    """refunded 결제도 매출에 포함됨을 확인 — Payment.status 와 무관하게 charge_success 기준."""

    async def fake_execute(stmt):
        # 시뮬레이션: charge_success 이벤트가 있는 payment_ids 하나만 환불(상태 refunded)된 케이스에서도
        # SQL 결과 SUM 은 9900 으로 반환된다고 가정. 즉 service 가 status 필터를 두지 않음을 검증.
        from sqlalchemy.dialects import postgresql

        sql = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})).lower()
        # revenue_krw 쿼리에 status 동등 필터가 없어야 환불 결제가 제외되지 않는다
        if "amount_krw" in sql and "sum" in sql:
            assert "status = 'success'" not in sql, "revenue 집계는 status='success' 동등 필터를 두면 안 됨"
            return _make_scalar_result(9900)
        if "qa_logs" in sql or "cost_usd" in sql:
            return _make_scalar_result(Decimal("0"))
        return _make_scalar_result(0)

    session = MagicMock()
    session.execute = fake_execute
    redis_runtime = MagicMock()

    with patch(
        "api.src.services.analytics_service.runtime_config_service.get_usd_to_krw",
        new=AsyncMock(return_value=1400),
    ):
        result = await analytics_service.get_revenue_variance_month(
            session, redis_runtime=redis_runtime, year_month="2026-05"
        )
    assert result["revenue_krw"] == 9900


@pytest.mark.asyncio
async def test_revenue_series_uses_charge_success_and_dedupes():
    """series 매출 쿼리도 동일 기준이어야 함 — charge_success 기반 + payment_id dedupe."""
    captured = []

    async def fake_execute(stmt):
        captured.append(stmt)
        # series는 rev_stmt → cost_stmt 두 번 호출됨
        return _make_rows_result([])

    session = MagicMock()
    session.execute = fake_execute
    redis_runtime = MagicMock()

    with patch(
        "api.src.services.analytics_service.runtime_config_service.get_usd_to_krw",
        new=AsyncMock(return_value=1400),
    ):
        result = await analytics_service.get_revenue_variance_series(
            session, redis_runtime=redis_runtime, months=3, to_year_month="2026-05"
        )

    assert result["months"] == 3
    rev_sql = _stmt_to_sql(captured[0]).lower()
    assert "payment_events" in rev_sql
    assert "charge_success" in rev_sql
    # 동일 payment_id 의 charge_success 이벤트가 중복돼도 한 번만 합산되도록 group by payment_id
    assert "group by" in rev_sql and "payment_id" in rev_sql


@pytest.mark.asyncio
async def test_revenue_export_rows_uses_charge_success():
    """Detail 시트도 동일 기준 — 환불된 결제도 export 에 포함되어 매출 집계와 일치."""

    async def fake_execute(stmt):
        return _make_rows_result([])

    session = MagicMock()
    session.execute = fake_execute

    rows, truncated = await analytics_service.get_revenue_variance_export_rows(
        session, year_month="2026-05", limit=10
    )
    assert rows == []
    assert truncated is False

    # SQL 검사 — 마지막 호출된 쿼리에 charge_success 가 포함되어야 함
    captured_stmt = None

    async def capture_execute(stmt):
        nonlocal captured_stmt
        captured_stmt = stmt
        return _make_rows_result([])

    session2 = MagicMock()
    session2.execute = capture_execute
    await analytics_service.get_revenue_variance_export_rows(
        session2, year_month="2026-05", limit=10
    )
    assert captured_stmt is not None
    sql = _stmt_to_sql(captured_stmt).lower()
    assert "charge_success" in sql
    assert "payment_events" in sql
