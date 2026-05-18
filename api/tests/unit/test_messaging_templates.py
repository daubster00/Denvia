"""TEMPLATE_CATALOG 및 템플릿 유틸리티 유닛 테스트."""

import pytest

from api.src.integrations.messaging.templates import (
    TEMPLATE_CATALOG,
    URGENT_CATEGORIES,
    TemplateCategory,
    get_template,
    render_sms_body,
)

# 스토리 AC-2 최소 세트 — 2026-05-18 고객 검수 v4 반영:
# `billing.auto_renew_success`(1-2) / `billing.retry_success`(1-3)는 고객 삭제 요청으로 폐기.
REQUIRED_TEMPLATE_CODES = [
    "billing.first_charge_success",
    "billing.retry_failed_1",
    "billing.retry_failed_2",
    "billing.retry_failed_3",
    "billing.refund_success",
    "subscription.cancel_requested",
    "subscription.canceled_finalized",
    "subscription.resumed",
    "notice.generic",
]

# 2026-05-18 고객 검수 v4 — 폐기 처리된 템플릿 코드 (회귀 가드)
DEPRECATED_TEMPLATE_CODES = [
    "billing.auto_renew_success",
    "billing.retry_success",
]


class TestTemplateCatalog:
    def test_all_required_templates_exist(self):
        """AC-2 최소 템플릿 세트가 TEMPLATE_CATALOG에 존재한다."""
        for code in REQUIRED_TEMPLATE_CODES:
            assert code in TEMPLATE_CATALOG, f"필수 템플릿 없음: {code}"

    def test_deprecated_templates_are_absent(self):
        """고객 v4 검수에서 삭제된 템플릿은 카탈로그에서 제거되어 있다."""
        for code in DEPRECATED_TEMPLATE_CODES:
            assert code not in TEMPLATE_CATALOG, (
                f"폐기 템플릿이 아직 존재합니다: {code}"
            )

    def test_billing_templates_have_billing_category(self):
        """billing.* 템플릿은 모두 BILLING 카테고리다."""
        billing_codes = [c for c in TEMPLATE_CATALOG if c.startswith("billing.")]
        for code in billing_codes:
            assert TEMPLATE_CATALOG[code].category == TemplateCategory.BILLING, code

    def test_subscription_templates_have_subscription_category(self):
        """subscription.* 템플릿은 모두 SUBSCRIPTION 카테고리다."""
        sub_codes = [c for c in TEMPLATE_CATALOG if c.startswith("subscription.")]
        for code in sub_codes:
            assert TEMPLATE_CATALOG[code].category == TemplateCategory.SUBSCRIPTION, code

    def test_notice_templates_have_notice_category(self):
        """notice.* 템플릿은 모두 NOTICE 카테고리다."""
        notice_codes = [c for c in TEMPLATE_CATALOG if c.startswith("notice.")]
        for code in notice_codes:
            assert TEMPLATE_CATALOG[code].category == TemplateCategory.NOTICE, code

    def test_all_templates_have_required_fields(self):
        """모든 템플릿이 title, body, variables, category를 가진다."""
        for code, defn in TEMPLATE_CATALOG.items():
            assert defn.title, f"{code}: title 누락"
            assert defn.body, f"{code}: body 누락"
            assert isinstance(defn.variables, list), f"{code}: variables 타입 오류"
            assert isinstance(defn.category, TemplateCategory), f"{code}: category 타입 오류"

    def test_template_variables_are_present_in_body(self):
        """각 템플릿의 variables에 선언된 키가 body에 존재한다."""
        for code, defn in TEMPLATE_CATALOG.items():
            for var in defn.variables:
                placeholder = f"{{{var}}}"
                assert placeholder in defn.body, (
                    f"{code}: body에 변수 '{var}' placeholder 없음"
                )


class TestUrgentCategories:
    def test_billing_is_urgent(self):
        assert TemplateCategory.BILLING in URGENT_CATEGORIES

    def test_subscription_is_urgent(self):
        assert TemplateCategory.SUBSCRIPTION in URGENT_CATEGORIES

    def test_system_is_urgent(self):
        assert TemplateCategory.SYSTEM in URGENT_CATEGORIES

    def test_notice_is_not_urgent(self):
        """NOTICE는 야간 차단 대상이므로 URGENT에 포함되지 않는다."""
        assert TemplateCategory.NOTICE not in URGENT_CATEGORIES


class TestGetTemplate:
    def test_valid_code_returns_template(self):
        t = get_template("billing.first_charge_success")
        assert t.category == TemplateCategory.BILLING

    def test_invalid_code_raises_value_error(self):
        with pytest.raises(ValueError, match="알 수 없는 template_code"):
            get_template("invalid.code")


class TestRenderSmsBody:
    def test_render_with_valid_variables(self):
        # 2026-05-18 v4 — first_charge_success는 변수 0개로 변경. 대신 refund_success로 검증.
        t = get_template("billing.refund_success")
        body = render_sms_body(
            t,
            {
                "refund_reason_label": "전액 환불",
                "amount_krw": "30,000",
                "refund_amount_krw": "30,000",
                "effective_at": "2026년 5월 18일",
            },
        )
        assert "전액 환불" in body
        assert "30,000" in body
        assert "2026년 5월 18일" in body

    def test_render_missing_variable_raises(self):
        t = get_template("billing.refund_success")
        with pytest.raises(ValueError, match="템플릿 변수 누락"):
            render_sms_body(t, {"refund_reason_label": "전액 환불"})  # 나머지 누락

    def test_render_no_variables_template(self):
        t = get_template("billing.retry_failed_1")
        body = render_sms_body(t, {})
        assert isinstance(body, str)
        assert len(body) > 0
