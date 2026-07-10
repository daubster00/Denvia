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
    """단일 프롬프트 블록의 오버라이드 값.

    trigger_config 가 주어지면 발동조건(키워드 매칭)까지 오버라이드한다(#129).
    None 이면 vendor 파일의 기본 발동조건을 그대로 쓴다.
    """

    def __init__(
        self,
        content: str,
        enabled: bool,
        trigger_config: dict | None = None,
    ) -> None:
        self.content = content
        self.enabled = enabled
        self.trigger_config = trigger_config


def _file_trigger_config(block_id: str, module: dict) -> dict:
    """vendor 모듈 dict → trigger_config 형태(mode + 키워드 리스트)."""
    if block_id == "BASE":
        return {"mode": "base"}
    if "keywords_all" in module:
        return {"mode": "keywords_all", "keywords_all": module["keywords_all"]}
    if "keywords_combo" in module:
        combo = module["keywords_combo"]
        return {
            "mode": "keywords_combo",
            "set1": combo["set1"],
            "independent": combo["independent"],
        }
    if "group_keywords" in module and "required_keywords" in module:
        return {
            "mode": "group",
            "group_keywords": module["group_keywords"],
            "required_keywords": module["required_keywords"],
        }
    return {"mode": "keywords", "keywords": module.get("keywords", [])}


def _match_trigger_config(query: str, cfg: dict, matchers: dict) -> bool:
    """trigger_config(mode + 키워드) 로 발동 여부를 판정. vendor 매칭 함수 재사용."""
    mode = cfg.get("mode")
    if mode == "base":
        return True
    if mode == "keywords_all":
        return matchers["all"](query, cfg.get("keywords_all") or [])
    if mode == "keywords_combo":
        return matchers["perio"](query, cfg.get("set1") or [], cfg.get("independent") or [])
    if mode == "group":
        return matchers["group"](
            query, cfg.get("group_keywords") or [], cfg.get("required_keywords") or []
        )
    # 기본(keywords) — 알 수 없는 mode 도 안전하게 keywords 매칭으로 처리.
    return matchers["kw"](query, cfg.get("keywords") or [])


def build_prompt_with_overrides(
    query: str,
    overrides: dict[str, PromptOverride] | None = None,
) -> str:
    """vendor/rag build_prompt_template 로직을 DB/Redis 오버라이드로 재현한다.

    overrides가 None이거나 비어있으면 vendor/rag 기본값 fallback.
    각 모듈의 발동조건은 override.trigger_config 가 있으면 그것을, 없으면 vendor 파일값을 쓴다.
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

        matchers = {
            "kw": _match_keywords,
            "all": _match_keywords_all,
            "perio": _match_periodontal,
            "group": _match_group_and_keywords,
        }

        def _eff_cfg(block_id: str) -> dict:
            """유효 발동조건 = override.trigger_config 우선, 없으면 vendor 파일값."""
            ov = overrides.get(block_id)
            if ov is not None and ov.trigger_config:
                return ov.trigger_config
            return _file_trigger_config(block_id, PROMPT_MODULES.get(block_id, {}))

        parts: list[str] = []

        base_override = overrides.get("BASE")
        if base_override is None:
            parts.append(BASE_PROMPT)
        elif base_override.enabled:
            parts.append(base_override.content)

        # 브릿지/치주치료/마취/치주낭 모듈이 활성화되면 치식_위치/치면_방향 블록은 주입하지 않는다.
        # (vendor build_prompt_template과 동일한 동작 — 각 모듈 본문의 자체 표기·산정 규칙과 충돌 방지)
        # 편집된 발동조건을 반영하려면 배제 판정도 유효 config 로 계산해야 한다.
        bridge_active = _match_trigger_config(query, _eff_cfg("브릿지"), matchers)
        periodontal_active = _match_trigger_config(query, _eff_cfg("치주치료_산정"), matchers)
        anesthesia_active = _match_trigger_config(query, _eff_cfg("마취_산정"), matchers)
        perio_exam_active = _match_trigger_config(
            query, _eff_cfg("치주낭측정검사_횟수산정"), matchers
        )
        suppress_positional = (
            bridge_active or periodontal_active or anesthesia_active or perio_exam_active
        )

        injected: list[str] = []
        for module_name, module_data in PROMPT_MODULES.items():
            matched = _match_trigger_config(query, _eff_cfg(module_name), matchers)
            if not matched:
                continue
            if suppress_positional and module_name in ("치식_위치", "치면_방향"):
                continue

            override = overrides.get(module_name)
            if override is not None:
                if not override.enabled:
                    continue
                parts.append(override.content)
            else:
                parts.append(module_data["text"])
            injected.append(module_name)

        # vendor build_prompt_template과 동일한 최종 템플릿 (#110 클라이언트 compact 포맷)
        parts.append("""
질문: {question}
문서: {context}
답변:""")

        if injected:
            logger.info("prompt_injection.modules_injected", modules=injected)

        return "\n".join(parts)

    except Exception as e:
        logger.warning("prompt_injection.build_failed", error=str(e))
        from rag.prompt_builder import build_prompt_template  # type: ignore[import-untyped]

        return build_prompt_template(query)
