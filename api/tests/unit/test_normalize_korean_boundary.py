"""멀티워드 동의어 치환의 한글 앞 경계 회귀 테스트 (2026-11-04).

## 사고 내용

운영 질문 "비보험 스켈링 후 치주소파술 청구 가능" 이 검색 단계에서
"비 연1회치석제거 후 치주소파술 청구 가능" 으로 치환됐다.
**비급여(보험 안 됨)를 연1회치석제거(보험 적용)로 뜻을 정반대로 뒤집은** 것이라
틀린 청구 기준이 안내될 수 있었다.

## 원인

파이프라인은 ``apply_scaling_rules`` → ``normalize_query`` 순서다.

1. ``apply_scaling_rules`` 는 ``(?<!비)(보험|급여)\\s*SC`` 보호가 있어
   "비보험 스켈링" 을 "비보험 치석제거" 로 **올바르게** 남긴다 (게시판 #136 에서 넣은 보호).
2. 그런데 ``normalize_query`` 의 PHASE 2(멀티워드 동의어)에 경계 검사가 없어서,
   DB 동의어 "보험 치석제거"(= 연1회치석제거)가 "비**보험 치석제거**" 안에 부분
   매칭돼 앞 단계의 보호를 **무력화**했다.

#136 은 같은 성격의 버그를 **영문** 경계로 막았는데, 한글 멀티워드에는 경계가 없어
같은 유형이 다시 난 것이다.

## 경계를 어디까지 막을 것인가 — 한 번 과하게 잡았다가 좁혔다

처음에는 한글 전체를 막았다(``(?<![가-힣])``). 그랬더니 운영 질문 2,000건에서
**막히면 안 되는 것 3건이 함께 막혔다** — "전악보험 치석제거", "임플란트크라운 제거",
"골드크라운 제거". 앞 글자(악·트·드)는 단순 수식어라 치환돼야 한다.

뜻을 뒤집는 것은 **부정 접두사뿐**이므로 ``(?<!비)`` 로 좁혔다. 기존 vendor 룰
``(?<!비)(보험|급여) SC``(#136)와 같은 방식이다. 좁힌 뒤 운영 질문 1,000건으로
재측정했을 때 **결과가 달라지는 질문 0건** — 회귀가 없음을 확인했다.
뒤는 조사("보험 치석제거는")가 붙으므로 열어 둔다.
"""
from __future__ import annotations

import pytest

from rag.run_qa import apply_scaling_rules, normalize_query

# 운영 동의어 사전(2026-11-04)에서 이 사건에 관련된 그룹만 그대로 가져왔다.
SYN = {
    "치석제거": ["스케일링", "s.c", "scaling", "s/c", "sc", "스켈링"],
    "2차치석제거": ["2차스케일링"],
    "비급여": ["비보", "비보험"],
    "연1회치석제거": [
        "연1회", "치석제거(나)", "치석제거 나",
        "보험스켈링", "보험 스켈링", "보험스케일링", "보험 스케일링", "보험 치석제거",
    ],
}


def _run(question: str) -> str:
    return normalize_query(apply_scaling_rules(question), SYN)


@pytest.mark.parametrize(
    "question",
    [
        "비보험 스켈링 후 치주소파술 청구 가능",   # 운영 실제 사고 질문 (qa_log 21002)
        "비보험 스케일링 후 치주소파술 청구 가능",
        "비보험 치석제거",
    ],
)
def test_non_covered_scaling_is_not_turned_into_covered(question: str) -> None:
    """"비보험" 이 "비" + "보험~" 으로 쪼개져 보험 항목으로 뒤집히면 안 된다."""
    out = _run(question)
    assert "연1회치석제거" not in out, out   # 보험 적용 항목으로 뒤집힘 = 사고
    assert "비급여 치석제거" in out, out      # 비급여로 정규화되는 것이 올바른 결과


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        # 앞에 한글이 없으면 멀티워드 동의어는 그대로 동작해야 한다 (비퇴행).
        ("보험 스켈링 후 치주소파술 청구 가능", "연1회치석제거"),
        ("보험 치석제거 산정 기준", "연1회치석제거"),
        ("보험 스켈링은 몇 번까지?", "연1회치석제거"),   # 뒤 조사는 막지 않는다
        # 다른 경로(vendor 룰)로 처리되는 표현들도 그대로여야 한다.
        ("비급여 스켈링 청구", "비급여 치석제거"),
        ("치주 스켈링", "치주치석제거"),
    ],
)
def test_multiword_synonym_still_applies(question: str, expected: str) -> None:
    assert expected in _run(question), _run(question)


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        # 한글 전체를 막았을 때 과잉 차단됐던 실제 운영 질문들.
        # 앞 글자가 부정 접두사가 아니면 치환이 살아 있어야 한다.
        ("전악보험 치석제거 시행시 처방전 발급 가능한가요", "연1회치석제거"),
        ("보험 치석제거 후 처방", "연1회치석제거"),
    ],
)
def test_modifier_prefix_does_not_block(question: str, expected: str) -> None:
    """수식어(전악·임플란트 등)가 앞에 붙어도 멀티워드 동의어는 치환돼야 한다."""
    assert expected in _run(question), _run(question)
