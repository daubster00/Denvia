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


def _make_row_result(**fields):
    """get_revenue_variance_month rev_stmt — .one() 이 gross/refund 컬럼 row 반환."""
    row = MagicMock(**fields)
    r = MagicMock()
    r.one = MagicMock(return_value=row)
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
        # 호출 순서: revenue(.one) / cost / error / anomaly
        idx = len(captured)
        if idx == 1:
            return _make_row_result(gross=9900, refund=0)  # gross/refund row
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
    assert result["gross_revenue_krw"] == 9900
    assert result["refund_krw"] == 0
    assert result["net_revenue_krw"] == 9900

    rev_sql = _stmt_to_sql(captured[0]).lower()
    assert "payment_events" in rev_sql
    assert "charge_success" in rev_sql
    # status='success' 단일 필터로 과거 방식과 다른 기준임이 보장되어야 함
    assert "payments.status" not in rev_sql or "in (" in rev_sql  # IN subquery 형태
    # payment_id 단위 중복 제거 (DISTINCT)
    assert "distinct" in rev_sql


@pytest.mark.asyncio
async def test_revenue_month_includes_refunded_payments_as_gross_and_subtracts_for_net():
    """charge_success 결제는 gross 에 포함되고, 그중 refunded 분은 refund 로 분리·차감되어 net 이 계산된다."""

    async def fake_execute(stmt):
        from sqlalchemy.dialects import postgresql

        sql = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})).lower()
        # revenue 쿼리 — gross 는 status 동등 필터 없이 charge_success 기반,
        # refund 는 case-when status='refunded' 로 분리되어야 함
        if "amount_krw" in sql and "sum" in sql:
            assert "where payments.status = 'success'" not in sql, "gross 는 status='success' 동등 필터를 두면 안 됨"
            assert "'refunded'" in sql, "refund 분리를 위해 status='refunded' case-when 필요"
            # 9900 결제 중 9900 이 환불된 시나리오 — net = 0
            return _make_row_result(gross=9900, refund=9900)
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
    assert result["gross_revenue_krw"] == 9900
    assert result["refund_krw"] == 9900
    assert result["net_revenue_krw"] == 0
    assert result["variance_krw"] == 0  # net 0 - token 0


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


# ---------------------------------------------------------------------------
# #145 — 지식 재구축(임베딩) 비용이 재무 집계에 합산되는지
#
# 배경: 관리자 화면 지출은 qa_logs(챗봇 대화)만 합산했고, 지식 재구축 때 나간
# 임베딩 비용은 어디에도 기록되지 않아 실제 OpenAI 청구액과 차이가 났다.
# 이제 rebuild_jobs.embedding_cost_usd 를 같이 더하고, 화면용으로 내역도 나눈다.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revenue_month_adds_rebuild_cost_to_token_cost():
    """token_cost_usd = 챗봇 대화 비용 + 지식 재구축 비용, 내역도 함께 내려온다."""
    captured = []

    async def fake_execute(stmt):
        captured.append(stmt)
        idx = len(captured)
        if idx == 1:
            return _make_row_result(gross=0, refund=0)
        if idx == 2:
            return _make_scalar_result(Decimal("48.34"))   # qa_logs
        if idx == 3:
            return _make_scalar_result(Decimal("50.00"))   # rebuild_jobs
        return _make_scalar_result(0)

    session = MagicMock()
    session.execute = fake_execute

    with patch(
        "api.src.services.analytics_service.runtime_config_service.get_usd_to_krw",
        new=AsyncMock(return_value=1400),
    ):
        result = await analytics_service.get_revenue_variance_month(
            session, redis_runtime=MagicMock(), year_month="2026-09"
        )

    assert result["token_cost_usd"] == "98.340000"
    assert result["qa_cost_usd"] == "48.340000"
    assert result["rebuild_cost_usd"] == "50.000000"
    # 내역의 합은 반올림 차이 없이 항상 총계와 같아야 한다.
    assert result["qa_cost_krw"] + result["rebuild_cost_krw"] == result["token_cost_krw"]
    assert result["rebuild_cost_krw"] == 70_000  # 50 × 1400
    assert result["variance_krw"] == 0 - result["token_cost_krw"]


@pytest.mark.asyncio
async def test_revenue_month_rebuild_query_targets_rebuild_jobs_without_user_filter():
    """재구축은 특정 회원의 질문이 아니라 관리자 작업 — 사용자 필터가 붙으면 안 된다."""
    captured = []

    async def fake_execute(stmt):
        captured.append(stmt)
        idx = len(captured)
        if idx == 1:
            return _make_row_result(gross=0, refund=0)
        if idx in (2, 3):
            return _make_scalar_result(Decimal("0"))
        return _make_scalar_result(0)

    session = MagicMock()
    session.execute = fake_execute

    with patch(
        "api.src.services.analytics_service.runtime_config_service.get_usd_to_krw",
        new=AsyncMock(return_value=1400),
    ):
        await analytics_service.get_revenue_variance_month(
            session, redis_runtime=MagicMock(), year_month="2026-09"
        )

    rebuild_sql = _stmt_to_sql(captured[2]).lower()
    assert "rebuild_jobs" in rebuild_sql
    assert "embedding_cost_usd" in rebuild_sql
    # NULL(측정 전 과거 재구축)은 SUM 에서 빠지고 COALESCE 로 0이 된다.
    assert "coalesce" in rebuild_sql
    assert "users" not in rebuild_sql


@pytest.mark.asyncio
async def test_revenue_month_without_rebuild_keeps_previous_total():
    """재구축 비용이 0이면 기존과 완전히 같은 총계가 나와야 한다(회귀 방지)."""
    captured = []

    async def fake_execute(stmt):
        captured.append(stmt)
        idx = len(captured)
        if idx == 1:
            return _make_row_result(gross=100_000, refund=0)
        if idx == 2:
            return _make_scalar_result(Decimal("12.345600"))
        if idx == 3:
            return _make_scalar_result(Decimal("0"))
        return _make_scalar_result(0)

    session = MagicMock()
    session.execute = fake_execute

    with patch(
        "api.src.services.analytics_service.runtime_config_service.get_usd_to_krw",
        new=AsyncMock(return_value=1400),
    ):
        result = await analytics_service.get_revenue_variance_month(
            session, redis_runtime=MagicMock(), year_month="2026-09"
        )

    assert result["token_cost_usd"] == "12.345600"
    assert result["rebuild_cost_krw"] == 0
    assert result["qa_cost_krw"] == result["token_cost_krw"]
    assert result["token_cost_krw"] in (17_283, 17_284)


@pytest.mark.asyncio
async def test_revenue_series_adds_rebuild_cost_per_month():
    """월별 추이에서도 재구축 비용이 합산되고 내역이 분리된다."""
    from datetime import datetime as _dt

    bucket = _dt(2026, 9, 1)

    captured = []

    async def fake_execute(stmt):
        captured.append(stmt)
        idx = len(captured)
        if idx == 1:      # rev
            return _make_rows_result([])
        if idx == 2:      # qa_logs cost
            return _make_rows_result([MagicMock(bucket=bucket, cost=Decimal("10.00"))])
        return _make_rows_result(  # rebuild_jobs cost
            [MagicMock(bucket=bucket, cost=Decimal("5.00"))]
        )

    session = MagicMock()
    session.execute = fake_execute

    with patch(
        "api.src.services.analytics_service.runtime_config_service.get_usd_to_krw",
        new=AsyncMock(return_value=1400),
    ):
        result = await analytics_service.get_revenue_variance_series(
            session, redis_runtime=MagicMock(), months=3, to_year_month="2026-09"
        )

    sept = [i for i in result["items"] if i["year_month"] == "2026-09"][0]
    assert sept["qa_cost_krw"] == 14_000        # 10 × 1400
    assert sept["rebuild_cost_krw"] == 7_000    # 5 × 1400
    assert sept["token_cost_krw"] == 21_000
    assert sept["qa_cost_krw"] + sept["rebuild_cost_krw"] == sept["token_cost_krw"]
    # 재구축이 없던 달은 0으로 채워지고 총계도 그대로.
    other = [i for i in result["items"] if i["year_month"] != "2026-09"]
    assert all(i["rebuild_cost_krw"] == 0 for i in other)
    assert all(i["token_cost_krw"] == i["qa_cost_krw"] for i in other)


@pytest.mark.asyncio
async def test_revenue_month_does_not_touch_per_user_breakdown():
    """사용자별 비용 분해에는 재구축 비용이 들어가면 안 된다.

    재구축은 특정 회원의 질문이 아니라 관리자 작업이라 사용자에게 배분할 수 없다.
    (사용자별 집계 함수의 SQL 에 rebuild_jobs 가 없어야 한다.)
    """
    import inspect

    from api.src.routers.admin import analytics as analytics_router

    # 사용자별 토큰 비용 (TOP 5 위젯·상세 표가 보는 엔드포인트)
    src = inspect.getsource(analytics_router.user_tokens)
    assert "RebuildJob" not in src
    assert "embedding_cost_usd" not in src

    # 사용자별 질문 목록·export 도 동일.
    for fn in (
        analytics_service.get_questions_items,
        analytics_service.get_questions_export_rows,
    ):
        fn_src = inspect.getsource(fn)
        assert "RebuildJob" not in fn_src
        assert "embedding_cost_usd" not in fn_src
