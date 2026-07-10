"""#129 동치성 검증 — 신규 5개 모듈을 DB 시드값으로 오버라이드해도
프롬프트 조립 결과가 '지금(파일 폴백)'과 동일해야 한다.

핵심 안전 속성:
  build_prompt_with_overrides(q, 코어5_오버라이드)  ==  build_prompt_with_overrides(q, 전체10_오버라이드)
즉, DB 로 외부화한 신규 5개 모듈(content·trigger_config)이 vendor 파일값과
byte 단위로 동일하므로, 편집 전에는 라이브 동작이 전혀 바뀌지 않는다.

또한 비-보험레진 질의는 vendor build_prompt_template 과도 완전 일치함을 확인한다.
(보험레진 활성 질의는 기존 prompt_injection 이 vendor 와 선점 편차가 있어 별도 처리 — #129 범위 밖.)
"""
from __future__ import annotations

import pytest

from api.src.rag_integration.prompt_injection import (
    PromptOverride,
    _file_trigger_config,
    build_prompt_with_overrides,
)

# vendor 파일 (docker 컨테이너 안에서 import 가능)
from rag.prompt_builder import BASE_PROMPT, PROMPT_MODULES, build_prompt_template  # noqa: E402

CORE = ["BASE", "치식_위치", "치면_방향", "마취_산정", "브릿지"]
ALL = ["BASE"] + list(PROMPT_MODULES.keys())

# 보험레진 활성 질의 — 기존 prompt_injection 이 vendor 와 선점 편차가 있어 vendor 비교에서 제외.
RESIN_QUERY = "전치부 근심 와동 몇 급 레진"

QUERIES = [
    "#16 브릿지 x x 13 제거 횟수",   # 브릿지 → 치식/치면 배제
    "치석제거 횟수 산정",             # 치주치료 combo
    "치주낭측정검사 몇 회",           # 치주낭 combo
    "침윤마취 횟수",                  # 마취 → 치식/치면 배제
    RESIN_QUERY,                      # 보험레진 combo (배제 없음)
    "임플란트 치근면처치술 청구",     # 임플란트 combo
    "초진 재진 30일",                # 초진,재진 keywords
    "#14 치식 위치는",               # 치식_위치 only
    "보험 임플란트 취소",            # 매칭 모듈 없음
]


def _override_for(block_id: str) -> PromptOverride:
    """DB 시드와 동일한 오버라이드 = content(파일 text) + trigger_config(파일 기준)."""
    if block_id == "BASE":
        return PromptOverride(
            content=BASE_PROMPT, enabled=True, trigger_config={"mode": "base"}
        )
    module = PROMPT_MODULES[block_id]
    return PromptOverride(
        content=module["text"],
        enabled=True,
        trigger_config=_file_trigger_config(block_id, module),
    )


@pytest.mark.parametrize("query", QUERIES)
def test_seeding_new_modules_is_behavior_neutral(query: str) -> None:
    """코어5만 오버라이드(신규5는 파일 폴백) == 전체10 오버라이드(신규5도 DB 시드값)."""
    core_only = {b: _override_for(b) for b in CORE}
    all_ten = {b: _override_for(b) for b in ALL}

    result_core = build_prompt_with_overrides(query, core_only)
    result_all = build_prompt_with_overrides(query, all_ten)

    assert result_core == result_all, f"신규 5개 DB 시드가 조립 결과를 바꿈: {query!r}"


@pytest.mark.parametrize("query", [q for q in QUERIES if q != RESIN_QUERY])
def test_matches_vendor_for_non_resin_queries(query: str) -> None:
    """비-보험레진 질의는 전체10 오버라이드 결과가 vendor 원본과 완전 일치."""
    all_ten = {b: _override_for(b) for b in ALL}
    assert build_prompt_with_overrides(query, all_ten) == build_prompt_template(query)


def test_resin_divergence_is_preexisting_and_stable() -> None:
    """보험레진 질의: vendor 는 치면_방향을 배제하지만 라이브 엔진은 배제하지 않음(선점 편차).

    #129 로 신규 도입된 것이 아니라 기존 prompt_injection 부터 있던 편차임을 고정.
    """
    all_ten = {b: _override_for(b) for b in ALL}
    engine_out = build_prompt_with_overrides(RESIN_QUERY, all_ten)
    vendor_out = build_prompt_template(RESIN_QUERY)
    # 라이브 엔진은 치면_방향을 주입, vendor 는 미주입 → 서로 달라야 정상.
    assert engine_out != vendor_out
    assert "치아의 치면 및 방향" in engine_out
    assert "치아의 치면 및 방향" not in vendor_out
