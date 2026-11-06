"""조사 "에도" 분리 회귀 테스트 (2026-11-06).

## 무엇이 문제였나

``vendor/rag/run_qa/run_qa.py`` 의 ``JOSA``(토큰 끝에서 떼어낼 조사 목록)에
복합 조사 "에서도"·"으로도"·"이랑도" 는 있는데 **가장 기본형인 "에"+"도" 가
빠져 있었다.**

그래서 "뿌리에도" 는 통째로 한 덩어리로 남아 동의어 치환이 **아예 되지 않았다.**
비교하면 "뿌리밖에" 는 "밖에" 가 목록에 있어 "치근밖에" 로 정상 치환됐다.
즉 같은 자리의 조사인데 하나만 빠져 있어 치환이 갈렸다.

## 왜 테스트로 못 박아 두는가

``vendor/rag`` 는 인수자(고객) 제공 자산이라 클라이언트 최신본을 다시 받아
덮어쓰는 일이 있다. 그때 이 한 줄이 조용히 사라져도 아무 에러가 나지 않고
검색 품질만 조금 떨어진다 — 그래서 테스트로 고정한다.

## 적용 근거

운영 질문 21,294건 전수 회귀에서 결과가 달라진 질문은 4건이고 전부 개선 방향,
퇴화 0건이었다.

* "뿌리에도 문제가없어" → "치근에도 문제가없어" (3건, 동일 질문 중복 기록)
* "유치신경치료에도 사용해도될까?" → "유치근관치료에도 사용해도될까?" (1건)
"""
from __future__ import annotations

import pytest

from rag.run_qa import apply_scaling_rules, normalize_query
# JOSA 는 패키지 __init__ 에서 노출하지 않으므로(vendor 파일을 건드리지 않기 위해)
# 모듈에서 직접 가져온다.
from rag.run_qa.run_qa import JOSA

# 운영 동의어 사전(2026-11-06)에서 이 건에 관련된 그룹만 그대로 가져왔다.
SYN = {
    "치근": ["root", "뿌리", "루트", "치아뿌리", "뿌리부분"],
    "근관치료": ["신경치료", "endo", "엔도", "펄팩토미", "펄펙토미"],
}


def _run(question: str) -> str:
    return normalize_query(apply_scaling_rules(question), SYN)


def test_josa_list_contains_edo() -> None:
    """"에도" 가 JOSA 에 남아 있어야 한다 (vendor 재동기화 시 유실 방지)."""
    assert "에도" in JOSA


def test_josa_list_is_sorted_longest_first() -> None:
    """긴 조사가 짧은 조사보다 먼저 매칭되도록 길이 역순 정렬이 유지돼야 한다.

    이게 깨지면 "뿌리에도" 가 1글자 "도" 로 먼저 쪼개져 "뿌리에" 가 남고
    치환이 다시 실패한다.
    """
    lengths = [len(j) for j in JOSA]
    assert lengths == sorted(lengths, reverse=True), JOSA
    assert JOSA.index("에도") < JOSA.index("도")


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        # 운영 실제 질문 (qa_logs)
        ("우식이없는치아 엑스레이찍었는데 뿌리에도 문제가없어 상병명뭐라고해야해", "치근에도"),
        ("유치신경치료에도 사용해도될까?", "유치근관치료에도"),
        # 같은 자리의 다른 조사들 — 원래 되던 것이 계속 돼야 한다 (비퇴행)
        ("뿌리밖에 안남았어", "치근밖에"),
        ("뿌리에서도 염증", "치근에서도"),
        # 조사는 떼었다가 그대로 다시 붙인다 — 은/는 맞춤법 교정은 하지 않는다("치근는").
        ("뿌리는 괜찮아", "치근는"),
    ],
)
def test_edo_is_split_and_synonym_applies(question: str, expected: str) -> None:
    assert expected in _run(question), _run(question)


@pytest.mark.parametrize(
    "question",
    [
        # 동의어가 아닌 평범한 단어는 "에도" 를 떼어도 바뀔 것이 없다.
        "오늘에도 청구 가능해?",
        "내역설명에도 적어야해?",
    ],
)
def test_edo_does_not_change_non_synonym_tokens(question: str) -> None:
    """조사만 추가됐을 뿐이므로 동의어가 아닌 토큰은 그대로여야 한다."""
    out = _run(question)
    base = question.split()[0]
    assert base in out, out
