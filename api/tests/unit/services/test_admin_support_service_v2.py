"""Story 9.3 — admin_support_service unit tests (확장 영역).

대상:
- _escape_ilike (q ILIKE escape)
- _kst_date_range (날짜 → datetime UTC 변환)
- _FORWARD_TRANSITIONS (force 분기)
- get_inquiry: subscription_status 매핑 (pro/free/blocked)
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.src.services import admin_support_service as svc


class TestEscapeIlike:
    def test_escape_percent(self):
        assert svc._escape_ilike("환불%") == "환불\\%"

    def test_escape_underscore(self):
        assert svc._escape_ilike("a_b") == "a\\_b"

    def test_escape_backslash(self):
        assert svc._escape_ilike("a\\b") == "a\\\\b"

    def test_no_escape_for_plain(self):
        assert svc._escape_ilike("환불") == "환불"


class TestKstDateRange:
    def test_both_none(self):
        s, e = svc._kst_date_range(None, None)
        assert s is None
        assert e is None

    def test_from_only_returns_kst_midnight(self):
        s, e = svc._kst_date_range(date(2026, 5, 1), None)
        assert s is not None and e is None
        assert s.tzinfo is not None
        assert s.year == 2026 and s.month == 5 and s.day == 1
        assert s.hour == 0 and s.minute == 0

    def test_to_includes_full_day(self):
        # to=2026-05-01 → 결과 끝은 2026-05-02 00:00 KST (exclusive)
        s, e = svc._kst_date_range(None, date(2026, 5, 1))
        assert e is not None
        assert e.day == 2  # +1일


class TestForwardTransitions:
    def test_open_can_go_to_in_progress(self):
        assert "in_progress" in svc._FORWARD_TRANSITIONS["open"]

    def test_open_can_go_to_resolved(self):
        assert "resolved" in svc._FORWARD_TRANSITIONS["open"]

    def test_in_progress_can_resolve(self):
        assert "resolved" in svc._FORWARD_TRANSITIONS["in_progress"]

    def test_resolved_blocks_revert_without_force(self):
        # resolved → 무엇이든 force 필요
        assert svc._FORWARD_TRANSITIONS["resolved"] == set()


class TestRecentQALimit:
    def test_recent_qa_limit_is_3(self):
        # Story 6.1은 10건. 9.3은 3건만 보여줌(컨텍스트용).
        assert svc._RECENT_QA_LIMIT == 3


def _make_inquiry_row(subscription_status: str = "free"):
    """get_inquiry SELECT 결과 row mock."""
    row = MagicMock()
    row.id = 7
    row.user_id = 10
    row.email = "user@example.com"
    row.phone = "01012345678"
    row.segment = "doctor"
    row.subscription_status = subscription_status
    row.user_created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    row.subject = "결제 환불"
    row.body = "문의 본문"
    row.status = "open"
    row.created_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
    row.resolved_at = None
    return row


class TestGetInquirySubscriptionStatusMapping:
    """users.subscription_status 가 'pro' 인 경우 그대로 'pro' 로 응답되어야 함.

    이전엔 schema 가 'active' 만 허용해 service 가 'pro' 를 'free' 로 깎아내렸다 → 코드리뷰 지적.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "raw_status,expected",
        [
            ("free", "free"),
            ("pro", "pro"),
            ("blocked", "blocked"),
            ("unknown_value", "free"),  # 미지의 값은 free 로 fallback
        ],
    )
    async def test_subscription_status_passthrough(self, raw_status, expected):
        row = _make_inquiry_row(subscription_status=raw_status)
        select_result = MagicMock()
        select_result.first = MagicMock(return_value=row)

        db = MagicMock()
        db.execute = AsyncMock(return_value=select_result)

        with (
            patch.object(svc, "_fetch_recent_qa", new=AsyncMock(return_value=[])),
            patch.object(svc, "_fetch_replies", new=AsyncMock(return_value=[])),
        ):
            detail = await svc.get_inquiry(db, inquiry_id=7)

        assert detail is not None
        assert detail.user_subscription_status == expected
