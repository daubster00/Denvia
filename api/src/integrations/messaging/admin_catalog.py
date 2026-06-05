"""관리자 알림톡 관리 페이지(`/admin/alimtalk`) 전용 카탈로그 메타데이터.

`templates.py`(SSOT)에는 발송 본문만 정의돼 있어서 관리자 페이지에서 필요한
정보(누구한테 어떤 상황에 보내지는지, SMS와 알림톡 구분, 알리고 등록 코드,
본문 예시 텍스트)가 빠져 있다. 본 모듈이 그 메타데이터를 1곳에 모은다.

SSOT 정책:
- 본문(`body_example`)은 `render_sms_body(template, _example_vars)`로 자동 생성.
  본문 자체는 절대 본 모듈에서 수정하지 않는다 — 카카오 비즈채널 검증이 본문
  글자 단위로 매칭하므로 `templates.py`가 단일 진실.
- 알리고 등록 코드(`aligo_tpl_code`)는 `docs/ALIMTALK_TEMPLATES.md` §4 표와 동기화.
  매핑 변경 시 본 모듈과 docs 둘 다 업데이트.

🚫 `notice.generic`은 관리자 UI 전면 노출 금지(2026-05-28 발송 폐기). 본 모듈에서도
   인덱싱하지 않는다 — feedback_no_notice_alimtalk_in_admin_ui.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

from api.src.integrations.messaging.templates import (
    TEMPLATE_CATALOG,
    TemplateCategory,
    render_sms_body,
)


# ── 채널·수신자 enums ────────────────────────────────────────────────────


class CatalogChannel(str, Enum):
    """관리자 UI 노출용 채널 구분."""

    ALIMTALK = "alimtalk"
    SMS = "sms"


RecipientKind = Literal["user", "admin"]


# ── 카탈로그 메타 ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class AdminCatalogEntry:
    """관리자 알림톡 관리 페이지 1행의 메타데이터."""

    template_code: str          # 알림톡: TEMPLATE_CATALOG 키 / SMS: 가상 키("sms.otp", "sms.temp_password")
    channel: CatalogChannel
    title: str
    aligo_tpl_code: str | None  # SMS는 None, 알림톡은 콘솔 등록 코드(UH_/UI_)
    recipient_kind: RecipientKind
    trigger_situation: str      # 누구한테 어떤 상황에 발송되는지 (한국어 1~2문장)


# 알리고 등록 코드 매핑 (docs/ALIMTALK_TEMPLATES.md §4와 동기화)
_ALIGO_TPL_CODES: dict[str, str] = {
    "billing.first_charge_success": "UH_9828",
    "billing.retry_failed_1": "UH_9829",
    "billing.retry_failed_2": "UH_9831",
    "billing.retry_failed_3": "UH_9824",
    "billing.refund_success": "UH_9832",
    "billing.refund_manual": "UI_1758",
    "subscription.cancel_requested": "UH_9833",
    "subscription.canceled_finalized": "UH_9834",
    "subscription.resumed": "UH_9836",
    "support.reply_received": "UH_9837",
    "system.rag_rebuild_complete": "UH_9841",
    "system.rag_rebuild_failed": "UH_9842",
    "admin.budget_warning.80": "UH_9843",
    "admin.budget_warning.95": "UH_9845",
    "admin.budget_hard_cap_reached": "UH_9846",
    "admin.support_inquiry_created": "UH_9848",
    "admin.anomaly_detected": "UH_9849",
}


# 발송 시점·수신자 매핑 (docs/ALIMTALK_TEMPLATES.md §5 표 요약)
_TRIGGERS: dict[str, tuple[RecipientKind, str]] = {
    "billing.first_charge_success": (
        "user",
        "사용자가 Pro 구독을 처음 결제하면 결제 성공 직후 결제자에게 발송.",
    ),
    "billing.retry_failed_1": (
        "user",
        "자동 결제가 1차 실패한 직후 결제자에게 발송. 1일 뒤 자동 재시도 예정 안내.",
    ),
    "billing.retry_failed_2": (
        "user",
        "1차 재시도까지 실패해 2차 결제도 실패한 직후 결제자에게 발송. 3일 뒤 마지막 재시도 예정.",
    ),
    "billing.retry_failed_3": (
        "user",
        "3번째(최종) 재시도까지 모두 실패해 Pro 구독이 해지될 예정인 시점에 결제자에게 발송.",
    ),
    "billing.refund_success": (
        "user",
        "사용자가 마이페이지에서 청약철회(즉시 해지 + 전액 환불)를 진행한 직후 환불자에게 발송.",
    ),
    "billing.refund_manual": (
        "user",
        "관리자가 관리자 페이지 결제내역에서 운영 환불(전액/부분)을 처리한 직후 환불받은 사용자에게 발송.",
    ),
    "subscription.cancel_requested": (
        "user",
        "사용자가 마이페이지에서 해지 신청을 완료한 직후(다음 결제일 전까지 사용 가능 안내).",
    ),
    "subscription.canceled_finalized": (
        "user",
        "해지 예정일이 도래해 Pro 구독이 실제로 종료되어 무료 버전으로 전환되는 시점에 발송.",
    ),
    "subscription.resumed": (
        "user",
        "해지 예약 상태에서 사용자가 \"해지 취소\"를 누른 직후 해지 철회자에게 발송.",
    ),
    "support.reply_received": (
        "user",
        "관리자가 사용자의 1:1 문의에 답변을 등록한 직후 문의 작성자에게 발송.",
    ),
    "system.rag_rebuild_complete": (
        "admin",
        "관리자 페이지에서 RAG(지식베이스) 재빌드를 실행해 정상 완료된 직후 관리자(admin@denvia.ai.kr)에게 발송.",
    ),
    "system.rag_rebuild_failed": (
        "admin",
        "RAG 재빌드가 실패했을 때 관리자(admin@denvia.ai.kr)에게 발송.",
    ),
    "admin.budget_warning.80": (
        "admin",
        "월 OpenAI 사용액이 예산의 80%에 도달했을 때 관리자(admin@denvia.ai.kr)에게 발송.",
    ),
    "admin.budget_warning.95": (
        "admin",
        "월 OpenAI 사용액이 예산의 95%에 도달했을 때 관리자(admin@denvia.ai.kr)에게 발송.",
    ),
    "admin.budget_hard_cap_reached": (
        "admin",
        "월 예산을 100% 소진해 무료 사용자 질의가 자동 차단되는 시점에 관리자(admin@denvia.ai.kr)에게 발송.",
    ),
    "admin.support_inquiry_created": (
        "admin",
        "사용자가 신규 1:1 문의를 등록한 직후 관리자(admin@denvia.ai.kr)에게 발송.",
    ),
    "admin.anomaly_detected": (
        "admin",
        "이상탐지(비밀번호 3회 오류·동시 로그인·동일 질문 반복·IP 중복 등) 발생 시 관리자에게 발송. "
        "2026-05-22 자동 발송 폐기 후 관리자가 차단 트리거를 누른 시점에만 발송.",
    ),
}


# 카테고리 우선순위 — admin_alimtalk_service.get_summary 와 동일.
_CATEGORY_ORDER: dict[str, int] = {
    "billing": 0,
    "subscription": 1,
    "support": 2,
    "system": 3,
}


# 더미 변수 값 — body_example 렌더용. admin_alimtalk_service._build_test_variables 와 동일 규칙.
def _example_variables(variable_names: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for var in variable_names:
        key = var.lower()
        if "amount" in key:
            result[var] = "19,800"
        elif any(t in key for t in ("at", "date", "until")):
            result[var] = "2026-12-31 23:59"
        elif "name" in key:
            result[var] = "테스트사용자"
        elif "email" in key:
            result[var] = "test@denvia.local"
        elif "subject" in key:
            result[var] = "(문의 제목 예시)"
        elif "identifier" in key:
            result[var] = "user@example.com"
        elif "type" in key:
            result[var] = "비밀번호 3회 오류"
        elif "percent" in key:
            result[var] = "80"
        elif "krw" in key:
            result[var] = "₩115,220"
        elif "count" in key:
            result[var] = "1,234"
        elif "error" in key:
            result[var] = "(오류 메시지 예시)"
        elif "title" in key:
            result[var] = "(공지 제목 예시)"
        elif "body" in key:
            result[var] = "(공지 본문 예시)"
        elif "label" in key:
            result[var] = "전액 환불"
        else:
            result[var] = "테스트값"
    return result


# ── SMS 가상 템플릿 ─────────────────────────────────────────────────────
# SMS는 알리고 콘솔 등록이 없는 자유 텍스트지만, 관리자 페이지에서
# 알림톡과 같은 행으로 테스트 발송할 수 있게 가상 템플릿 코드를 부여한다.


@dataclass(frozen=True)
class SmsTemplate:
    """SMS 가상 템플릿 — 알리고 send_sms()로 전송할 본문."""

    template_code: str
    title: str
    body: str
    recipient_kind: RecipientKind
    trigger_situation: str


SMS_CATALOG: dict[str, SmsTemplate] = {
    "sms.otp": SmsTemplate(
        template_code="sms.otp",
        title="SMS 인증번호(OTP)",
        # 본문은 _OTP_BODY_TEMPLATE(`Aligo adapter`)과 동일 — 테스트 발송 시 더미 코드 "000000"
        # 으로 자동 치환. 실제 운영 OTP는 Redis에 저장 후 6자리 난수 발송.
        body="[Denvia] 인증번호: 000000\n3분 안에 입력해주세요.",
        recipient_kind="user",
        trigger_situation=(
            "회원가입·아이디찾기·비밀번호찾기 단계에서 사용자가 휴대폰 인증을 요청했을 때 "
            "Redis OTP 저장 후 본인 휴대폰으로 발송. 테스트 발송은 더미 코드(000000)로 전송."
        ),
    ),
    "sms.temp_password": SmsTemplate(
        template_code="sms.temp_password",
        title="SMS 임시 비밀번호",
        body="Denvia 임시 비밀번호: A1b2C3d4 (로그인 후 즉시 변경됩니다)",
        recipient_kind="user",
        trigger_situation=(
            "사용자가 비밀번호 찾기에서 이메일+휴대폰으로 본인 확인에 성공하면 "
            "8자리 임시 비밀번호를 생성·저장한 뒤 본인 휴대폰으로 발송. "
            "테스트 발송은 위 예시 본문 그대로 전송."
        ),
    ),
}


# ── 공개 API ────────────────────────────────────────────────────────────


def build_admin_catalog_entries() -> list[AdminCatalogEntry]:
    """관리자 UI 노출용 카탈로그 행 목록 — 알림톡 + SMS 통합.

    공지(notice) 카테고리는 발송 폐기 — 본 함수가 자동 제외.
    """
    entries: list[AdminCatalogEntry] = []

    # 알림톡 행
    for code, defn in TEMPLATE_CATALOG.items():
        if defn.category == TemplateCategory.NOTICE:
            continue  # 🚫 발송 폐기 — feedback_no_notice_alimtalk_in_admin_ui
        recipient, situation = _TRIGGERS.get(
            code,
            ("admin", "(발송 시점 미정의 — admin_catalog.py 보완 필요)"),
        )
        entries.append(
            AdminCatalogEntry(
                template_code=code,
                channel=CatalogChannel.ALIMTALK,
                title=defn.title,
                aligo_tpl_code=_ALIGO_TPL_CODES.get(code),
                recipient_kind=recipient,
                trigger_situation=situation,
            )
        )

    # SMS 행 — 본문 자유 텍스트, 알리고 매핑 없음
    for code, sms in SMS_CATALOG.items():
        entries.append(
            AdminCatalogEntry(
                template_code=code,
                channel=CatalogChannel.SMS,
                title=sms.title,
                aligo_tpl_code=None,
                recipient_kind=sms.recipient_kind,
                trigger_situation=sms.trigger_situation,
            )
        )

    return entries


def render_body_example(template_code: str) -> str:
    """관리자 페이지 상세보기에서 보여줄 본문 예시 텍스트."""
    if template_code in SMS_CATALOG:
        return SMS_CATALOG[template_code].body
    defn = TEMPLATE_CATALOG.get(template_code)
    if defn is None:
        return ""
    return render_sms_body(defn, _example_variables(defn.variables))


def get_aligo_tpl_code(template_code: str) -> str | None:
    """알림톡 등록 코드 조회 — 미등록·SMS·notice는 None."""
    return _ALIGO_TPL_CODES.get(template_code)


def get_recipient_kind(template_code: str) -> RecipientKind | None:
    if template_code in SMS_CATALOG:
        return SMS_CATALOG[template_code].recipient_kind
    trigger = _TRIGGERS.get(template_code)
    return trigger[0] if trigger else None


def get_trigger_situation(template_code: str) -> str | None:
    if template_code in SMS_CATALOG:
        return SMS_CATALOG[template_code].trigger_situation
    trigger = _TRIGGERS.get(template_code)
    return trigger[1] if trigger else None


def is_sms_template(template_code: str) -> bool:
    return template_code in SMS_CATALOG


def category_sort_key(category: str) -> int:
    return _CATEGORY_ORDER.get(category, 99)
