"""메시징 템플릿 카탈로그 — 공급자 독립적 템플릿 정의 (F-501)."""

from dataclasses import dataclass
from enum import Enum


class TemplateCategory(str, Enum):
    """알림 발송 카테고리 — 야간 차단 규칙 적용 기준 (F-502)."""

    BILLING = "billing"           # 결제 관련 — 야간에도 즉시 발송
    SUBSCRIPTION = "subscription"  # 구독 관련 — 야간에도 즉시 발송
    NOTICE = "notice"             # 공지·광고성 — 21~08 KST 야간 차단 대상
    SYSTEM = "system"             # 시스템 긴급 — 야간에도 즉시 발송


# URGENT_CATEGORIES: 야간 차단에서 제외되는 카테고리
URGENT_CATEGORIES = frozenset(
    [TemplateCategory.BILLING, TemplateCategory.SUBSCRIPTION, TemplateCategory.SYSTEM]
)


@dataclass(frozen=True)
class TemplateDefinition:
    """알림 템플릿 정의."""

    title: str
    body: str
    variables: list[str]
    category: TemplateCategory


# TEMPLATE_CATALOG: template_code → TemplateDefinition
# key 형식: "{category}.{action}" (공급자 콘솔 등록 ID는 ALIMTALK_TEMPLATE_MAP_JSON env로 주입)
TEMPLATE_CATALOG: dict[str, TemplateDefinition] = {
    # ── 결제 (billing) ──────────────────────────────────────────────────────
    "billing.first_charge_success": TemplateDefinition(
        title="첫 구독 결제 완료",
        body=(
            "안녕하세요, Denvia입니다.\n"
            "Pro 구독이 시작되었습니다.\n"
            "결제 금액: {amount_krw}원\n"
            "다음 결제일: {next_charge_at}"
        ),
        variables=["amount_krw", "next_charge_at"],
        category=TemplateCategory.BILLING,
    ),
    "billing.auto_renew_success": TemplateDefinition(
        title="구독 자동 갱신 완료",
        body=(
            "Denvia Pro 구독이 자동 갱신되었습니다.\n"
            "결제 금액: {amount_krw}원\n"
            "다음 결제일: {next_charge_at}"
        ),
        variables=["amount_krw", "next_charge_at"],
        category=TemplateCategory.BILLING,
    ),
    "billing.retry_failed_1": TemplateDefinition(
        title="결제 실패 안내 (1차)",
        body=(
            "Denvia 구독 결제에 실패했습니다.\n"
            "1일 후 자동 재시도됩니다.\n"
            "카드 정보를 확인해주세요."
        ),
        variables=[],
        category=TemplateCategory.BILLING,
    ),
    "billing.retry_failed_2": TemplateDefinition(
        title="결제 실패 안내 (2차)",
        body=(
            "Denvia 구독 결제가 다시 실패했습니다.\n"
            "3일 후 마지막으로 재시도됩니다.\n"
            "카드 정보를 확인하지 않으면 구독이 해지될 수 있습니다."
        ),
        variables=[],
        category=TemplateCategory.BILLING,
    ),
    "billing.retry_failed_3": TemplateDefinition(
        title="결제 최종 실패",
        body=(
            "Denvia 구독 결제가 최종 실패했습니다.\n"
            "구독이 해지 예정입니다.\n"
            "고객센터 문의: {support_url}"
        ),
        variables=["support_url"],
        category=TemplateCategory.BILLING,
    ),
    "billing.refund_success": TemplateDefinition(
        title="환불 처리 완료",
        body=(
            "환불이 완료되었습니다.\n"
            "환불 금액: {amount_krw}원\n"
            "처리일: {effective_at}"
        ),
        variables=["amount_krw", "effective_at"],
        category=TemplateCategory.BILLING,
    ),
    # ── 구독 (subscription) ──────────────────────────────────────────────────
    "subscription.cancel_requested": TemplateDefinition(
        title="구독 해지 예약 완료",
        body=(
            "Denvia Pro 구독 해지가 예약되었습니다.\n"
            "{effective_at}까지 서비스를 이용하실 수 있습니다."
        ),
        variables=["effective_at"],
        category=TemplateCategory.SUBSCRIPTION,
    ),
    "subscription.canceled_finalized": TemplateDefinition(
        title="구독 해지 완료",
        body=(
            "Denvia Pro 구독이 해지되었습니다.\n"
            "이용해 주셔서 감사합니다."
        ),
        variables=[],
        category=TemplateCategory.SUBSCRIPTION,
    ),
    "subscription.resumed": TemplateDefinition(
        title="구독 해지 철회 완료",
        body=(
            "Denvia Pro 구독 해지가 철회되었습니다.\n"
            "다음 결제일: {next_charge_at}"
        ),
        variables=["next_charge_at"],
        category=TemplateCategory.SUBSCRIPTION,
    ),
    # ── 공지 (notice) ────────────────────────────────────────────────────────
    "notice.generic": TemplateDefinition(
        title="Denvia 공지사항",
        body="{title}\n\n{body}",
        variables=["title", "body"],
        category=TemplateCategory.NOTICE,
    ),
}


def get_template(template_code: str) -> TemplateDefinition:
    """템플릿 코드로 TemplateDefinition을 조회한다. 없으면 ValueError."""
    if template_code not in TEMPLATE_CATALOG:
        raise ValueError(f"알 수 없는 template_code: {template_code}")
    return TEMPLATE_CATALOG[template_code]


def render_sms_body(template: TemplateDefinition, variables: dict[str, str]) -> str:
    """템플릿 본문에 변수를 삽입해 SMS 발송용 텍스트를 반환한다."""
    try:
        return template.body.format(**variables)
    except KeyError as e:
        raise ValueError(f"템플릿 변수 누락: {e}") from e
