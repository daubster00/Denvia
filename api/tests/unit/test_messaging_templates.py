"""TEMPLATE_CATALOG 및 템플릿 유틸리티 유닛 테스트."""

import pytest

from api.src.integrations.messaging.templates import (
    TEMPLATE_CATALOG,
    URGENT_CATEGORIES,
    TemplateCategory,
    get_template,
    render_sms_body,
)

# 스토리 AC-2에서 명시한 최소 세트
REQUIRED_TEMPLATE_CODES = [
    "billing.first_charge_success",
    "billing.auto_renew_success",
    "billing.retry_failed_1",
    "billing.retry_failed_2",
    "billing.retry_failed_3",
    "billing.refund_success",
    "subscription.cancel_requested",
    "subscription.canceled_finalized",
    "subscription.resumed",
    "notice.generic",
]


class TestTemplateCatalog:
    def test_all_required_templates_exist(self):
        """AC-2 최소 템플릿 세트가 TEMPLATE_CATALOG에 존재한다."""
        for code in REQUIRED_TEMPLATE_CODES:
            assert code in TEMPLATE_CATALOG, f"필수 템플릿 없음: {code}"

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
        t = get_template("billing.first_charge_success")
        body = render_sms_body(t, {"amount_krw": "9,900", "next_charge_at": "2026-05-23"})
        assert "9,900" in body
        assert "2026-05-23" in body

    def test_render_missing_variable_raises(self):
        t = get_template("billing.first_charge_success")
        with pytest.raises(ValueError, match="템플릿 변수 누락"):
            render_sms_body(t, {"amount_krw": "9,900"})  # next_charge_at 누락

    def test_render_no_variables_template(self):
        t = get_template("billing.retry_failed_1")
        body = render_sms_body(t, {})
        assert isinstance(body, str)
        assert len(body) > 0
