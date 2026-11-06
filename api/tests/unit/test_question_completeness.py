"""조각 질문 판정 고정 — #149 결정 ①(되묻기) · 2026-11-03 검수 P0-5.

이 규칙은 **사용자에게 답을 주지 않고 되묻는** 판단이다. 경계가 흔들리면 정상 질문에도
"조금만 더 적어주세요" 가 뜨고(오탐), 반대로 조각 질문이 엉뚱한 항목으로 검색된다(미탐).

검수 문서에 적힌 **오탐·미탐 예시 전체를 표로 고정**한다. 구현을 바꿀 때 이 표가
기대 결과이고, 구현이 기준이 아니다.
"""

from __future__ import annotations

import pytest

from api.src.rag_integration.question_completeness import (
    ANSWER_KIND_CLARIFICATION,
    CLARIFY_MESSAGE,
    first_anaphora_index,
    has_anaphora,
    has_billing_topic,
    needs_clarification,
)

# ──────────────────────────────────────────────────────────────────────────────
# 1. 검수 문서 §P0-5 "확인된 오탐 예시" — 되묻으면 안 된다
# ──────────────────────────────────────────────────────────────────────────────

REVIEW_FALSE_POSITIVE_CASES = [
    "초진료?",
    "본인부담금?",
    "요양급여 기준?",
    "교정도 되나요?",
    "초진료산정기준알려주세요",
]


@pytest.mark.parametrize("question", REVIEW_FALSE_POSITIVE_CASES)
def test_review_false_positive_cases_are_answered(question: str) -> None:
    """스스로 뜻이 통하는 청구 주제 질문은 되묻지 않고 답한다."""
    assert needs_clarification(question, has_known_topic=False) is False


# ──────────────────────────────────────────────────────────────────────────────
# 2. 검수 문서 §P0-5 "확인된 미탐 예시" — 반드시 되물어야 한다
# ──────────────────────────────────────────────────────────────────────────────

REVIEW_FALSE_NEGATIVE_CASES = [
    "몇 번까지 돼?",
    "65세 미만의 경우는?",
    "그렇게 하면 돼요?",
    "그 경우에는 환자 본인부담금이 어떻게 달라지는 건가요?",
]


@pytest.mark.parametrize("question", REVIEW_FALSE_NEGATIVE_CASES)
def test_review_false_negative_cases_ask_back(question: str) -> None:
    """앞 대화 없이는 뜻이 정해지지 않는 질문은 되묻는다."""
    assert needs_clarification(question, has_known_topic=False) is True


def test_anaphora_beats_topic_and_length() -> None:
    """지시어는 **길이·주제보다 먼저** 평가한다 (검수 P0-5 필수 수정).

    "그 경우에는 환자 본인부담금이 …" 는 7어절이고 주제어(본인부담금)도 있지만,
    "그 경우" 가 가리키는 앞 대화 없이는 어떤 기준을 묻는지 정해지지 않는다.
    """
    question = "그 경우에는 환자 본인부담금이 어떻게 달라지는 건가요?"
    assert has_billing_topic(question) is True  # 주제어는 있다
    assert len(question.split()) >= 6           # 길이 예외에 걸릴 길이다
    assert needs_clarification(question, has_known_topic=True) is True


# ──────────────────────────────────────────────────────────────────────────────
# 3. 기존 고정 케이스 (결정 ① 도입 시점부터 유지)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "question",
    [
        "하얀색?",                 # 클라이언트가 든 바로 그 예시
        "하얀색",
        "몇 번?",
        "왜?",
        "그건?",
        "그건 몇 번까지 돼?",
        "그럼 그 경우는 어떻게 돼?",
        "아까 그거 다시 알려줘",
        "그러면 안 되는 거야?",
        "그경우에는 어떻게 되나요?",   # 공백 없이 붙여 쓴 지시어
    ],
)
def test_fragment_questions_need_clarification(question: str) -> None:
    assert needs_clarification(question, has_known_topic=False) is True


@pytest.mark.parametrize(
    "question",
    [
        "스케일링 산정 기준 알려주세요",
        "임플란트 보험 적용 조건",
        "틀니 보험 적용 조건이 궁금한데 알려주세요",
        "초진 재진 구분 기준은 무엇인가요",
        "본인부담금 계산 어떻게 하나요",
        "요양급여비용 청구 방법 알려주세요",
        "11~17 발치 산정 어떻게 하나요",
        "GI 충전?",
    ],
)
def test_self_contained_questions_are_answered(question: str) -> None:
    assert needs_clarification(question, has_known_topic=False) is False


@pytest.mark.parametrize("question", ["하얀색?", "11~17 가능?"])
def test_known_topic_from_vendor_exempts(question: str) -> None:
    """vendor 행위 추출이 주제를 잡았으면(장애인가산 행위 등) 단독 검색이 가능하다."""
    assert needs_clarification(question, has_known_topic=True) is False


def test_empty_question_is_not_our_job() -> None:
    assert needs_clarification("", has_known_topic=False) is False
    assert needs_clarification("   ", has_known_topic=False) is False
    assert needs_clarification("?", has_known_topic=False) is False


# ──────────────────────────────────────────────────────────────────────────────
# 4. 주제 판별기 — vendor 가 모르는 일반 청구 주제를 웹 계층에서 알아야 한다
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "question",
    [
        "초진료?",
        "재진 산정",
        "본인부담금 얼마예요",
        "요양급여 기준",
        "교정도 되나요?",
        "삭감되면 어떻게 하나요",
        "초진료산정기준알려주세요",   # 공백 없음
        "파노라마 촬영",
        "장애인 가산",
    ],
)
def test_has_billing_topic_true(question: str) -> None:
    assert has_billing_topic(question) is True


@pytest.mark.parametrize(
    "question",
    ["하얀색?", "몇 번까지 돼?", "그건?", "왜요?", "65세 미만은?"],
)
def test_has_billing_topic_false(question: str) -> None:
    assert has_billing_topic(question) is False


# ──────────────────────────────────────────────────────────────────────────────
# 5. 지시어 탐지
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "question",
    [
        "그럼 어떻게 되나요",
        "그건 안 되나요",
        "이거는 어떻게 산정하나요",
        "그 경우에는 어떻게 하나요",
        "같은 경우에도 적용되나요",
        "방금 말한 내용 다시 알려주세요",
        "그렇게 하면 돼요?",
        "해당 항목은 어떻게 되나요",
        "위에서 알려준 기준으로요",
    ],
)
def test_has_anaphora_true(question: str) -> None:
    assert has_anaphora(question) is True


@pytest.mark.parametrize(
    "question",
    [
        "스케일링 산정 기준 알려주세요",
        "임플란트 보험 적용 조건",
        "초진 재진 구분 기준은 무엇인가요",
        "같은 날 임플란트 두 개 하면 어떻게 되나요",  # "같은 날" 은 앞 대화 의존이 아니다
    ],
)
def test_has_anaphora_false(question: str) -> None:
    assert has_anaphora(question) is False


# ──────────────────────────────────────────────────────────────────────────────
# 6. 되묻기 응답 종류 — 문구가 아니라 구조화된 값으로 식별한다 (검수 P1-7)
# ──────────────────────────────────────────────────────────────────────────────


def test_clarification_marker_is_structured_not_text() -> None:
    """``qa_logs.answer_kind`` 에 넣는 값이 문구와 독립이어야 한다.

    문구를 고치면 과거 되묻기 턴이 일반 대화로 되살아나던 결합(P1-7)을 끊은 결과다.
    """
    assert ANSWER_KIND_CLARIFICATION == "clarification"
    assert CLARIFY_MESSAGE  # 문구는 사용자 노출용으로만 쓰인다
    assert ANSWER_KIND_CLARIFICATION not in CLARIFY_MESSAGE


# ──────────────────────────────────────────────────────────────────────────────
# 7. 주제 없는 질문은 길이와 무관하게 되묻는다 (2026-11-04, 운영 사례 대응)
#
# 계기: 운영에서 "나는 검정색이 좋아"(3어절·주제 없음)에 챗봇이
# "검정색 봉합사를 말하는 거라면 블랙실크가…" 라고 답을 지어냈다. 3어절이라
# 기존 "2어절 이하" 기준을 한 끗 차이로 넘겼다.
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "question",
    [
        "나는 검정색이 좋아",        # 운영 실제 사례 (qa_log 20957)
        "나 지금 똥 마려워",          # 운영 실제 사례
        "예시 여러개 보내줘봐!",      # 무엇의 예시인지 앞 대화 없이는 모른다
        "오늘 날씨 어때?",
        "점심 뭐 먹을까",
    ],
)
def test_no_topic_asks_back_regardless_of_length(question: str) -> None:
    """보험청구 주제가 하나도 없으면 어절 수와 무관하게 되묻는다."""
    assert needs_clarification(question, has_known_topic=False) is True


@pytest.mark.parametrize(
    "question",
    [
        # 2026-11-04 사전 보강 전에는 아래가 전부 "주제 없음" 으로 막혔다.
        # 운영 qa_logs 최근 1,000건 실측에서 뽑은 **실제 고객 질문**이다.
        "급성치관주위염 상병명으로 항생제 처방이 가능할까?",
        "수술후지혈처치에 내역설명을 꼭 달아야 해?",
        "근단변위판막술 시 구강전정성형술",
        "동요도 적은 치아 상병명",
        "자율점검 하는방법 알려줘",
        "소염술 간단/복잡 차이점",
        "잔존유치 치근단 촬영 내역설명",
        "이가 시려서 치근단 촬영. 상병명은?",
        "1치당 아닌 1면당 산정되는것은?",
        "27년도에 바뀌는 고시",
        "치아 착색으로 인했을때 상병명 적절한것?",
        "의료법 관련 규정은 어디서 확인할수 있을까",
        "자보 혜택 받기 애매한 경우도 있을까요?",
        "페리덱스 유아한테 발라도대나",
    ],
)
def test_real_questions_are_not_blocked(question: str) -> None:
    """정상 치과 질문은 되묻기로 떨어지면 안 된다 (오탐 회귀 방지)."""
    assert needs_clarification(question, has_known_topic=False) is False


@pytest.mark.parametrize(
    "question",
    [
        "PRR 이 뭔가요",
        "엔도중에 NiTi 는 몇 번 넣을수 있지?",
        "하루 CU, RP 같이 몇회까지 가능한지",
        "CU 후 리제노머 사용 내역설명 추천",
    ],
)
def test_latin_abbreviation_counts_as_topic(question: str) -> None:
    """치과 현장 영문 약어(CU·RP·PRR·NiTi…)는 주제로 인정한다."""
    assert has_billing_topic(question) is True
    assert needs_clarification(question, has_known_topic=False) is False


@pytest.mark.parametrize(
    "question",
    [
        # 2026-11-04 운영 되묻기 오탐 (qa_log 20979). 판단 단계가 실패해도
        # 주제어로 걸러져 되묻기까지 가지 않아야 한다.
        "산소랑 아산화질소는?",
        "아산화질소 청구 가능해?",
        "행동조절 90분 산정",
    ],
)
def test_sedation_terms_are_topics(question: str) -> None:
    assert has_billing_topic(question) is True
    assert needs_clarification(question, has_known_topic=False) is False


# ──────────────────────────────────────────────────────────────────────────────
# 8. 지시어는 "있는가" 가 아니라 "어디에 있는가" 로 가른다 (2026-11-06, 게시판 #150-A)
#
# 계기: 되묻기 도입 직후 운영 반송 12건 중 9건(75%)이 오탐이었다. 고객이 같은 질문을
# 7회 던졌는데 "그럼" 한 단어 때문에 매번 반송됐다
# (qa_log 21224·21225·21226·21227·21229·21231·21241). 같은 내용을 지시어 없이
# "결핵검사 매년받아야해?" 로 바꿔 던진 21232 는 문서 5개가 정상 검색됐다.
#
# 규칙: 지시어가 **문장 첫 어절**이면 되묻고, **문장 중간**에 나오면서 **앞쪽 구간에
# 이미 보험청구 주제어가 적혀 있으면** 자립 문장으로 보고 통과시킨다.
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "question",
    [
        # 고객 실제 질문 — 7회 연속 반송된 결핵검진 건 (qa_log 21225 외)
        "결핵검진은 매년받고 있는데 그럼 대상자 리스트를 매년 작성해야되?",
        "의료인종사자 결핵검진은 매년받고 있는데 그럼 대상자 리스트를 매년 작성해야되?",
        # 고객 실제 질문 — 상악동 건 (qa_log 21215·21216·21101)
        "상악동 약처방 나갈건데 기본진료 상병에 '상악동염 NOS' 넣을건데 이건 부상병이어도 상관없지?",
        # 설계 검토 때 든 예시 — 완전히 정상적인 청구 질문
        "스케일링은 매년 되는데 그럼 치주소파술도 매년 되나요?",
        # 운영 표본에서 같은 이유로 막혀 있던 질문들
        "치관확장 청구하려고 하는데 SILKAM이랑 슈처다필론이랑 같은 거야?",
        "토요일은 그럼 평일에비해 하루종일 가산이야?",
        "임플란트를 심고 그걸로 지대치를 사용해서 부분틀니는 가능해?",
        "실손24 프로그램에서 청구하는거 있잖아. 그거 가입 안하면 안되는거야?",
    ],
)
def test_midsentence_anaphora_with_topic_in_front_is_answered(question: str) -> None:
    """지시어가 문장 중간이고 앞쪽에 주제어가 있으면 되묻지 않는다."""
    assert has_anaphora(question) is True            # 지시어는 분명히 있다
    assert needs_clarification(question, has_known_topic=False) is False


@pytest.mark.parametrize(
    "question",
    [
        # 설계 docstring 에 기록된 사례 — 절대 깨뜨리면 안 된다
        "그 경우에는 환자 본인부담금이 어떻게 달라지는 건가요?",
        # 주제어는 있지만 지시어가 문장 맨 앞 → 앞 대화 없이는 대상이 없다
        "그럼 매년 치과에서는 리스트를 작성해야해?",
        "그럼 스케일링도 같이 되나요?",
        "이건 부상병이어도 상관없지?",
        "그렇게 하면 돼요?",
    ],
)
def test_leading_anaphora_still_asks_back(question: str) -> None:
    """지시어가 문장 첫 어절이면 주제어·길이와 무관하게 되묻는다."""
    assert needs_clarification(question, has_known_topic=False) is True


@pytest.mark.parametrize(
    "question",
    [
        # 지시어 앞쪽에 보험청구 주제가 하나도 없다 → 여전히 되묻는다
        "어제 말한 그거 다시 알려줘",
        "아까 그 경우는 어떻게 돼?",
        "제가 어제 물어본 그건 어떻게 되나요",
    ],
)
def test_midsentence_anaphora_without_topic_in_front_asks_back(question: str) -> None:
    """지시어가 중간이어도 **앞쪽에 주제어가 없으면** 자립이 아니다."""
    assert needs_clarification(question, has_known_topic=False) is True


def test_first_anaphora_index_reports_position() -> None:
    """위치 판정의 기반 — 지시어가 처음 나오는 어절 번호를 돌려준다."""
    assert first_anaphora_index("그럼 어떻게 되나요") == 0
    assert first_anaphora_index("그 경우에는 본인부담금이 어떻게 되나요") == 0
    assert first_anaphora_index("결핵검진은 매년받고 있는데 그럼 리스트 작성해야되?") == 3
    assert first_anaphora_index("스케일링 산정 기준 알려주세요") is None


def test_clarification_stays_for_real_fragments() -> None:
    """실제 반송 12건 중 **정당한** 되묻기는 그대로 남아야 한다 (운영 qa_log 21230)."""
    assert needs_clarification("시발", has_known_topic=False) is True


# ──────────────────────────────────────────────────────────────────────────────
# 9. 범용어(`산정` 류)는 "수치만 묻는 질문" 분기를 무력화하지 못한다
#    (2026-11-06, 게시판 #150-B)
#
# 계기: 운영 qa_log 20969 "몇악당 산정되는거야?" 가 통과해 그대로 검색으로 넘어갔다.
# 주제어로 걸린 것은 `산정`(청구 금액·횟수를 계산한다) 하나뿐인데, 이 말은 보험청구
# 질문 거의 전부에 등장하는 범용 동사다. 주제가 있다고 판정되는 순간 "수치만 묻는
# 맥락 의존 질문" 분기(규칙 2)가 통째로 건너뛰어진다. "**무엇을** 몇악당 산정하는지"
# 가 빠진 질문이라 앞 대화 없이는 답할 수 없다.
#
# 규칙: 범용어는 규칙 3(주제가 잡히면 답한다)에서는 그대로 주제로 인정하고,
# 규칙 2(수치만 묻는 질문)에서만 주제로 세지 않는다. 사전에서 빼지 않는 이유는
# 아래 `test_sanjeong_stays_a_topic_for_self_contained_questions` 가 고정한다.
#
# 실측(운영 표본 2,953건, outputs/measure_clarify_150b.py): 되묻기 136 → 137건.
# 새로 막힌 질문은 20969 단 1건(= 목표 미탐), 새로 통과한 질문 0건.
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "question",
    [
        # 운영 미탐 본건 (qa_log 20969, 2026-11-04 10:22)
        "몇악당 산정되는거야?",
        # 같은 꼴 — 대상이 빠지고 수치·범용어만 남은 질문
        "몇악당 산정해?",
        "몇번까지 산정 가능해?",
        "몇 퍼센트 삭감돼?",
        "몇번까지 접수돼?",
    ],
)
def test_metric_only_with_generic_term_asks_back(question: str) -> None:
    """범용어 하나로는 "수치만 묻는 질문" 을 통과시킬 수 없다."""
    # 사전 자체에는 여전히 주제어로 남아 있다 (규칙 3 용도).
    assert has_billing_topic(question) is True
    # 다만 범용어를 제외하면 주제가 없다 → 규칙 2 가 살아난다.
    assert has_billing_topic(question, allow_generic=False) is False
    assert needs_clarification(question, has_known_topic=False) is True


@pytest.mark.parametrize(
    "question",
    [
        # 바로 다음 턴에 고객이 직접 고쳐 던진 완성 문장 (qa_log 20970)
        "치면세마는 몇악당 산정이야>",
        # `산정` 을 사전에서 빼면(방안 2) 전부 새로 막히던 자립 질문들.
        # 운영 표본 실측 10건 중 9건 — 이 테스트가 그 방안의 재도입을 막는다.
        "블랙실크사용시 산정불가항목",
        "블랙실크 산정가능항목",
        "러버댐 산정 기준",
        "즉충 산정기준",
        "드라이소켓 재산정기준",
        "1치당 아닌 1면당 산정되는것은?",
        "구토반사 심한 환자 리도카글 산정 기준",
        "개월초과 6개월이내 동일부위 시행하여 50%만 산정했는데 90일은 지나긴함",
    ],
)
def test_sanjeong_stays_a_topic_for_self_contained_questions(question: str) -> None:
    """`산정` 은 사전에 남아 있어야 한다 — 대상이 분명한 질문을 막으면 안 된다."""
    assert needs_clarification(question, has_known_topic=False) is False


@pytest.mark.parametrize(
    "question",
    [
        # `청구` 를 범용어에 넣었을 때(방안 3-wide) 새로 막히던 자립 질문들.
        # 사전에 없는 행위 이름(스켈링·프로빙·드라이소켓·나이타이)을 쓴 정상 질문에서
        # `청구` 가 유일한 주제 신호였다 — 그래서 `청구` 는 범용어가 아니다.
        "연1회 스켈링이랑 프로빙 동시청구 가능해?",
        "연1회 하면서 지각과민 청구 가능한가요?",
        "드라이소켓 같은달에 2번 청구 되나요",
        "엔도중 나이타이 몇번 청구가능해?",
        # `처치` 를 범용어에 넣었을 때 새로 막히던 질문 — `처치` 는 실제 행위 이름의
        # 일부다 (지각과민처치 · 보통처치 · 후처치).
        "지각과민처치 1일가능횟수",
        "지각과민처치 8개이상하루에처치시 사유",
        "지각과민처치(간단) 하루 최대 청구가능한 횟수는?",
    ],
)
def test_procedure_name_fragments_are_not_generic(question: str) -> None:
    """행위 이름의 일부가 될 수 있는 말(`청구`·`처치`)은 범용어로 취급하지 않는다."""
    assert needs_clarification(question, has_known_topic=False) is False


def test_generic_terms_never_contain_procedure_words() -> None:
    """범용어 집합에 행위 이름의 조각이 섞여 들어오는 것을 막는 가드.

    실측으로 오탐이 확인된 말들이다. 누군가 "같은 성질 같다" 며 다시 넣으면
    "지각과민처치 1일가능횟수" 류 정상 질문이 되묻기로 반송된다.
    """
    from api.src.rag_integration.question_completeness import _GENERIC_TOPIC_TERMS

    forbidden = {
        "청구", "처치", "제거", "검사", "검진", "촬영", "수술", "시술", "술식",
        "고정", "세척", "연마", "측정", "분석", "진단", "사진", "영상", "충전",
    }
    assert _GENERIC_TOPIC_TERMS & forbidden == set()
    # 반대로 본건의 원인인 `산정` 은 반드시 들어 있어야 한다.
    assert "산정" in _GENERIC_TOPIC_TERMS


# ============================================================================
# 섹션 10 — 전수 재측정에서 드러난 사전 누락 (2026-11-06, #150-B 검수)
#
# `_GENERIC_TOPIC_TERMS`(혼자서는 대상을 정하지 못하는 범용어) 도입을 표본 2,953건
# 으로만 재면 신규 오탐이 0건으로 보이지만, 운영 질문 **전수 21,393건**으로 재면
# 2건이 드러났다. 둘 다 행위 이름이 사전에 없어 `산정` 이 유일한 주제 신호였던 질문이다.
# 고칠 곳은 규칙이 아니라 사전이라는 원칙(`needs_clarification` 6) 주석)의 실례.
# ============================================================================


@pytest.mark.parametrize(
    "question",
    [
        # 운영 qa_log 실제 질문 — 전부 혼자서 뜻이 통하는 자립 질문이다.
        "프로빙 횟수산정 어떻게해",          # [635]
        "나이타이산정횟수",                  # [11180]
        "프로빙은?",                         # [7930]
        "#26,27리엔도해서 나이타이 썼는데 횟수 2번맞지?",   # [19293]
        "당일발수근충에 나이타이파일 필수인지?",            # [20667]
        "연1회 스켈링이랑 프로빙 동시청구 가능해?",
        "엔도중 나이타이 몇번 청구가능해?",
    ],
)
def test_transliterated_procedure_names_are_topics(question: str) -> None:
    """음차 행위·기구 이름(프로빙·나이타이)은 주제어로 인정해 되묻지 않는다."""
    assert needs_clarification(question, has_known_topic=False) is False


def test_metric_only_misses_still_asked_back_after_dictionary_fix() -> None:
    """사전을 보강해도 대상이 빠진 수치 질문은 계속 되묻는다 (#150-B 목표 보존).

    사전에 단어를 더하면 미탐이 되살아날 수 있으므로 함께 고정한다.
    """
    assert needs_clarification("몇악당 산정되는거야?", has_known_topic=False) is True
    assert needs_clarification("횟수가 0.5로 줄었는데 왜 그럴까?", has_known_topic=False) is True
    # 같은 뜻의 완성 문장은 통과해야 한다.
    assert needs_clarification("치면세마는 몇악당 산정이야?", has_known_topic=False) is False
