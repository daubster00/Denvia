"""프롬프트 블록 + 모델 파라미터 런타임 구성 서비스 — Story 8.4."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

import redis.asyncio as aioredis
import structlog
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.model_param_config import ModelParamConfig
from api.src.models.prompt_module_config import PromptModuleConfig
from api.src.models.user import User
from api.src.rag_integration.prompt_injection import get_trigger_keywords
from api.src.schemas.admin.prompts import (
    ModelParamsResponse,
    ModelParamsUpdateRequest,
    PromptBlockResponse,
    PromptsListResponse,
    PromptUpdateResponse,
    TriggerConfig,
)
from api.src.settings import REDIS_DB_RUNTIME_CONFIG, settings

logger = structlog.get_logger(__name__)

# #129: 발동조건 매칭 방식 4종 + BASE 고정.
_TRIGGER_MODES = {"base", "keywords", "keywords_all", "keywords_combo", "group"}
# mode → 비어있으면 안 되는 키워드 리스트 필드들.
_TRIGGER_REQUIRED_LISTS = {
    "keywords": ("keywords",),
    "keywords_all": ("keywords_all",),
    "keywords_combo": ("set1", "independent"),
    "group": ("group_keywords", "required_keywords"),
}
# vendor 가 정규식으로 취급하는 키워드 접두사 (그 외는 문자열 리터럴 매칭).
_REGEX_PREFIXES = (r"\b", r"\d", "#", r"i\d")


def _flatten_trigger(cfg: dict | None) -> list[str]:
    """trigger_config → 평탄화된 키워드 목록(구버전 프론트 호환/표시용)."""
    if not cfg:
        return []
    kws: list[str] = []
    for field in ("keywords", "keywords_all", "set1", "independent",
                  "group_keywords", "required_keywords"):
        vals = cfg.get(field)
        if vals:
            kws.extend(vals)
    return kws


def _validate_trigger_config(block_id: str, cfg: TriggerConfig) -> None:
    """발동조건 검증 → 위반 시 HTTP 422 {code}. (프롬프트 파손 방지 핵심)"""
    from fastapi import HTTPException

    def _fail(code: str, **extra) -> None:
        raise HTTPException(status_code=422, detail={"code": code, **extra})

    if cfg.mode not in _TRIGGER_MODES:
        _fail("PROMPT_TRIGGER_MODE_INVALID", mode=cfg.mode)

    # BASE 는 항상 포함(트리거 없음) — mode 는 base 로 고정. 그 외 블록은 base 금지.
    if block_id == "BASE" and cfg.mode != "base":
        _fail("PROMPT_TRIGGER_BASE_LOCKED")
    if block_id != "BASE" and cfg.mode == "base":
        _fail("PROMPT_TRIGGER_BASE_LOCKED")

    if cfg.mode == "base":
        return

    data = cfg.model_dump()
    keywords_seen: list[str] = []
    for field in _TRIGGER_REQUIRED_LISTS[cfg.mode]:
        vals = data.get(field)
        # 공백만 있는 항목은 무효 취급.
        cleaned = [v for v in (vals or []) if v and v.strip()]
        if not cleaned:
            _fail("PROMPT_TRIGGER_KEYWORDS_EMPTY", field=field)
        keywords_seen.extend(cleaned)

    # 정규식 검증은 vendor 매칭 규칙과 정확히 일치시킨다:
    #   - keywords_combo(치주식 조합)는 vendor 가 정규식이 아니라 '문자열 포함'으로만 매칭한다
    #     ("?" 같은 항목이 정상값이므로 re.compile 하면 안 됨).
    #   - keywords/keywords_all/group 은 특정 접두사(\b, \d, #, i\d)로 시작할 때만 정규식으로 취급.
    if cfg.mode != "keywords_combo":
        for kw in keywords_seen:
            if kw.startswith(_REGEX_PREFIXES):
                try:
                    re.compile(kw)
                except re.error:
                    _fail("PROMPT_TRIGGER_REGEX_INVALID", keyword=kw)

VALID_K_RANGE = (1, 20)
VALID_TEMP_RANGE = (0.0, 1.0)
VALID_TOKENS_RANGE = (256, 4096)
# 사용자 질문 입력 글자수 상한 — 시스템 프롬프트는 별도 변수라 카운트에서 자동 제외.
VALID_QUESTION_CHARS_RANGE = (100, 5000)
DEFAULT_QUESTION_CHARS = 2000


async def _get_redis() -> aioredis.Redis:
    return aioredis.from_url(
        settings.redis_url,
        db=REDIS_DB_RUNTIME_CONFIG,
        decode_responses=True,
    )


async def get_prompts(db: AsyncSession) -> PromptsListResponse:
    rows = (
        await db.execute(select(PromptModuleConfig).order_by(PromptModuleConfig.id))
    ).scalars().all()

    blocks = []
    for row in rows:
        cfg = row.trigger_config
        # trigger_config 는 마이그레이션에서 채워지나, 없으면(구데이터) 파일 기준으로 폴백.
        trigger_keywords = _flatten_trigger(cfg) if cfg else get_trigger_keywords(row.block_id)
        blocks.append(
            PromptBlockResponse(
                block_id=row.block_id,
                trigger_keywords=trigger_keywords,
                trigger_config=TriggerConfig(**cfg) if cfg else None,
                content=row.content,
                enabled=row.enabled,
                updated_at=row.updated_at,
            )
        )
    return PromptsListResponse(blocks=blocks)


async def update_prompt(
    request: Request,
    block_id: str,
    content: str,
    enabled: bool,
    admin: User,
    db: AsyncSession,
    trigger_config: TriggerConfig | None = None,
) -> PromptUpdateResponse:
    from fastapi import HTTPException

    row = (
        await db.execute(
            select(PromptModuleConfig).where(PromptModuleConfig.block_id == block_id)
        )
    ).scalar_one_or_none()

    if row is None:
        raise HTTPException(status_code=422, detail={"code": "PROMPT_BLOCK_NOT_FOUND"})

    if not content.strip():
        raise HTTPException(status_code=422, detail={"code": "PROMPT_CONTENT_EMPTY"})

    # 발동조건 편집(#129). 생략 시 기존값 유지(글 내용만 변경).
    if trigger_config is not None:
        _validate_trigger_config(block_id, trigger_config)
        new_trigger = trigger_config.model_dump(exclude_none=True)
    else:
        new_trigger = row.trigger_config

    before_hash = hashlib.sha256(row.content.encode()).hexdigest()[:12]
    before_enabled = row.enabled
    before_trigger_mode = (row.trigger_config or {}).get("mode")

    row.content = content
    row.enabled = enabled
    row.trigger_config = new_trigger
    row.updated_by_admin_id = admin.id
    row.updated_at = datetime.now(tz=timezone.utc)
    await db.commit()
    await db.refresh(row)

    after_hash = hashlib.sha256(content.encode()).hexdigest()[:12]
    after_trigger_mode = (new_trigger or {}).get("mode")
    request.state.audit_target_type = "prompt_block"
    request.state.audit_target_id = block_id
    request.state.audit_diff = {
        "before": {
            "content_hash": before_hash,
            "enabled": before_enabled,
            "trigger_mode": before_trigger_mode,
        },
        "after": {
            "content_hash": after_hash,
            "enabled": enabled,
            "trigger_mode": after_trigger_mode,
        },
    }

    try:
        r = await _get_redis()
        async with r:
            await r.set(
                f"runtime:prompt:{block_id}",
                json.dumps(
                    {"content": content, "enabled": enabled, "trigger_config": new_trigger},
                    ensure_ascii=False,
                ),
            )
    except Exception as e:
        logger.warning("prompt_config.redis_update_failed", block_id=block_id, error=str(e))

    logger.info(
        "prompt_config.updated",
        block_id=block_id,
        before_hash=before_hash,
        after_hash=after_hash,
    )

    return PromptUpdateResponse(
        block_id=row.block_id,
        content=row.content,
        enabled=row.enabled,
        trigger_config=TriggerConfig(**new_trigger) if new_trigger else None,
        updated_at=row.updated_at,
    )


async def get_model_params(db: AsyncSession) -> ModelParamsResponse:
    rows = (await db.execute(select(ModelParamConfig))).scalars().all()
    params = {row.key: row.value_json for row in rows}
    return ModelParamsResponse(
        rag_k=int(params.get("rag_k", 5)),
        rag_temperature=float(params.get("rag_temperature", 0.0)),
        max_tokens=int(params.get("max_tokens", 1024)),
        max_question_chars=int(
            params.get("max_question_chars", DEFAULT_QUESTION_CHARS)
        ),
    )


async def update_model_params(
    request: Request,
    req: ModelParamsUpdateRequest,
    admin: User,
    db: AsyncSession,
) -> ModelParamsResponse:
    from fastapi import HTTPException

    errors = []
    if not (VALID_K_RANGE[0] <= req.rag_k <= VALID_K_RANGE[1]):
        errors.append({"field": "rag_k", "min": 1, "max": 20, "received": req.rag_k})
    if not (VALID_TEMP_RANGE[0] <= req.rag_temperature <= VALID_TEMP_RANGE[1]):
        errors.append(
            {"field": "rag_temperature", "min": 0.0, "max": 1.0, "received": req.rag_temperature}
        )
    if not (VALID_TOKENS_RANGE[0] <= req.max_tokens <= VALID_TOKENS_RANGE[1]):
        errors.append(
            {"field": "max_tokens", "min": 256, "max": 4096, "received": req.max_tokens}
        )
    if not (
        VALID_QUESTION_CHARS_RANGE[0]
        <= req.max_question_chars
        <= VALID_QUESTION_CHARS_RANGE[1]
    ):
        errors.append(
            {
                "field": "max_question_chars",
                "min": VALID_QUESTION_CHARS_RANGE[0],
                "max": VALID_QUESTION_CHARS_RANGE[1],
                "received": req.max_question_chars,
            }
        )

    if errors:
        raise HTTPException(
            status_code=422,
            detail={"code": "MODEL_PARAM_OUT_OF_RANGE", "errors": errors},
        )

    now = datetime.now(tz=timezone.utc)
    updates = {
        "rag_k": req.rag_k,
        "rag_temperature": req.rag_temperature,
        "max_tokens": req.max_tokens,
        "max_question_chars": req.max_question_chars,
    }
    before: dict[str, object] = {}

    for key, value in updates.items():
        existing = (
            await db.execute(
                select(ModelParamConfig).where(ModelParamConfig.key == key)
            )
        ).scalar_one_or_none()

        if existing:
            before[key] = existing.value_json
            existing.value_json = value
            existing.updated_by_admin_id = admin.id
            existing.updated_at = now
        else:
            before[key] = None
            db.add(
                ModelParamConfig(
                    key=key,
                    value_json=value,
                    updated_by_admin_id=admin.id,
                    updated_at=now,
                )
            )

    await db.commit()

    request.state.audit_target_type = "rag_model_params"
    request.state.audit_target_id = "runtime"
    request.state.audit_diff = {"before": before, "after": updates}

    try:
        r = await _get_redis()
        async with r:
            await r.mset(
                {
                    "runtime:rag_k": str(req.rag_k),
                    "runtime:rag_temperature": str(req.rag_temperature),
                    "runtime:max_tokens": str(req.max_tokens),
                    "runtime:max_question_chars": str(req.max_question_chars),
                }
            )
    except Exception as e:
        logger.warning("prompt_config.redis_update_failed", keys=list(updates), error=str(e))

    return ModelParamsResponse(
        rag_k=req.rag_k,
        rag_temperature=req.rag_temperature,
        max_tokens=req.max_tokens,
        max_question_chars=req.max_question_chars,
    )
