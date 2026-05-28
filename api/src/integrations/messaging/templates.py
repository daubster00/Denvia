"""메시징 템플릿 카탈로그 — 공급자 독립적 템플릿 정의 (F-501).

본 카탈로그의 본문은 알리고 콘솔 등록본과 글자 단위로 일치해야 한다.
카카오 알림톡은 등록 템플릿의 고정 텍스트가 발송 본문과 매칭될 때만 통과한다.
변수 부분(`{변수}`)은 가변 텍스트 영역으로 임의 값 허용.

알리고 등록명·tpl_code 매핑은 docs/ALIMTALK_TEMPLATES.md §5 참조.
"""

from dataclasses import dataclass, field
from enum import Enum


# 알리고 알림톡 버튼 link_type 코드 (알리고 공식 명세 그대로):
#   WL = 웹링크 / AL = 앱링크 / BK = 봇키워드 / MD = 메시지전달
#   DS = 배송조회 / BC = 상담톡 전환 / AC = 채널 추가
ALIGO_BUTTON_LINK_TYPES = frozenset({"WL", "AL", "BK", "MD", "DS", "BC", "AC"})


@dataclass(frozen=True)
class TemplateButton:
    """알림톡 등록 버튼 — 발송 form의 button_X JSON으로 직렬화된다.

    카카오 비즈채널 검증은 등록된 버튼이 발송 시점에 함께 전달되지 않으면
    "메시지가 템플릿과 일치하지 않음"으로 반려한다. 본 카탈로그가 SSOT인
    이상, 알리고 콘솔에 등록된 버튼 정의를 여기에 동기화해 두어야 한다.
    """

    name: str
    link_type: str            # WL / AL / BK / MD / DS / BC / AC
    link_mo: str = ""         # 모바일 URL (WL/AL)
    link_pc: str = ""         # PC URL (WL)
    link_ios: str = ""        # iOS 앱링크 (AL)
    link_and: str = ""        # Android 앱링크 (AL)


class TemplateCategory(str, Enum):
    """알림 발송 카테고리 — 야간 차단 규칙 적용 기준 (F-502)."""

    BILLING = "billing"           # 결제 관련 — 야간에도 즉시 발송
    SUBSCRIPTION = "subscription"  # 구독 관련 — 야간에도 즉시 발송
    NOTICE = "notice"             # 공지·광고성 — 21~08 KST 야간 차단 대상
    SYSTEM = "system"             # 시스템 긴급 — 야간에도 즉시 발송
    SUPPORT = "support"           # Story 9.3 — 고객문의 답변 알림 (야간에도 즉시 발송)


# URGENT_CATEGORIES: 야간 차단에서 제외되는 카테고리
URGENT_CATEGORIES = frozenset(
    [
        TemplateCategory.BILLING,
        TemplateCategory.SUBSCRIPTION,
        TemplateCategory.SYSTEM,
        TemplateCategory.SUPPORT,
    ]
)


@dataclass(frozen=True)
class TemplateDefinition:
    """알림 템플릿 정의."""

    title: str
    body: str
    variables: list[str]
    category: TemplateCategory
    buttons: list[TemplateButton] = field(default_factory=list)


# TEMPLATE_CATALOG: template_code → TemplateDefinition
# key 형식: "{category}.{action}" (공급자 콘솔 등록 ID는 ALIMTALK_TEMPLATE_MAP_JSON env로 주입)
#
# 2026-05-18 — 알리고 콘솔 등록본을 SSOT로 채택. 본문은 등록 캡쳐(17/17)와 글자 단위 정렬.
# 폐기 항목 (회귀 가드: test_messaging_templates.py DEPRECATED_TEMPLATE_CODES):
#   • billing.refund_denied                   : ADR-0001 편차 #5 — "거부" 개념 자체 폐기 (2026-05-12)
#   • billing.auto_renew_success              : 고객 검수 v4 (2026-05-18) — 삭제 요청
#   • billing.retry_success                   : 고객 검수 v4 (2026-05-18) — 삭제 요청
#   • subscription.extended_due_to_killswitch : 클라이언트 검수서 미포함 → 발송 안 함 (2026-05-18)
TEMPLATE_CATALOG: dict[str, TemplateDefinition] = {
    # ── 결제 (billing) ──────────────────────────────────────────────────────
    "billing.first_charge_success": TemplateDefinition(
        title="Denvia 첫 구독 결제 완료",
        body=(
            "안녕하세요, Denvia입니다.\n"
            "\n"
            "결제가 정상적으로 완료되어 Pro 구독이 시작되었습니다.\n"
            "\n"
            "결제 금액: {amount_krw}원\n"
            "다음 결제일: {next_charge_at}\n"
            "\n"
            "문의사항은 앱 내 \"문의작성\"을 통해 언제든 문의해주세요.\n"
            "\n"
            "감사합니다."
        ),
        variables=["amount_krw", "next_charge_at"],
        category=TemplateCategory.BILLING,
        buttons=[
            # 알리고 콘솔 등록 1번 버튼 — 카카오톡 채널 추가(AC). 발송 form button_1에
            # 함께 포함되지 않으면 카카오 비즈채널이 "메시지가 템플릿과 일치하지 않음"
            # 으로 거부한다(2026-05-28 진단 — user-facing 10종 미수신 원인).
            TemplateButton(name="채널 추가", link_type="AC"),
            TemplateButton(
                name="문의하기",
                link_type="WL",
                link_mo="https://denvia.ai.kr/my/inquiries/new",
                link_pc="https://denvia.ai.kr/my/inquiries/new",
            ),
        ],
    ),
    "billing.retry_failed_1": TemplateDefinition(
        title="Denvia 결제 실패 안내 1차",
        body=(
            "안녕하세요, Denvia입니다.\n"
            "\n"
            "Pro 구독 정기결제에 실패했습니다.\n"
            "\n"
            "1일 후 자동 재시도됩니다.\n"
            "카드 정보를 확인해주세요."
        ),
        variables=[],
        category=TemplateCategory.BILLING,
        buttons=[
            # 알리고 콘솔 등록 1번 버튼 — 카카오톡 채널 추가(AC). 발송 form button_1에
            # 함께 포함되지 않으면 카카오 비즈채널이 "메시지가 템플릿과 일치하지 않음"
            # 으로 거부한다(2026-05-28 진단 — user-facing 10종 미수신 원인).
            TemplateButton(name="채널 추가", link_type="AC"),
            TemplateButton(
                name="문의하기",
                link_type="WL",
                link_mo="https://denvia.ai.kr/my/inquiries/new",
                link_pc="https://denvia.ai.kr/my/inquiries/new",
            ),
        ],
    ),
    "billing.retry_failed_2": TemplateDefinition(
        title="Denvia 결제 실패 안내 2차",
        body=(
            "안녕하세요, Denvia입니다.\n"
            "\n"
            "Pro 구독 결제가 다시 실패했습니다.\n"
            "\n"
            "3일 후 마지막으로 재시도됩니다.\n"
            "마지막 재시도에서도 결제가 실패할 경우 Pro 구독은 자동 해지될 수 있습니다.\n"
            "\n"
            "문의사항은 앱 내 \"문의작성\"을 통해 언제든 문의해주세요.\n"
            "\n"
            "감사합니다."
        ),
        variables=[],
        category=TemplateCategory.BILLING,
        buttons=[
            # 알리고 콘솔 등록 1번 버튼 — 카카오톡 채널 추가(AC). 발송 form button_1에
            # 함께 포함되지 않으면 카카오 비즈채널이 "메시지가 템플릿과 일치하지 않음"
            # 으로 거부한다(2026-05-28 진단 — user-facing 10종 미수신 원인).
            TemplateButton(name="채널 추가", link_type="AC"),
            TemplateButton(
                name="문의하기",
                link_type="WL",
                link_mo="https://denvia.ai.kr/my/inquiries/new",
                link_pc="https://denvia.ai.kr/my/inquiries/new",
            ),
        ],
    ),
    "billing.retry_failed_3": TemplateDefinition(
        title="Denvia 결제 최종 실패 안내",
        body=(
            "안녕하세요, Denvia입니다.\n"
            "\n"
            "Pro 구독 결제가 최종 실패했습니다.\n"
            "\n"
            "Pro 구독이 해지될 예정입니다.\n"
            "고객센터를 통해 문의하실 수 있습니다."
        ),
        # 알리고 등록본에 support_url 변수 없음 (콘솔 웹링크 버튼으로 대체). 코드도 변수 제거.
        variables=[],
        category=TemplateCategory.BILLING,
        buttons=[
            TemplateButton(name="채널 추가", link_type="AC"),
            TemplateButton(
                name="문의작성",
                link_type="WL",
                link_mo="https://denvia.ai.kr/my/inquiries/new",
                link_pc="https://denvia.ai.kr/my/inquiries/new",
            ),
        ],
    ),
    "billing.refund_success": TemplateDefinition(
        title="Denvia 환불 처리 완료",
        body=(
            "환불이 완료되었습니다.\n"
            "\n"
            "처리 유형: {refund_reason_label}\n"
            "결제 원금: {amount_krw}원\n"
            "환불 금액: {refund_amount_krw}원\n"
            "처리일: {effective_at}\n"
            "\n"
            "영업일 3~4일 내 결제 카드로 입금됩니다.\n"
            "문의는 Denvia 1:1 문의 게시판을 이용해주세요."
        ),
        # Story 3.6 v1.1 청약철회(cooling_off) 전용.
        # 2026-05-26 이전에는 Story 9.1 운영 환불(manual_full/manual_partial)도 본 템플릿을
        # 공용으로 썼으나, 별도 등록(UI_1758, billing.refund_manual)이 완료되어 운영 환불은
        # 분리되었다. `refund_reason_label`은 표시용 한국어. cooling_off에서는 항상
        # "즉시 해지 및 전액 환불" 단일 라벨이 들어간다.
        variables=[
            "refund_reason_label",
            "amount_krw",
            "refund_amount_krw",
            "effective_at",
        ],
        category=TemplateCategory.BILLING,
        buttons=[
            # 알리고 콘솔 등록 1번 버튼 — 카카오톡 채널 추가(AC). 발송 form button_1에
            # 함께 포함되지 않으면 카카오 비즈채널이 "메시지가 템플릿과 일치하지 않음"
            # 으로 거부한다(2026-05-28 진단 — user-facing 10종 미수신 원인).
            TemplateButton(name="채널 추가", link_type="AC"),
            TemplateButton(
                name="문의하기",
                link_type="WL",
                link_mo="https://denvia.ai.kr/my/inquiries/new",
                link_pc="https://denvia.ai.kr/my/inquiries/new",
            ),
        ],
    ),
    "billing.refund_manual": TemplateDefinition(
        title="Denvia 운영 환불 처리 완료",
        body=(
            "안녕하세요, Denvia입니다.\n"
            "\n"
            "요청하신 환불이 처리되었습니다.\n"
            "\n"
            "결제금액: {amount_krw}원\n"
            "환불금액: {refund_amount_krw}원\n"
            "환불처리일: {effective_at}\n"
            "\n"
            "영업일 3~4일 내 결제 카드로 입금됩니다.\n"
            "자세한 내용은 1:1 문의 답변에서 확인해주세요."
        ),
        # Story 9.1 v1.1 운영 환불(관리자 수동 전액·부분) 전용. 2026-05-26 분리 등록.
        # 알리고 콘솔 등록명 "Denvia 운영 환불 처리 완료" (UI_1758). 콘솔의 변수명은
        # 한국어(#{결제금액}/#{환불금액}/#{환불처리일})지만, 알리고는 최종 렌더 텍스트의
        # 고정 문구만 검증하므로 코드 변수명은 영문 유지(다른 템플릿과 일관).
        variables=["amount_krw", "refund_amount_krw", "effective_at"],
        category=TemplateCategory.BILLING,
        # UI_1758 알리고 콘솔 등록 버튼(2026-05-28 스크린샷 동기화).
        # 운영 환불은 1:1 문의 답변에서 진행되므로 목록 페이지로 이동.
        buttons=[
            TemplateButton(name="채널 추가", link_type="AC"),
            TemplateButton(
                name="1:1문의 답변",
                link_type="WL",
                link_mo="https://denvia.ai.kr/my/inquiries",
                link_pc="https://denvia.ai.kr/my/inquiries",
            ),
        ],
    ),
    # ── 구독 (subscription) ──────────────────────────────────────────────────
    "subscription.cancel_requested": TemplateDefinition(
        title="Denvia 구독 해지 예약 완료",
        body=(
            "Pro 구독 해지가 예약되었습니다.\n"
            "\n"
            "{effective_at}까지 Pro 구독 서비스를 이용하실 수 있으며, 이후 무료 버전으로 전환됩니다.\n"
            "\n"
            "감사합니다."
        ),
        variables=["effective_at"],
        category=TemplateCategory.SUBSCRIPTION,
        buttons=[
            # 알리고 콘솔 등록 1번 버튼 — 카카오톡 채널 추가(AC). 발송 form button_1에
            # 함께 포함되지 않으면 카카오 비즈채널이 "메시지가 템플릿과 일치하지 않음"
            # 으로 거부한다(2026-05-28 진단 — user-facing 10종 미수신 원인).
            TemplateButton(name="채널 추가", link_type="AC"),
            TemplateButton(
                name="문의하기",
                link_type="WL",
                link_mo="https://denvia.ai.kr/my/inquiries/new",
                link_pc="https://denvia.ai.kr/my/inquiries/new",
            ),
        ],
    ),
    "subscription.canceled_finalized": TemplateDefinition(
        title="Denvia 구독 해지 완료",
        body=(
            "Denvia Pro 구독이 해지되었습니다.\n"
            "\n"
            "{user_name}님은 {effective_at}부터 무료 버전으로 전환됩니다.\n"
            "\n"
            "감사합니다."
        ),
        # user_name: 호출 측이 생략하면 billing_service._notify_subscription_event 내부에서
        # email local-part로 자동 주입(없으면 "고객").
        variables=["user_name", "effective_at"],
        category=TemplateCategory.SUBSCRIPTION,
        buttons=[
            # 알리고 콘솔 등록 1번 버튼 — 카카오톡 채널 추가(AC). 발송 form button_1에
            # 함께 포함되지 않으면 카카오 비즈채널이 "메시지가 템플릿과 일치하지 않음"
            # 으로 거부한다(2026-05-28 진단 — user-facing 10종 미수신 원인).
            TemplateButton(name="채널 추가", link_type="AC"),
            TemplateButton(
                name="문의하기",
                link_type="WL",
                link_mo="https://denvia.ai.kr/my/inquiries/new",
                link_pc="https://denvia.ai.kr/my/inquiries/new",
            ),
        ],
    ),
    "subscription.resumed": TemplateDefinition(
        title="Denvia 구독 해지 철회 완료",
        body="Pro 구독 해지가 철회되었습니다.",
        variables=[],
        category=TemplateCategory.SUBSCRIPTION,
        buttons=[
            # 알리고 콘솔 등록 1번 버튼 — 카카오톡 채널 추가(AC). 발송 form button_1에
            # 함께 포함되지 않으면 카카오 비즈채널이 "메시지가 템플릿과 일치하지 않음"
            # 으로 거부한다(2026-05-28 진단 — user-facing 10종 미수신 원인).
            TemplateButton(name="채널 추가", link_type="AC"),
            TemplateButton(
                name="문의하기",
                link_type="WL",
                link_mo="https://denvia.ai.kr/my/inquiries/new",
                link_pc="https://denvia.ai.kr/my/inquiries/new",
            ),
        ],
    ),
    # ── 고객문의 (support) — Story 9.3 ───────────────────────────────────────
    "support.reply_received": TemplateDefinition(
        title="Denvia 고객문의 답변 도착",
        body=(
            "고객문의에 답변이 등록되었습니다.\n"
            "\n"
            "문의 제목: {inquiry_subject}\n"
            "\n"
            "쪽지함에서 자세한 내용을 확인해주세요."
        ),
        variables=["inquiry_subject"],
        category=TemplateCategory.SUPPORT,
        buttons=[
            # 알리고 콘솔 등록 1번 버튼 — 카카오톡 채널 추가(AC). 발송 form button_1에
            # 함께 포함되지 않으면 카카오 비즈채널이 "메시지가 템플릿과 일치하지 않음"
            # 으로 거부한다(2026-05-28 진단 — user-facing 10종 미수신 원인).
            TemplateButton(name="채널 추가", link_type="AC"),
            TemplateButton(
                name="문의하기",
                link_type="WL",
                link_mo="https://denvia.ai.kr/my/inquiries/new",
                link_pc="https://denvia.ai.kr/my/inquiries/new",
            ),
        ],
    ),
    # ── 공지 (notice) ────────────────────────────────────────────────────────
    # 🚫 알림톡 미발송 (2026-05-28 결정) — 본 카탈로그에 잔존하는 이유는 야간 차단(F-502)
    # 회귀 테스트(test_night_block_toggle, test_notification_service)가 NOTICE 카테고리
    # 템플릿 1종을 fixture로 요구하기 때문이다. 운영 코드에서 `template_code="notice.generic"`
    # 으로 enqueue/dispatch 호출은 일절 없으며(검색 0건), 알리고 콘솔 UH_9838 등록본도
    # 더 이상 카카오 채널로 발송되지 않는다. 신규 공지는 인앱 쪽지함(`/inbox`)으로만
    # 노출한다.
    # 버튼은 제거(콘솔 등록 버튼 동기화 대상 아님 — 발송 자체가 없으므로).
    "notice.generic": TemplateDefinition(
        title="Denvia 공지사항 안내",
        body="{title}\n\n{body}",
        variables=["title", "body"],
        category=TemplateCategory.NOTICE,
    ),
    # ── 시스템 (system) ──────────────────────────────────────────────────────────
    "system.rag_rebuild_complete": TemplateDefinition(
        title="Denvia RAG 재빌드 완료",
        body="Denvia RAG 재빌드가 완료되었습니다.\n활성 청크 수: {chunk_count}",
        variables=["chunk_count"],
        category=TemplateCategory.SYSTEM,
        buttons=[
            TemplateButton(
                name="확인하기",
                link_type="WL",
                link_mo="https://denvia.ai.kr/admin/rag/data",
                link_pc="https://denvia.ai.kr/admin/rag/data",
            ),
        ],
    ),
    "system.rag_rebuild_failed": TemplateDefinition(
        title="Denvia RAG 재빌드 실패",
        body="Denvia RAG 재빌드가 실패했습니다.\n오류: {error}",
        variables=["error"],
        category=TemplateCategory.SYSTEM,
        buttons=[
            TemplateButton(
                name="확인하기",
                link_type="WL",
                link_mo="https://denvia.ai.kr/admin/rag/data",
                link_pc="https://denvia.ai.kr/admin/rag/data",
            ),
        ],
    ),
    # ── 관리자 예산 경고 (Story 5.2) ─────────────────────────────────────────
    # 알리고 등록본은 본문 첫 줄에 [Denvia] 제목을 중복 포함. 코드도 동일하게 작성.
    # spent_krw / limit_krw 값은 호출처에서 "₩" prefix + 콤마 구분 포함해 넘긴다 (예: "₩115,220").
    # 전체 시스템 KRW 통일에 따라 USD 변수(spent_usd/limit_usd) → KRW 변수로 교체.
    # 알리고 콘솔에 등록된 템플릿도 동일하게 재등록 + 카카오 재심사 필요 (자료/Denvia_카카오_알림톡_메시지_안내서.docx 동기화).
    "admin.budget_warning.80": TemplateDefinition(
        title="Denvia 월 예산 80% 도달",
        body=(
            "[Denvia] 월 예산 80% 도달\n"
            "\n"
            "이번 달 OpenAI API 비용이 월 예산의 {percent}%에 도달했습니다.\n"
            "\n"
            "현재 사용액: {spent_krw}\n"
            "월 한도: {limit_krw}\n"
            "\n"
            "관리자 대시보드에서 사용 패턴을 점검해주세요."
        ),
        variables=["percent", "spent_krw", "limit_krw"],
        category=TemplateCategory.SYSTEM,
        buttons=[
            TemplateButton(
                name="확인하기",
                link_type="WL",
                link_mo="https://denvia.ai.kr/admin",
                link_pc="https://denvia.ai.kr/admin",
            ),
        ],
    ),
    "admin.budget_warning.95": TemplateDefinition(
        title="Denvia 월 예산 95% 도달 안내",
        body=(
            "[Denvia] 월 예산 95% 도달 안내\n"
            "\n"
            "이번 달 OpenAI API 비용이 월 예산의 {percent}%에 도달했습니다.\n"
            "\n"
            "100% 도달 시 무료 질의가 자동 차단됩니다.\n"
            "\n"
            "현재 사용액: {spent_krw} / {limit_krw}"
        ),
        variables=["percent", "spent_krw", "limit_krw"],
        category=TemplateCategory.SYSTEM,
        buttons=[
            TemplateButton(
                name="확인하기",
                link_type="WL",
                link_mo="https://denvia.ai.kr/admin",
                link_pc="https://denvia.ai.kr/admin",
            ),
        ],
    ),
    "admin.budget_hard_cap_reached": TemplateDefinition(
        title="Denvia 월 예산 소진 안내",
        body=(
            "[Denvia] 월 예산 소진 안내\n"
            "\n"
            "월 예산 {limit_krw}이 소진되어 무료 사용자 질의가 일시 차단되었습니다.\n"
            "\n"
            "유료 사용자는 영향 없습니다.\n"
            "다음 달 1일 자동 해제 또는 예산 상향 시 즉시 재개됩니다."
        ),
        variables=["limit_krw"],
        category=TemplateCategory.SYSTEM,
        buttons=[
            TemplateButton(
                name="확인하기",
                link_type="WL",
                link_mo="https://denvia.ai.kr/admin",
                link_pc="https://denvia.ai.kr/admin",
            ),
        ],
    ),
    # ── 관리자 고객문의 신규 접수 (Story 9.3 후속) ───────────────────────────
    "admin.support_inquiry_created": TemplateDefinition(
        title="Denvia 신규 1:1 문의 접수 알림",
        body=(
            "[Denvia] 새 1:1 문의 접수\n"
            "\n"
            "새 1:1 문의가 접수되었습니다.\n"
            "\n"
            "작성자: {user_name}\n"
            "문의 제목: {inquiry_subject}\n"
            "\n"
            "관리자 페이지에서 답변을 처리해주세요."
        ),
        variables=["user_name", "inquiry_subject"],
        category=TemplateCategory.SYSTEM,
        buttons=[
            TemplateButton(
                name="확인하기",
                link_type="WL",
                link_mo="https://denvia.ai.kr/admin/cs",
                link_pc="https://denvia.ai.kr/admin/cs",
            ),
        ],
    ),
    # ── 관리자 가입 신청 알림 — 발송 폐기 (2026-05-28) ───────────────────────
    # `admin.account.signup_request` (Story 10.2, 2026-05-27)는 추가 직후 폐기.
    # master/operator는 /admin/admins 페이지의 pending 목록을 직접 확인한다.
    # 본 카탈로그·관련 서비스 함수(`enqueue_admin_signup_request_alert`)·알리고 콘솔
    # 모두에서 제거. 신규 발송 트리거 없음.
    # ── 관리자 계정 수명주기 알림 (Story 10.3) — 발송 폐기 (2026-05-27) ───
    # admin.account.approved / blocked / unblocked / deleted 4종을 한 차례 추가했다가
    # 즉시 제거. 운영자가 /admin/admins 페이지에서 대상자 휴대폰을 직접 보고
    # 필요 시 별도 채널로 안내하는 것으로 충분 — 알림톡 surface 추가 보류.
    # 신규 발송 트리거 없음. 본 카탈로그·docs/ALIMTALK_TEMPLATES.md·알리고 콘솔 모두 미등록.
    # ── 관리자 이상탐지 알림 (2026-05-18 고객 추가요청) ──────────────────────
    # 사용자 측 보안 알림(5-1~5-6)을 모두 폐기하고, 이상탐지 시 관리자에게만
    # 단일 채널로 발송. 무료/유료 구분 없음. 발송 연결은 Story 6.2 후속.
    "admin.anomaly_detected": TemplateDefinition(
        title="Denvia 이상탐지 관리자 알림",
        body=(
            "[Denvia] 이상탐지 알림\n"
            "\n"
            "이상탐지 내용: {anomaly_type}\n"
            "이상탐지 계정: {user_identifier}\n"
            "\n"
            "관리자 페이지에서 확인이 필요합니다."
        ),
        # anomaly_type: 한국어 사유 라벨 (예: "비밀번호 3회 오류", "동시 로그인", "동일 질문 반복", "IP 중복")
        # user_identifier: 대상 계정 식별자 (email 또는 user_id)
        variables=["anomaly_type", "user_identifier"],
        category=TemplateCategory.SYSTEM,
        # 2026-05-28 — 알리고 콘솔(UH_9849) 등록 버튼 동기화.
        # 발송 form에 button_1을 함께 보내지 않으면 카카오 검증이
        # "메시지가 템플릿과 일치하지 않음"으로 반려한다(검증 완료).
        buttons=[
            TemplateButton(
                name="확인하기",
                link_type="WL",
                link_mo="https://denvia.ai.kr/admin/anomaly",
                link_pc="https://denvia.ai.kr/admin/anomaly",
            ),
        ],
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
