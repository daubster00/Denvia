"""#145 — 지식 재구축(임베딩) 토큰 계산·비용 환산 단위 테스트.

배경: 관리자 화면의 지출이 챗봇 대화(qa_logs)만 합산해 실제 OpenAI 청구액과
달랐다. 원인은 임베딩 호출이 langchain get_openai_callback 에 안 잡혀 재구축
비용이 아예 기록되지 않은 것. 토큰은 OpenAI 에 추가 호출 없이 tiktoken 으로 센다.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from api.src.services.embedding_cost import (
    EMBEDDING_ENCODING,
    EMBEDDING_MODEL,
    EMBEDDING_USD_PER_1M_TOKENS,
    count_tokens,
    embedding_cost_usd,
)

# ── 상수 (모델·단가가 바뀌면 여기부터 깨져야 한다) ────────────────────────────

def test_model_and_price_constants():
    # vendor/rag/update_vectorstore 가 쓰는 모델과 반드시 일치해야 한다.
    assert EMBEDDING_MODEL == "text-embedding-3-large"
    assert EMBEDDING_ENCODING == "cl100k_base"
    assert EMBEDDING_USD_PER_1M_TOKENS == Decimal("0.13")


def test_vendor_uses_the_same_embedding_model():
    """상수가 실제 재구축 코드의 모델명과 어긋나면 비용이 틀어지므로 소스로 확인."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[4] / (
        "vendor/rag/update_vectorstore/update_vectorstore.py"
    )
    text = src.read_text(encoding="utf-8")
    assert f'OpenAIEmbeddings(model="{EMBEDDING_MODEL}")' in text


# ── 토큰 계산 ────────────────────────────────────────────────────────────────

def test_count_tokens_matches_tiktoken_directly():
    import tiktoken

    enc = tiktoken.get_encoding(EMBEDDING_ENCODING)
    texts = ["치과 보험청구 안내", "스케일링 급여 기준\n본인부담금"]
    expected = sum(len(enc.encode(t)) for t in texts)

    total, is_approx = count_tokens(texts)
    assert is_approx is False
    assert total == expected


def test_count_tokens_is_sum_over_documents():
    a, _ = count_tokens(["가나다"])
    b, _ = count_tokens(["라마바사"])
    both, _ = count_tokens(["가나다", "라마바사"])
    assert both == a + b


def test_count_tokens_empty_is_zero():
    assert count_tokens([]) == (0, False)


def test_count_tokens_accepts_generator():
    """워커는 제너레이터(d.page_content for d in docs)를 넘긴다."""
    total, _ = count_tokens(t for t in ["보험청구", "청구반송"])
    assert total > 0


def test_count_tokens_does_not_blow_up_on_special_token_text():
    """지식 문서에 <|endoftext|> 같은 문자열이 있어도 예외 없이 세어야 한다."""
    total, is_approx = count_tokens(["<|endoftext|> 치과"])
    assert is_approx is False
    assert total > 0


# ── 비용 환산 ────────────────────────────────────────────────────────────────

def test_cost_of_one_million_tokens_is_the_unit_price():
    assert embedding_cost_usd(1_000_000) == Decimal("0.130000")


def test_cost_is_linear():
    assert embedding_cost_usd(2_000_000) == Decimal("0.260000")
    assert embedding_cost_usd(500_000) == Decimal("0.065000")


@pytest.mark.parametrize("tokens", [0, -1])
def test_cost_of_non_positive_tokens_is_zero(tokens: int):
    assert embedding_cost_usd(tokens) == Decimal("0.000000")


def test_cost_quantized_to_six_decimals():
    """qa_logs.cost_usd 와 같은 정밀도(소수점 6자리)로 반올림된다."""
    cost = embedding_cost_usd(1)
    assert cost.as_tuple().exponent == -6
    assert cost == Decimal("0.000000")  # 0.00000013 → 6자리 반올림 시 0


def test_cost_fits_numeric_12_6_column():
    """rebuild_jobs.embedding_cost_usd 는 numeric(12,6) — 자릿수를 넘지 않아야 한다."""
    # 1억 토큰(현실적 상한을 크게 웃도는 값)이어도 $13 수준.
    cost = embedding_cost_usd(100_000_000)
    assert cost == Decimal("13.000000")
    digits = len(cost.as_tuple().digits)
    assert digits <= 12


def test_realistic_single_rebuild_cost_range():
    """진단 근거 재현 — 재구축 1회는 센트 단위(수백 원)여야 한다."""
    # 5,296조각 × 조각당 약 300토큰 ≈ 1.6M 토큰
    cost = embedding_cost_usd(1_588_800)
    assert Decimal("0.1") < cost < Decimal("0.5")
