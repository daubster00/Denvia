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

__all__ = [
    "generate_rule_answer",
    "apply_scaling_rules",
    "normalize_query",
    "load_synonym_dict",
    "init_rag",
    "get_retriever",
    "get_syn_dict",
    "extract_procedures",
]
