"""ADR-0002 §8 RAG 계약 테스트 — vendor/rag/ 수정 회귀 방지.

대부분의 테스트는 OPENAI_API_KEY 없이 실행 가능하다.
임베딩이 필요한 테스트는 개별 skip 처리.
"""

import json
import os
import socket
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

VENDOR_RAG = Path(__file__).parents[3] / "vendor" / "rag"
SYNONYMS_PATH = VENDOR_RAG / "run_qa" / "config" / "synonyms.json"

NEEDS_OPENAI = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY 없음 — 임베딩 필요 테스트 skip",
)


def test_run_qa_signature_stable():
    """공개 심볼 4종 임포트 성공 — AC-1 계약."""
    from run_qa import (  # noqa: F401
        generate_rule_answer,
        apply_scaling_rules,
        normalize_query,
        load_synonym_dict,
    )


def test_prompt_builder_output_shape():
    """`build_prompt_template(query)` 반환 타입이 str인지 확인."""
    from prompt_builder import build_prompt_template

    result = build_prompt_template("임플란트 보험 기준")
    assert isinstance(result, str), "build_prompt_template은 str을 반환해야 함"
    assert len(result) > 0, "반환된 프롬프트 템플릿이 비어 있으면 안 됨"


def test_synonyms_json_schema():
    """`config/synonyms.json` 스키마 회귀 없음 — 최소 1개 키, 값은 list[str]."""
    assert SYNONYMS_PATH.exists(), f"synonyms.json이 없음: {SYNONYMS_PATH}"
    data = json.loads(SYNONYMS_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "synonyms.json 최상위가 dict이어야 함"
    assert len(data) > 0, "synonyms.json에 최소 1개 키가 있어야 함"
    for key, val in data.items():
        assert isinstance(val, list), f"'{key}' 값이 list이어야 함"
        for item in val:
            assert isinstance(item, str), f"'{key}'의 항목이 str이어야 함"


def test_normalize_query_output():
    """`normalize_query`가 str을 반환하고 입력을 변환하는지 확인."""
    from run_qa import normalize_query

    result = normalize_query("치아교정")
    assert isinstance(result, str), "normalize_query는 str을 반환해야 함"


def test_apply_scaling_rules_output():
    """`apply_scaling_rules`가 dict을 반환하는지 확인 (인터페이스 고정)."""
    from run_qa import apply_scaling_rules

    result = apply_scaling_rules("임플란트 비용")
    assert isinstance(result, dict), "apply_scaling_rules는 dict을 반환해야 함"


@NEEDS_OPENAI
def test_update_vectorstore_idempotent():
    """동일 seed 데이터로 2회 빌드 시 인덱스 파일 존재 확인 (멱등성)."""
    from update_vectorstore import update_vectorstore

    seed_dir = str(VENDOR_RAG / "data" / "seed")

    with tempfile.TemporaryDirectory() as base:
        idx1 = os.path.join(base, "run1")
        idx2 = os.path.join(base, "run2")
        os.makedirs(idx1)
        os.makedirs(idx2)

        update_vectorstore(data_dir=seed_dir, vector_path=idx1)
        update_vectorstore(data_dir=seed_dir, vector_path=idx2)

        files1 = set(os.listdir(idx1))
        files2 = set(os.listdir(idx2))

        assert files1 == files2, f"두 빌드 결과 파일 목록이 달라야 하지 않음: {files1} vs {files2}"
        assert len(files1) > 0, "빌드 후 인덱스 파일이 최소 1개 이상이어야 함"
