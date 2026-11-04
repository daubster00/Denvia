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
