"""OpenAI 채팅 모델 선택과 비용 계산 유닛 테스트.

2026-10-28: 단가표를 client 모듈의 보정표에서 runtime_config_service.CHAT_MODEL_CATALOG
(단일 출처)로 옮겼다. 관리자 화면에 보여주는 가격과 qa_logs.cost_usd 단가가 같은 표를 쓴다.
"""

import pytest

from api.src.integrations.openai.client import (
    DEFAULT_CHAT_MODEL,
    _is_reasoning_model,
)
from api.src.services.runtime_config_service import (
    ALLOWED_CHAT_MODELS,
    CHAT_MODEL_CATALOG,
    CHAT_MODEL_PRICES_PER_MTOK,
    estimate_cost_usd,
    get_chat_model_spec,
)

# OpenAI 가 서비스를 종료했거나 세대가 지나 내린 모델 — 다시 들어오면 안 된다.
RETIRED_MODELS = ("gpt-4-turbo", "o4-mini", "gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo")


def test_gpt_5_4_mini_is_default_allowed_reasoning_model():
    assert DEFAULT_CHAT_MODEL == "gpt-5.4-mini"
    assert "gpt-5.4-mini" in ALLOWED_CHAT_MODELS
    assert "gpt-5.4" in ALLOWED_CHAT_MODELS
    assert "gpt-6-luna" in ALLOWED_CHAT_MODELS
    assert "o4-mini" not in ALLOWED_CHAT_MODELS
    assert _is_reasoning_model("gpt-5.4-mini") is True


@pytest.mark.parametrize("model_id", RETIRED_MODELS)
def test_retired_models_are_not_selectable(model_id: str):
    """단종·구세대 모델은 선택 목록에 없어야 한다 (gpt-4-turbo 는 2026-10-23 서비스 종료)."""
    assert model_id not in ALLOWED_CHAT_MODELS


def test_selected_models_have_prices_for_budget_tracking():
    """예산 집계가 0원으로 새지 않도록, 선택 가능한 모든 모델에 단가가 있어야 한다."""
    for model_id in ALLOWED_CHAT_MODELS:
        assert model_id in CHAT_MODEL_PRICES_PER_MTOK
        input_price, output_price = CHAT_MODEL_PRICES_PER_MTOK[model_id]
        assert input_price > 0
        assert output_price > 0


def test_known_model_prices_match_openai_list():
    assert CHAT_MODEL_PRICES_PER_MTOK["gpt-5.4-mini"] == (0.75, 4.50)
    assert CHAT_MODEL_PRICES_PER_MTOK["gpt-5.4"] == (2.50, 15.00)
    assert CHAT_MODEL_PRICES_PER_MTOK["gpt-6-luna"] == (0.10, 0.50)


def test_catalog_is_ordered_by_output_price():
    """드롭다운이 '싼 것 → 비싼 것' 순으로 보이도록 카탈로그 순서를 고정한다."""
    prices = [m.output_usd_per_mtok for m in CHAT_MODEL_CATALOG]
    assert prices == sorted(prices)


def test_catalog_entries_are_unique_and_described():
    ids = [m.model_id for m in CHAT_MODEL_CATALOG]
    assert len(ids) == len(set(ids))
    for m in CHAT_MODEL_CATALOG:
        assert m.label and m.tier and m.speed and m.quality and m.note


def test_estimate_cost_changes_with_model():
    """모델을 바꾸면 같은 토큰 수라도 비용이 달라져야 한다."""
    cheap = estimate_cost_usd("gpt-6-luna", 1_000_000, 1_000_000)
    base = estimate_cost_usd("gpt-5.4-mini", 1_000_000, 1_000_000)
    pricey = estimate_cost_usd("gpt-5.4", 1_000_000, 1_000_000)
    assert cheap == pytest.approx(0.10 + 0.50)
    assert base == pytest.approx(0.75 + 4.50)
    assert pricey == pytest.approx(2.50 + 15.00)
    assert cheap < base < pricey


def test_estimate_cost_unknown_model_returns_none():
    """카탈로그에 없는 모델은 계산하지 않고 None → LangChain 추정치를 그대로 둔다."""
    assert estimate_cost_usd("gpt-4-turbo", 1000, 1000) is None


def test_get_chat_model_spec():
    spec = get_chat_model_spec("gpt-5.4-mini")
    assert spec is not None
    assert spec.input_usd_per_mtok == 0.75
    assert get_chat_model_spec("없는모델") is None
