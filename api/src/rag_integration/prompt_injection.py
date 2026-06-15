"""프롬프트 블록 런타임 주입 — vendor/rag 수정 없이 DB/Redis 오버라이드 적용."""
from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


def get_trigger_keywords(block_id: str) -> list[str]:
    """vendor/rag prompt_builder.PROMPT_MODULES에서 block_id의 키워드를 읽는다.

    BASE는 항상 포함(트리거 없음)이므로 빈 리스트 반환.
    리플렉션이므로 vendor/rag 파일은 수정하지 않는다.
    """
    if block_id == "BASE":
        return []
    try:
        from rag.prompt_builder import PROMPT_MODULES  # type: ignore[import-untyped]

        module = PROMPT_MODULES.get(block_id, {})
        # 모듈 매칭 방식 4종(keywords / keywords_all / keywords_combo / group+required)을
        # 모두 펼쳐 트리거 키워드 목록으로 반환한다.
        kws = list(module.get("keywords", []))
        kws += list(module.get("keywords_all", []))
        combo = module.get("keywords_combo")
        if combo:
            kws += list(combo.get("set1", [])) + list(combo.get("independent", []))
        kws += list(module.get("group_keywords", [])) + list(module.get("required_keywords", []))
        return kws
    except Exception as e:
        logger.warning("prompt_injection.get_keywords_failed", block_id=block_id, error=str(e))
        return []


class PromptOverride:
    """단일 프롬프트 블록의 오버라이드 값."""

    def __init__(self, content: str, enabled: bool) -> None:
        self.content = content
        self.enabled = enabled


def build_prompt_with_overrides(
    query: str,
    overrides: dict[str, PromptOverride] | None = None,
) -> str:
    """vendor/rag build_prompt_template 로직을 DB/Redis 오버라이드로 재현한다.

    overrides가 None이거나 비어있으면 vendor/rag 기본값 fallback.
    """
    if not overrides:
        from rag.prompt_builder import build_prompt_template  # type: ignore[import-untyped]

        return build_prompt_template(query)

    try:
        from rag.prompt_builder import BASE_PROMPT, PROMPT_MODULES  # type: ignore[import-untyped]
        from rag.prompt_builder.prompt_builder import (  # type: ignore[import-untyped]
            _match_group_and_keywords,
            _match_keywords,
            _match_keywords_all,
            _match_periodontal,
        )

        parts: list[str] = []

        base_override = overrides.get("BASE")
        if base_override is None:
            parts.append(BASE_PROMPT)
        elif base_override.enabled:
            parts.append(base_override.content)

        # 브릿지/치주치료/마취 모듈이 활성화되면 치식_위치/치면_방향 블록은 주입하지 않는다.
        # (vendor build_prompt_template과 동일한 동작 — 각 모듈 본문의 자체 표기·산정 규칙과 충돌 방지)
        bridge_active = _match_keywords(query, PROMPT_MODULES["브릿지"]["keywords"])
        periodontal_active = (
            "keywords_combo" in PROMPT_MODULES.get("치주치료_산정", {})
            and _match_periodontal(
                query,
                PROMPT_MODULES["치주치료_산정"]["keywords_combo"]["set1"],
                PROMPT_MODULES["치주치료_산정"]["keywords_combo"]["independent"],
            )
        )
        anesthesia_active = _match_keywords(query, PROMPT_MODULES["마취_산정"]["keywords"])

        injected: list[str] = []
        for module_name, module_data in PROMPT_MODULES.items():
            # vendor build_prompt_template과 동일한 매칭 방식 4종 분기
            if "group_keywords" in module_data and "required_keywords" in module_data:
                matched = _match_group_and_keywords(
                    query, module_data["group_keywords"], module_data["required_keywords"]
                )
            elif "keywords_all" in module_data:
                matched = _match_keywords_all(query, module_data["keywords_all"])
            elif "keywords_combo" in module_data:
                matched = _match_periodontal(
                    query,
                    module_data["keywords_combo"]["set1"],
                    module_data["keywords_combo"]["independent"],
                )
            else:
                matched = _match_keywords(query, module_data["keywords"])

            if not matched:
                continue
            if bridge_active and module_name in ("치식_위치", "치면_방향"):
                continue
            if periodontal_active and module_name in ("치식_위치", "치면_방향"):
                continue
            if anesthesia_active and module_name in ("치식_위치", "치면_방향"):
                continue

            override = overrides.get(module_name)
            if override is not None:
                if not override.enabled:
                    continue
                parts.append(override.content)
            else:
                parts.append(module_data["text"])
            injected.append(module_name)

        parts.append("""

질문: {question}

문서:
{context}

답변:""")

        if injected:
            logger.info("prompt_injection.modules_injected", modules=injected)

        return "\n".join(parts)

    except Exception as e:
        logger.warning("prompt_injection.build_failed", error=str(e))
        from rag.prompt_builder import build_prompt_template  # type: ignore[import-untyped]

        return build_prompt_template(query)
