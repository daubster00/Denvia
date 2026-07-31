"""run_qa 패키지 — 임포트 인터페이스 노출."""

from .run_qa import (
    generate_rule_answer,
    apply_scaling_rules,
    normalize_query,
    load_synonym_dict,
    init_rag,
    get_retriever,
    get_syn_dict,
    extract_procedures,
)
# 게시판 #139/#140 — 치주낭측정검사 횟수 자동산정(장애인가산과 동일한 결정형 우회 모듈)
from .periodontal_pocket_calc import (
    get_periodontal_result,
    build_periodontal_llm_prompt,
)

__all__ = [
    "generate_rule_answer",
    "apply_scaling_rules",
    "normalize_query",
    "load_synonym_dict",
    "init_rag",
    "get_retriever",
    "get_syn_dict",
    "extract_procedures",
    "get_periodontal_result",
    "build_periodontal_llm_prompt",
]
