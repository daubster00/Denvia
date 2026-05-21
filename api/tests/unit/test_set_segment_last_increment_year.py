"""set_segment 핸들러가 experience_last_increment_year 를 현재 KST 연도로 기록하는지 검증.

연차 매년 1월 1일 +1 가산 배치(career_tasks.annual_increment)의 가드값을 만들어 두는
경계 동작이라, 단위 테스트로 명시적으로 잠가둔다.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.src.routers import me as me_router
from api.src.schemas.auth import SegmentRequest


def _make_user() -> MagicMock:
    user = MagicMock()
    user.segment = None
    user.years_of_experience = None
    user.experience_last_increment_year = None
    return user


def _kst_dt(year: int) -> MagicMock:
    dt = MagicMock(spec=datetime)
    dt.year = year
    return dt


@pytest.mark.asyncio
async def test_doctor_signup_records_current_kst_year():
    """doctor + years=3 가입 시 experience_last_increment_year = 현재 KST 연도."""
    user = _make_user()
    db = MagicMock()
    db.commit = AsyncMock()

    body = SegmentRequest(segment="doctor", years_of_experience=3)
    with patch.object(me_router, "now_kst", return_value=_kst_dt(2026)):
        await me_router.set_segment(body=body, current_user=user, db=db)

    assert user.segment == "doctor"
    assert user.years_of_experience == 3
    assert user.experience_last_increment_year == 2026
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_hygienist_signup_records_current_kst_year():
    user = _make_user()
    db = MagicMock()
    db.commit = AsyncMock()

    body = SegmentRequest(segment="hygienist", years_of_experience=10)
    with patch.object(me_router, "now_kst", return_value=_kst_dt(2030)):
        await me_router.set_segment(body=body, current_user=user, db=db)

    assert user.experience_last_increment_year == 2030


@pytest.mark.asyncio
async def test_student_other_signup_leaves_increment_year_null():
    """student_other 는 years_of_experience=None → last_increment_year도 None 유지."""
    user = _make_user()
    db = MagicMock()
    db.commit = AsyncMock()

    body = SegmentRequest(segment="student_other", years_of_experience=None)
    with patch.object(me_router, "now_kst", return_value=_kst_dt(2026)):
        await me_router.set_segment(body=body, current_user=user, db=db)

    assert user.segment == "student_other"
    assert user.years_of_experience is None
    assert user.experience_last_increment_year is None
