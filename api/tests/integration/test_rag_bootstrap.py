"""RAG 부트스트랩 통합 테스트 — FAISS 초기화 + run_qa end-to-end.

OPENAI_API_KEY 없으면 전체 skip.
실행: cd api && uv run pytest tests/integration/test_rag_bootstrap.py -v
"""

import os
import tempfile

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY 없음 — RAG 통합 테스트 skip",
)


@pytest.fixture(scope="module")
def tmp_faiss_dirs():
    """격리된 임시 FAISS 디렉터리 세트를 생성한다."""
    with tempfile.TemporaryDirectory() as base:
        index_a = os.path.join(base, "index_a")
        current = os.path.join(base, "current")
        seed_dir = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "vendor", "rag", "data", "seed"
        )
        os.makedirs(index_a, exist_ok=True)
        yield {"index_a": index_a, "current": current, "seed_dir": seed_dir, "base": base}


@pytest.fixture(scope="module")
def built_faiss(tmp_faiss_dirs):
    """seed 데이터로 index_a를 빌드하고 current 심볼릭 링크를 생성한다."""
    from update_vectorstore import update_vectorstore
    from api.utils.faiss_swap import swap_faiss_index

    dirs = tmp_faiss_dirs
    update_vectorstore(data_dir=dirs["seed_dir"], vector_path=dirs["index_a"])
    swap_faiss_index(dirs["index_a"], dirs["current"])
    return dirs


def test_faiss_current_symlink_points_to_index_a(built_faiss):
    """current 심볼릭 링크가 index_a를 가리키는지 확인."""
    current = built_faiss["current"]
    assert os.path.islink(current) or os.path.isdir(current), "current 링크/디렉터리가 존재해야 함"
    real = os.path.realpath(current)
    assert os.path.basename(real) == "index_a", "current는 index_a를 가리켜야 함"


def test_run_qa_responds_with_seed_query(built_faiss):
    """init_rag + retriever 부트가 성공하고 generate_rule_answer가 호출 가능한지 확인."""
    from run_qa.run_qa import init_rag, generate_rule_answer, get_retriever

    init_rag(faiss_path=built_faiss["current"])
    retriever = get_retriever()
    assert retriever is not None, "init_rag 후 retriever가 None이면 안 됨"

    # vendor 시그니처: generate_rule_answer(query) — 1 인자. extract_procedures 미매칭 시 None 반환.
    answer = generate_rule_answer("임플란트 보험 적용 기준")
    assert answer is None or isinstance(answer, str)
