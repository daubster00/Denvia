"""Unit 테스트 — Story 6.4 segment 헬퍼·집계 로직."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from api.src.services.analytics_service import (
    _bucket_years,
    _mask_email,
    get_segment_stats,
)


def test_bucket_years_boundaries():
    assert _bucket_years(0) == "0-2"
    assert _bucket_years(1) == "0-2"
    assert _bucket_years(2) == "0-2"
    assert _bucket_years(3) == "3-5"
    assert _bucket_years(5) == "3-5"
    assert _bucket_years(6) == "6-10"
    assert _bucket_years(10) == "6-10"
    assert _bucket_years(11) == "11-20"
    assert _bucket_years(20) == "11-20"
    assert _bucket_years(21) == "20+"
    assert _bucket_years(30) == "20+"
    assert _bucket_years(99) == "20+"


def test_mask_email_normal():
    assert _mask_email("kim@example.com") == "k**@example.com"


def test_mask_email_short_local_unchanged():
    assert _mask_email("a@b.co") == "a@b.co"


def test_mask_email_no_at_sign_unchanged():
    assert _mask_email("invalid") == "invalid"


def test_mask_email_long_local():
    assert _mask_email("longuser@domain.org") == "l**@domain.org"


@pytest.mark.asyncio
async def test_get_segment_stats_empty_db():
    """빈 DB → total=0, by_segment 3행 모두 0, by_experience 10행 모두 0."""
    session = MagicMock()
    empty_result = MagicMock()
    empty_result.all = MagicMock(return_value=[])
    session.execute = AsyncMock(return_value=empty_result)

    result = await get_segment_stats(session)

    assert result["total"] == 0
    assert result["applied_filters"] == {
        "include_withdrawn": False,
        "include_blocked": False,
    }
    assert len(result["by_segment"]) == 3
    seg_keys = [r.segment for r in result["by_segment"]]
    assert seg_keys == ["doctor", "hygienist", "student_other"]
    for r in result["by_segment"]:
        assert r.count == 0
        assert r.active_count == 0
        assert r.pro_count == 0

    # by_experience: 2 segments * 5 buckets = 10 rows
    assert len(result["by_experience"]) == 10
    for r in result["by_experience"]:
        assert r.count == 0


@pytest.mark.asyncio
async def test_get_segment_stats_aggregates_segments():
    """SQL row 결과에서 doctor/hygienist/student_other를 정확한 위치에 매핑."""
    session = MagicMock()
    seg_result = MagicMock()
    # (segment, count, active_count, pro_count)
    seg_result.all = MagicMock(
        return_value=[
            ("doctor", 10, 9, 3),
            ("hygienist", 5, 5, 0),
            ("student_other", 2, 2, 0),
            (None, 1, 1, 0),  # NULL segment 사용자
        ]
    )
    exp_result = MagicMock()
    exp_result.all = MagicMock(
        return_value=[
            ("doctor", 4, 5),
            ("doctor", 12, 1),
            ("hygienist", 3, 5),
        ]
    )
    session.execute = AsyncMock(side_effect=[seg_result, exp_result])

    result = await get_segment_stats(session)

    # NULL segment는 by_segment에서 제외, total에는 포함
    assert result["total"] == 18  # 10+5+2+1
    by_seg = {r.segment: r for r in result["by_segment"]}
    assert by_seg["doctor"].count == 10
    assert by_seg["doctor"].active_count == 9
    assert by_seg["doctor"].pro_count == 3
    assert by_seg["hygienist"].count == 5
    assert by_seg["student_other"].count == 2

    # by_experience: doctor 4년 → 3-5, doctor 12년 → 11-20, hygienist 3년 → 3-5
    by_exp = {(r.segment, r.years_bucket): r.count for r in result["by_experience"]}
    assert by_exp[("doctor", "3-5")] == 5
    assert by_exp[("doctor", "11-20")] == 1
    assert by_exp[("hygienist", "3-5")] == 5
    assert by_exp[("doctor", "0-2")] == 0
    assert by_exp[("hygienist", "0-2")] == 0


@pytest.mark.asyncio
async def test_get_segment_stats_include_withdrawn_echoed():
    session = MagicMock()
    empty = MagicMock()
    empty.all = MagicMock(return_value=[])
    session.execute = AsyncMock(return_value=empty)

    result = await get_segment_stats(
        session, include_withdrawn=True, include_blocked=True
    )

    assert result["applied_filters"] == {
        "include_withdrawn": True,
        "include_blocked": True,
    }
