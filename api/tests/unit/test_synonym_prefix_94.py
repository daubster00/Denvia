"""#94 — 접두-기호형 동의어 sanitize 회귀 테스트.

g.inlay 처럼 평문 동의어(inlay)의 접두-기호형은 vendor 동의어 직접치환이
접두("g.")를 삼키므로, 런타임 dict 빌드 시 제거되어 접두가 보존돼야 한다.
정당한 기호 동의어(c/f, p/e)는 유지돼야 한다(비퇴행).
"""
from api.src.services.synonym_service import _sanitize_group_synonyms


def test_drops_prefixed_symbol_form_when_plain_tail_exists():
    # 티켓 케이스: g.inlay 는 평문 inlay 가 있으므로 런타임 dict에서 제외
    assert _sanitize_group_synonyms(["inray", "inlay", "g.inlay"]) == [
        "inray",
        "inlay",
    ]


def test_keeps_legit_symbol_synonyms():
    # c/f, p/e 는 tail(f, e)이 평문 동의어와 불일치 → 유지(비퇴행)
    assert _sanitize_group_synonyms(["cf", "c/f"]) == ["cf", "c/f"]
    assert _sanitize_group_synonyms(["pe", "p/e"]) == ["pe", "p/e"]


def test_keeps_prefixed_when_no_plain_tail():
    # 보존 기준이 되는 평문 tail이 없으면 유지
    assert _sanitize_group_synonyms(["g.inlay"]) == ["g.inlay"]


def test_case_insensitive_tail_match():
    assert _sanitize_group_synonyms(["inlay", "G.Inlay"]) == ["inlay"]


def test_no_symbol_list_unchanged():
    assert _sanitize_group_synonyms(["a", "b", "c"]) == ["a", "b", "c"]
