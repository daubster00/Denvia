"""Story 4.6 — admin_alimtalk_service 단위 테스트.

검증 대상:
1) _mask_phone — 11자리 010 / 10자리 / 12자리 / 비-010 / 빈 문자열 / 하이픈 입력 / None
2) _build_test_variables — amount / at·date·until / name / email / 그 외 / 빈 변수 / 다중 변수
3) _strip_phone — 하이픈·공백 제거
4) PHONE_REGEX — 정규식 직접 검증 (12 케이스)
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from api.src.services.admin_alimtalk_service import (
    _PHONE_REGEX,
    _build_test_variables,
    _mask_phone,
    _strip_phone,
)


# ── _mask_phone ─────────────────────────────────────────────────────────


class TestMaskPhone:
    def test_normal_010_eleven_digits(self):
        assert _mask_phone("01012341234") == "010-****-1234"

    def test_with_hyphens(self):
        assert _mask_phone("010-1234-1234") == "010-****-1234"

    def test_with_spaces(self):
        assert _mask_phone("010 1234 1234") == "010-****-1234"

    def test_ten_digits_old_format(self):
        # 011 + 7 = 10자리 — 비-010 케이스, **** + last 4
        assert _mask_phone("0111234567") == "****4567"

    def test_twelve_digits(self):
        # 12자리 — **** + last 4
        assert _mask_phone("010123456789") == "****6789"

    def test_non_010_prefix(self):
        assert _mask_phone("01699998888") == "****8888"

    def test_none_returns_none(self):
        assert _mask_phone(None) is None

    def test_empty_string_returns_none(self):
        assert _mask_phone("") is None

    def test_bytes_input(self):
        assert _mask_phone(b"01012341234") == "010-****-1234"

    def test_short_input(self):
        assert _mask_phone("123") == "****"


# ── _strip_phone ────────────────────────────────────────────────────────


class TestStripPhone:
    def test_removes_hyphens(self):
        assert _strip_phone("010-1234-1234") == "01012341234"

    def test_removes_spaces(self):
        assert _strip_phone(" 010 1234 1234 ") == "01012341234"

    def test_removes_parens(self):
        assert _strip_phone("(010)1234-1234") == "01012341234"

    def test_none_returns_empty(self):
        assert _strip_phone(None) == ""

    def test_already_clean(self):
        assert _strip_phone("01012341234") == "01012341234"


# ── _build_test_variables ───────────────────────────────────────────────


@dataclass
class _FakeTemplate:
    variables: list[str]


class TestBuildTestVariables:
    def test_amount_variable(self):
        tpl = _FakeTemplate(variables=["amount_krw"])
        result = _build_test_variables(tpl)
        assert result == {"amount_krw": "19,800"}

    def test_amount_substring_anywhere(self):
        tpl = _FakeTemplate(variables=["refund_amount_krw", "amount"])
        result = _build_test_variables(tpl)
        assert result["refund_amount_krw"] == "19,800"
        assert result["amount"] == "19,800"

    def test_date_variables(self):
        tpl = _FakeTemplate(variables=["next_charge_at", "effective_at", "expires_until"])
        result = _build_test_variables(tpl)
        assert result["next_charge_at"] == "2026-12-31 23:59"
        assert result["effective_at"] == "2026-12-31 23:59"
        assert result["expires_until"] == "2026-12-31 23:59"

    def test_name_variable(self):
        tpl = _FakeTemplate(variables=["user_name", "applicant_name"])
        result = _build_test_variables(tpl)
        assert result["user_name"] == "테스트사용자"
        assert result["applicant_name"] == "테스트사용자"

    def test_email_variable(self):
        tpl = _FakeTemplate(variables=["applicant_email_masked"])
        result = _build_test_variables(tpl)
        assert result["applicant_email_masked"] == "test@denvia.local"

    def test_other_variable(self):
        tpl = _FakeTemplate(variables=["title", "body", "inquiry_subject"])
        result = _build_test_variables(tpl)
        assert result["title"] == "테스트값"
        assert result["body"] == "테스트값"
        assert result["inquiry_subject"] == "테스트값"

    def test_empty_variables_list(self):
        tpl = _FakeTemplate(variables=[])
        assert _build_test_variables(tpl) == {}

    def test_mixed_real_template(self):
        # billing.first_charge_success 변수 셋
        tpl = _FakeTemplate(variables=["amount_krw", "next_charge_at"])
        result = _build_test_variables(tpl)
        assert result == {
            "amount_krw": "19,800",
            "next_charge_at": "2026-12-31 23:59",
        }


# ── _PHONE_REGEX (정규식 직접 검증) ──────────────────────────────────────


class TestPhoneRegex:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("01012341234", True),
            ("01000000000", True),
            ("01099999999", True),
            ("0101234123", False),  # 10자리
            ("010123412345", False),  # 12자리
            ("01112341234", False),  # 011
            ("01612341234", False),  # 016
            ("01712341234", False),  # 017
            ("0107", False),  # 너무 짧음
            ("abc12345678", False),  # 영문 포함
            ("", False),
            ("010-1234-1234", False),  # 하이픈 포함 (서비스에서 strip 후 검증)
        ],
    )
    def test_pattern(self, raw: str, expected: bool):
        assert bool(_PHONE_REGEX.match(raw)) is expected
