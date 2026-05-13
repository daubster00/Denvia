"""Story 9.1 — finance_service 단위 테스트.

대상:
- _excel_safe_cell: CSV-injection 4종 방어
- _kst_window: KST [from 00:00, (to+1) 00:00) 변환
- _row_to_item: JSONB code/message 추출 + null 케이스
"""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

import pytest

from api.src.services.finance_service import (
    _excel_safe_cell,
    _extract_refund_reason_from_event,
    _kst_window,
    _row_to_item,
)


class TestExcelSafeCell:
    @pytest.mark.parametrize("dangerous", ["=cmd", "+SUM(A1)", "-2+3", "@SYSTEM"])
    def test_dangerous_prefix_gets_quote(self, dangerous: str) -> None:
        out = _excel_safe_cell(dangerous)
        assert isinstance(out, str)
        assert out.startswith("'")
        assert out[1:] == dangerous

    def test_safe_string_unchanged(self) -> None:
        assert _excel_safe_cell("INVALID_CARD_NUMBER") == "INVALID_CARD_NUMBER"

    def test_empty_string_unchanged(self) -> None:
        assert _excel_safe_cell("") == ""

    def test_int_unchanged(self) -> None:
        assert _excel_safe_cell(123) == 123

    def test_none_unchanged(self) -> None:
        assert _excel_safe_cell(None) is None


class TestKstWindow:
    def test_single_day_window_is_24h(self) -> None:
        f = date(2026, 5, 1)
        t = date(2026, 5, 1)
        start, end_excl = _kst_window(f, t)
        assert start == datetime.fromisoformat("2026-05-01T00:00:00+09:00")
        # to+1 00:00 KST exclusive — 같은 날도 24h 윈도우.
        assert end_excl == datetime.fromisoformat("2026-05-02T00:00:00+09:00")

    def test_multi_day_window(self) -> None:
        f = date(2026, 5, 1)
        t = date(2026, 5, 7)
        start, end_excl = _kst_window(f, t)
        assert (end_excl - start).days == 7


class TestRowToItem:
    def _row(self, *, raw=None, charged_at=None, email="user@example.com"):
        return SimpleNamespace(
            event_id=42,
            payment_id=7,
            event_type="charge_failed",
            created_at=charged_at or datetime.fromisoformat("2026-05-07T05:23:11+00:00"),
            raw_response_json=raw,
            amount_krw=9900,
            provider_order_id="sub-7-2026-05-07",
            payment_status="failed",
            p_user_id=42,
            p_charged_at=None,
            email=email,
            bk_card_last4="1234",
            bk_card_company="현대",
        )

    def test_extracts_code_and_message_from_raw(self) -> None:
        item = _row_to_item(
            self._row(raw={"code": "INVALID_CARD_NUMBER", "message": "잘못된 카드번호"})
        )
        assert item.provider_error_code == "INVALID_CARD_NUMBER"
        assert item.provider_error_message == "잘못된 카드번호"

    def test_null_raw_returns_null_fields(self) -> None:
        item = _row_to_item(self._row(raw=None))
        assert item.provider_error_code is None
        assert item.provider_error_message is None

    def test_empty_raw_dict_returns_null_fields(self) -> None:
        item = _row_to_item(self._row(raw={}))
        assert item.provider_error_code is None
        assert item.provider_error_message is None

    def test_email_is_masked(self) -> None:
        item = _row_to_item(self._row(email="user@example.com"))
        assert item.user_email_masked == "u**@example.com"

    def test_short_local_email_not_masked(self) -> None:
        item = _row_to_item(self._row(email="a@b.co"))
        assert item.user_email_masked == "a@b.co"


class TestExtractRefundReason:
    def test_returns_reason_text(self) -> None:
        assert (
            _extract_refund_reason_from_event(
                {"reason": "구독 갱신 실수입니다", "qa_count_during_period": 0}
            )
            == "구독 갱신 실수입니다"
        )

    def test_none_raw_returns_none(self) -> None:
        assert _extract_refund_reason_from_event(None) is None

    def test_non_dict_returns_none(self) -> None:
        assert _extract_refund_reason_from_event("oops") is None

    def test_missing_reason_key_returns_none(self) -> None:
        assert _extract_refund_reason_from_event({"qa_count_during_period": 0}) is None

    def test_blank_reason_returns_none(self) -> None:
        assert _extract_refund_reason_from_event({"reason": "   "}) is None

    def test_non_string_reason_returns_none(self) -> None:
        assert _extract_refund_reason_from_event({"reason": 123}) is None

    def test_picks_toss_cancel_reason_when_top_level_missing(self) -> None:
        raw = {
            "status": "CANCELED",
            "cancels": [
                {
                    "cancelReason": "너무 가난해요. 환불 해주세요",
                    "canceledAt": "2026-05-12T08:58:52+09:00",
                    "cancelAmount": 9900,
                }
            ],
        }
        assert (
            _extract_refund_reason_from_event(raw) == "너무 가난해요. 환불 해주세요"
        )

    def test_picks_most_recent_cancel_reason(self) -> None:
        raw = {
            "cancels": [
                {"cancelReason": "옛날 취소", "canceledAt": "2026-05-01T00:00:00+09:00"},
                {"cancelReason": "최근 취소", "canceledAt": "2026-05-12T08:58:52+09:00"},
            ]
        }
        assert _extract_refund_reason_from_event(raw) == "최근 취소"

    def test_top_level_reason_wins_over_cancels(self) -> None:
        raw = {
            "reason": "관리자 메모",
            "cancels": [{"cancelReason": "토스 응답 사유"}],
        }
        assert _extract_refund_reason_from_event(raw) == "관리자 메모"

    def test_empty_cancels_returns_none(self) -> None:
        assert _extract_refund_reason_from_event({"cancels": []}) is None

    def test_cancels_with_no_valid_reason_returns_none(self) -> None:
        raw = {"cancels": [{"cancelReason": "  "}, {"cancelAmount": 9900}]}
        assert _extract_refund_reason_from_event(raw) is None
