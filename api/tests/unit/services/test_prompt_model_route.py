"""특정 프롬프트 모델 라우팅(복수 지정) 단위 테스트.

검증 대상:
  1. ``build_prompt_with_overrides_detailed`` 의 "실제 주입된 블록 목록" 정확성
     (키워드만 포함 / 블록 꺼짐 / 상호배제 탈락 케이스 구분)
  2. ``normalize_prompt_model_routes`` fail-safe (손상값 폐기 · 구버전 단일형 승격 · 중복 제거)
  3. ``resolve_effective_chat_model`` 모델 선택 + 우선순위 (추가 API 호출 없는 순수 함수)
"""

from __future__ import annotations

import pytest

from api.src.rag_integration.prompt_injection import (
    PromptOverride,
    build_prompt_with_overrides,
    build_prompt_with_overrides_detailed,
)
from api.src.services.runtime_config_service import (
    ALLOWED_CHAT_MODELS,
    normalize_prompt_model_routes,
    resolve_effective_chat_model,
)

BASE_MODEL = "gpt-5.4-mini"
ROUTE_MODEL = "gpt-5.4"
OTHER_MODEL = "gpt-6-luna"
# 브릿지 블록이 실제로 발동하는 질문 / 발동하지 않는 질문.
BRIDGE_QUERY = "브릿지 산정 어떻게 하나요"
PLAIN_QUERY = "초진 재진 구분 알려주세요"


def _file_overrides() -> dict[str, PromptOverride]:
    """DB 시드와 동일한 오버라이드(파일 내용 + 파일 발동조건) 전체 블록."""
    from rag.prompt_builder import BASE_PROMPT, PROMPT_MODULES  # type: ignore[import-untyped]

    from api.src.rag_integration.prompt_injection import _file_trigger_config

    overrides: dict[str, PromptOverride] = {
        "BASE": PromptOverride(
            content=BASE_PROMPT, enabled=True, trigger_config={"mode": "base"}
        )
    }
    for block_id, module in PROMPT_MODULES.items():
        overrides[block_id] = PromptOverride(
            content=module["text"],
            enabled=True,
            trigger_config=_file_trigger_config(block_id, module),
        )
    return overrides


def _route(block_id: str, model: str, enabled: bool = True) -> dict:
    return {"block_id": block_id, "model": model, "enabled": enabled}


# ──────────────────────────────────────────────────────────────────────────────
# 1. 주입 목록 정확성
# ──────────────────────────────────────────────────────────────────────────────


def test_detailed_returns_same_prompt_as_legacy_wrapper() -> None:
    """기존 시그니처(문자열 반환)와 detailed 의 프롬프트 문자열이 동일해야 한다."""
    overrides = _file_overrides()
    text, _ = build_prompt_with_overrides_detailed(BRIDGE_QUERY, overrides)
    assert text == build_prompt_with_overrides(BRIDGE_QUERY, overrides)


def test_injected_contains_matched_block() -> None:
    _, injected = build_prompt_with_overrides_detailed(BRIDGE_QUERY, _file_overrides())
    assert "브릿지" in injected


def test_injected_excludes_base() -> None:
    """BASE 는 항상 선주입되는 고정 블록 — 주입 목록에는 들어가지 않는다."""
    _, injected = build_prompt_with_overrides_detailed(PLAIN_QUERY, _file_overrides())
    assert "BASE" not in injected


def test_injected_empty_for_unmatched_query() -> None:
    _, injected = build_prompt_with_overrides_detailed(
        "오늘 날씨 어때요", _file_overrides()
    )
    assert injected == []


def test_disabled_block_not_injected_even_if_keyword_present() -> None:
    """키워드가 포함돼도 블록이 꺼져 있으면 주입되지 않는다 → 기본 모델 유지."""
    overrides = _file_overrides()
    overrides["브릿지"] = PromptOverride(
        content=overrides["브릿지"].content,
        enabled=False,
        trigger_config=overrides["브릿지"].trigger_config,
    )
    _, injected = build_prompt_with_overrides_detailed(BRIDGE_QUERY, overrides)
    assert "브릿지" not in injected


def test_suppressed_block_not_injected() -> None:
    """상호배제로 탈락한 블록은 주입 목록에서 빠진다(브릿지 → 치식_위치 배제)."""
    _, injected = build_prompt_with_overrides_detailed(
        "브릿지 치식 위치 산정", _file_overrides()
    )
    assert "브릿지" in injected
    assert "치식_위치" not in injected


def test_fallback_without_overrides_returns_empty_injected() -> None:
    """vendor 폴백 경로는 주입 목록을 알 수 없으므로 빈 목록(= 기본 모델)."""
    _, injected = build_prompt_with_overrides_detailed(BRIDGE_QUERY, None)
    assert injected == []


# ──────────────────────────────────────────────────────────────────────────────
# 2. normalize_prompt_model_routes — fail-safe
# ──────────────────────────────────────────────────────────────────────────────


def test_normalize_none_is_empty() -> None:
    assert normalize_prompt_model_routes(None) == []


def test_normalize_routes_object() -> None:
    raw = (
        '{"routes": [{"block_id": "브릿지", "model": "%s", "enabled": true},'
        ' {"block_id": "마취_산정", "model": "%s", "enabled": false}]}'
        % (ROUTE_MODEL, OTHER_MODEL)
    )
    assert normalize_prompt_model_routes(raw) == [
        _route("브릿지", ROUTE_MODEL, True),
        _route("마취_산정", OTHER_MODEL, False),
    ]


def test_normalize_bare_list() -> None:
    routes = normalize_prompt_model_routes(
        [{"block_id": "브릿지", "model": ROUTE_MODEL}]
    )
    assert routes == [_route("브릿지", ROUTE_MODEL, True)]


def test_normalize_legacy_single_object_is_promoted() -> None:
    """단일 지정 구버전 저장값은 1건짜리 목록으로 자동 승격된다."""
    routes = normalize_prompt_model_routes(
        {"enabled": True, "block_id": "브릿지", "model": ROUTE_MODEL}
    )
    assert routes == [_route("브릿지", ROUTE_MODEL, True)]


def test_normalize_preserves_order() -> None:
    """목록 순서 = 우선순위이므로 정규화가 순서를 바꾸면 안 된다."""
    routes = normalize_prompt_model_routes(
        {
            "routes": [
                {"block_id": "마취_산정", "model": OTHER_MODEL},
                {"block_id": "브릿지", "model": ROUTE_MODEL},
            ]
        }
    )
    assert [r["block_id"] for r in routes] == ["마취_산정", "브릿지"]


def test_normalize_drops_duplicate_block_keeping_first() -> None:
    routes = normalize_prompt_model_routes(
        {
            "routes": [
                {"block_id": "브릿지", "model": ROUTE_MODEL},
                {"block_id": "브릿지", "model": OTHER_MODEL},
            ]
        }
    )
    assert routes == [_route("브릿지", ROUTE_MODEL, True)]


@pytest.mark.parametrize(
    "bad",
    [
        {"block_id": "", "model": "gpt-5.4"},
        {"block_id": "BASE", "model": "gpt-5.4"},
        {"block_id": "브릿지", "model": "허용안된모델"},
        {"block_id": "브릿지"},
        "문자열항목",
        None,
    ],
)
def test_normalize_drops_bad_entries_but_keeps_good_ones(bad: object) -> None:
    """못 쓰는 지정만 버리고 나머지는 살린다 — 전체가 날아가면 안 된다."""
    routes = normalize_prompt_model_routes(
        {"routes": [bad, {"block_id": "마취_산정", "model": OTHER_MODEL}]}
    )
    assert routes == [_route("마취_산정", OTHER_MODEL, True)]


@pytest.mark.parametrize("raw", ["not-json", "123", '{"foo": 1}'])
def test_normalize_corrupt_value_is_empty(raw: str) -> None:
    assert normalize_prompt_model_routes(raw) == []


# ──────────────────────────────────────────────────────────────────────────────
# 3. resolve_effective_chat_model — 선택 + 우선순위
# ──────────────────────────────────────────────────────────────────────────────

ROUTES = [_route("브릿지", ROUTE_MODEL), _route("마취_산정", OTHER_MODEL)]


def test_resolve_uses_route_model_when_block_injected() -> None:
    assert resolve_effective_chat_model(BASE_MODEL, ROUTES, ["브릿지"]) == ROUTE_MODEL


def test_resolve_matches_second_entry_too() -> None:
    """목록 아래쪽 지정도 당연히 걸린다."""
    assert (
        resolve_effective_chat_model(BASE_MODEL, ROUTES, ["마취_산정"]) == OTHER_MODEL
    )


def test_resolve_first_entry_wins_when_both_injected() -> None:
    """두 지정이 동시에 주입되면 목록 앞쪽이 이긴다(우선순위 규칙)."""
    assert (
        resolve_effective_chat_model(BASE_MODEL, ROUTES, ["마취_산정", "브릿지"])
        == ROUTE_MODEL
    )


def test_resolve_priority_follows_list_order_not_injection_order() -> None:
    """우선순위는 주입 순서가 아니라 관리자가 정한 목록 순서를 따른다."""
    reordered = [_route("마취_산정", OTHER_MODEL), _route("브릿지", ROUTE_MODEL)]
    assert (
        resolve_effective_chat_model(BASE_MODEL, reordered, ["브릿지", "마취_산정"])
        == OTHER_MODEL
    )


def test_resolve_skips_disabled_entry_and_falls_to_next() -> None:
    routes = [_route("브릿지", ROUTE_MODEL, enabled=False), _route("마취_산정", OTHER_MODEL)]
    assert (
        resolve_effective_chat_model(BASE_MODEL, routes, ["브릿지", "마취_산정"])
        == OTHER_MODEL
    )


def test_resolve_uses_base_when_only_disabled_entry_matches() -> None:
    routes = [_route("브릿지", ROUTE_MODEL, enabled=False)]
    assert resolve_effective_chat_model(BASE_MODEL, routes, ["브릿지"]) == BASE_MODEL


def test_resolve_uses_base_when_other_block_injected() -> None:
    assert resolve_effective_chat_model(BASE_MODEL, ROUTES, ["치식_위치"]) == BASE_MODEL


def test_resolve_uses_base_when_nothing_injected() -> None:
    assert resolve_effective_chat_model(BASE_MODEL, ROUTES, []) == BASE_MODEL


def test_resolve_uses_base_when_no_routes() -> None:
    assert resolve_effective_chat_model(BASE_MODEL, [], ["브릿지"]) == BASE_MODEL
    assert resolve_effective_chat_model(BASE_MODEL, None, ["브릿지"]) == BASE_MODEL


def test_route_models_are_whitelisted() -> None:
    assert ROUTE_MODEL in ALLOWED_CHAT_MODELS
    assert OTHER_MODEL in ALLOWED_CHAT_MODELS
    assert BASE_MODEL in ALLOWED_CHAT_MODELS
