"""Unit 테스트 — 접속 통계 기기별 분해 (게시판 #144).

get_access_buckets 가 login_events.ua 기반 pc/mobile/unknown 분해를 정확히
버킷에 담는지, 그리고 주(week) 버킷 경계가 일요일 시작으로 묶이는지 검증한다.

세션은 다른 analytics 테스트와 동일하게 MagicMock + AsyncMock 으로 대체하고,
SQL 이 돌려주는 행 모양 ``(day, user_id, device, n)`` 만 흉내낸다.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.src.services.analytics_service import (
    _access_device_expr,
    get_access_buckets,
)
from api.src.utils.device import _MOBILE_TOKENS, classify_device, mobile_ua_regex


def _session_with_rows(rows: list[tuple]) -> MagicMock:
    """execute().all() 이 rows 를 돌려주는 가짜 세션."""
    session = MagicMock()
    result = MagicMock()
    result.all = MagicMock(return_value=rows)
    session.execute = AsyncMock(return_value=result)
    return session


# ---------------------------------------------------------------------------
# 판별 기준 SSOT — device.py 의 토큰 목록에서 정규식이 만들어지는지
# ---------------------------------------------------------------------------


def test_mobile_ua_regex_covers_every_token():
    """정규식은 _MOBILE_TOKENS 전부를 담아야 한다 (파이썬/SQL 기준 일치)."""
    pattern = mobile_ua_regex()
    for token in _MOBILE_TOKENS:
        assert token.replace(" ", "") in pattern.replace("\\", "").replace(" ", "")
    assert pattern.count("|") == len(_MOBILE_TOKENS) - 1


def test_access_device_expr_compiles_to_case():
    """CASE 식이 unknown/mobile/pc 3분기로 만들어진다."""
    sql = str(_access_device_expr().compile(compile_kwargs={"literal_binds": True}))
    assert "CASE" in sql
    assert "unknown" in sql and "mobile" in sql and "pc" in sql


def test_classify_device_matches_expected_labels():
    """SQL 분기와 같은 결론을 파이썬 유틸도 내는지 (기준 이중화 방지 회귀)."""
    assert classify_device("Mozilla/5.0 (Windows NT 10.0; Win64; x64)") == "pc"
    iphone_ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Mobile"
    assert classify_device(iphone_ua) == "mobile"
    assert classify_device(None) == "unknown"


# ---------------------------------------------------------------------------
# (1) PC UA 만 있을 때
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pc_only_bucket():
    rows = [
        (date(2026, 9, 1), 1, "pc", 3),
        (date(2026, 9, 1), 2, "pc", 1),
    ]
    session = _session_with_rows(rows)

    summary = await get_access_buckets(
        session, "day", date(2026, 9, 1), date(2026, 9, 1)
    )

    assert len(summary.buckets) == 1
    b = summary.buckets[0]
    assert (b.visitors, b.visits) == (2, 4)
    assert (b.pc_visitors, b.pc_visits) == (2, 4)
    assert (b.mobile_visitors, b.mobile_visits) == (0, 0)
    assert (b.unknown_visitors, b.unknown_visits) == (0, 0)
    assert summary.total_pc_visitors == 2
    assert summary.total_pc_visits == 4
    assert summary.total_mobile_visits == 0


# ---------------------------------------------------------------------------
# (2) 모바일 UA 만 있을 때
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mobile_only_bucket():
    rows = [(date(2026, 9, 2), 7, "mobile", 5)]
    session = _session_with_rows(rows)

    summary = await get_access_buckets(
        session, "day", date(2026, 9, 2), date(2026, 9, 2)
    )

    b = summary.buckets[0]
    assert (b.visitors, b.visits) == (1, 5)
    assert (b.mobile_visitors, b.mobile_visits) == (1, 5)
    assert (b.pc_visitors, b.pc_visits) == (0, 0)
    assert summary.total_mobile_visitors == 1
    assert summary.total_visitors == 1


# ---------------------------------------------------------------------------
# (3) 한 회원이 PC·모바일 둘 다 → 전체 고유 1명, 기기별은 각각 1명
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_same_user_on_both_devices_counted_twice_per_device():
    rows = [
        (date(2026, 9, 3), 42, "pc", 2),
        (date(2026, 9, 3), 42, "mobile", 3),
    ]
    session = _session_with_rows(rows)

    summary = await get_access_buckets(
        session, "day", date(2026, 9, 3), date(2026, 9, 3)
    )

    b = summary.buckets[0]
    # 전체 고유 회원은 1명이지만 기기별로는 각각 1명씩 잡히는 것이 정상.
    assert b.visitors == 1
    assert b.visits == 5
    assert b.pc_visitors == 1 and b.pc_visits == 2
    assert b.mobile_visitors == 1 and b.mobile_visits == 3
    assert b.pc_visitors + b.mobile_visitors > b.visitors
    assert summary.total_visitors == 1
    assert summary.total_pc_visitors == 1
    assert summary.total_mobile_visitors == 1


# ---------------------------------------------------------------------------
# (4) ua 가 비어 판별 불가 → unknown
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_device_bucket():
    rows = [
        (date(2026, 9, 4), 1, "unknown", 2),
        (date(2026, 9, 4), 2, "pc", 1),
    ]
    session = _session_with_rows(rows)

    summary = await get_access_buckets(
        session, "day", date(2026, 9, 4), date(2026, 9, 4)
    )

    b = summary.buckets[0]
    assert (b.unknown_visitors, b.unknown_visits) == (1, 2)
    assert (b.pc_visitors, b.pc_visits) == (1, 1)
    assert b.visitors == 2 and b.visits == 3
    assert summary.total_unknown_visitors == 1
    assert summary.total_unknown_visits == 2


@pytest.mark.asyncio
async def test_unrecognized_device_label_falls_back_to_unknown():
    """SQL 이 예상 밖 값을 돌려줘도 unknown 으로 흡수한다 (방어)."""
    rows = [(date(2026, 9, 4), 1, None, 2)]
    session = _session_with_rows(rows)

    summary = await get_access_buckets(
        session, "day", date(2026, 9, 4), date(2026, 9, 4)
    )

    assert summary.buckets[0].unknown_visits == 2
    assert summary.buckets[0].visits == 2


# ---------------------------------------------------------------------------
# (5) week 단위 버킷 경계 — 주 시작은 일요일
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_week_bucket_boundary_starts_on_sunday():
    """2026-09-05(토)와 2026-09-06(일)은 서로 다른 주 버킷에 들어간다."""
    rows = [
        (date(2026, 9, 5), 1, "pc", 1),      # 토요일 → 08-30(일) 시작 주
        (date(2026, 9, 6), 1, "mobile", 2),  # 일요일 → 09-06(일) 시작 주
        (date(2026, 9, 8), 2, "mobile", 1),  # 화요일 → 09-06 주
    ]
    session = _session_with_rows(rows)

    summary = await get_access_buckets(
        session, "week", date(2026, 9, 1), date(2026, 9, 9)
    )

    starts = [b.bucket_start for b in summary.buckets]
    assert starts == [date(2026, 8, 30), date(2026, 9, 6)]

    first, second = summary.buckets
    assert (first.visitors, first.visits) == (1, 1)
    assert (first.pc_visitors, first.pc_visits) == (1, 1)
    assert first.mobile_visits == 0

    assert (second.visitors, second.visits) == (2, 3)
    assert (second.mobile_visitors, second.mobile_visits) == (2, 3)
    assert second.pc_visits == 0

    # 구간 전체: 회원 1·2 두 명, 모바일 고유 2명 / PC 고유 1명
    assert summary.total_visitors == 2
    assert summary.total_visits == 4
    assert summary.total_pc_visitors == 1
    assert summary.total_mobile_visitors == 2


@pytest.mark.asyncio
async def test_empty_buckets_filled_with_zero():
    """접속 기록이 없는 날도 0으로 채워 버킷 개수는 유지된다."""
    session = _session_with_rows([])

    summary = await get_access_buckets(
        session, "day", date(2026, 9, 1), date(2026, 9, 3)
    )

    assert len(summary.buckets) == 3
    for b in summary.buckets:
        assert b.visitors == 0 and b.visits == 0
        assert b.pc_visits == 0 and b.mobile_visits == 0 and b.unknown_visits == 0
    assert summary.total_visitors == 0
    assert summary.total_mobile_visitors == 0
