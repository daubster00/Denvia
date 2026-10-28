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
from api.src.models.prompt_module_config import BUILTIN_BLOCK_IDS, PromptModuleConfig
from api.src.models.user import User
from api.src.rag_integration.prompt_injection import get_trigger_keywords
from api.src.schemas.admin.prompts import (
    ModelParamsResponse,
    ModelParamsUpdateRequest,
    PromptBlockResponse,
    PromptModelRouteItem,
    PromptModelRoutesResponse,
    PromptModelRoutesUpdateRequest,
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

# 블록 조립 순서를 담는 Redis 키 — query_runner 가 이 목록으로 어떤 블록이 존재하는지 파악한다.
# 값은 JSON 배열(DB id 오름차순 = [BASE, 원본 블록…, 관리자 추가 블록…]).
PROMPT_ORDER_KEY = "runtime:prompt:__order__"
# block_id 최대 길이 (prompt_module_configs.block_id 컬럼 = String(40)).
MAX_BLOCK_ID_LEN = 40


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

async def _validate_suppresses(
    db: AsyncSession, block_id: str, suppresses: list[str]
) -> list[str]:
    """상호배제(예외처리) 대상 검증 → 정리된 목록 반환. 위반 시 HTTP 422 {code}.

    각 대상은 (1) 실존 블록, (2) 자기 자신 아님, (3) BASE 아님(BASE 는 항상 포함).
    """
    from fastapi import HTTPException

    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in suppresses or []:
        t = (raw or "").strip()
        if not t or t in seen:
            continue
        if t == block_id:
            raise HTTPException(
                status_code=422,
                detail={"code": "PROMPT_SUPPRESS_TARGET_INVALID", "target": t, "reason": "self"},
            )
        if t == "BASE":
            raise HTTPException(
                status_code=422,
                detail={"code": "PROMPT_SUPPRESS_TARGET_INVALID", "target": t, "reason": "base"},
            )
        seen.add(t)
        cleaned.append(t)

    if cleaned:
        existing = set(
            (
                await db.execute(
                    select(PromptModuleConfig.block_id).where(
                        PromptModuleConfig.block_id.in_(cleaned)
                    )
                )
            ).scalars().all()
        )
        for t in cleaned:
            if t not in existing:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "PROMPT_SUPPRESS_TARGET_INVALID",
                        "target": t,
                        "reason": "unknown",
                    },
                )
    return cleaned


# 특정 프롬프트 모델 라우팅 설정의 model_param_configs.key (JSONB 1행에 전체 설정을 담는다).
# 블록마다 모델 컬럼을 두는 대신 "프롬프트 1개 + 모델 1개" 단일 설정으로 관리한다.
PROMPT_MODEL_ROUTE_PARAM_KEY = "prompt_model_route"

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
                suppresses=row.suppresses,
                # 원본(빌트인) 블록은 끄기만 가능, 관리자 생성 블록만 완전 삭제 가능.
                deletable=row.block_id not in BUILTIN_BLOCK_IDS,
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
    suppresses: list[str] | None = None,
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

    # 상호배제(예외처리) 편집(#95). 생략(None) 시 기존값 유지. []는 "배제 없음" 명시.
    if suppresses is not None:
        new_suppresses = await _validate_suppresses(db, block_id, suppresses)
    else:
        new_suppresses = row.suppresses

    before_hash = hashlib.sha256(row.content.encode()).hexdigest()[:12]
    before_enabled = row.enabled
    before_trigger_mode = (row.trigger_config or {}).get("mode")

    row.content = content
    row.enabled = enabled
    row.trigger_config = new_trigger
    row.suppresses = new_suppresses
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
                    {
                        "content": content,
                        "enabled": enabled,
                        "trigger_config": new_trigger,
                        "suppresses": new_suppresses,
                    },
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
        suppresses=new_suppresses,
        updated_at=row.updated_at,
    )


async def _rebuild_order_index(db: AsyncSession, r: aioredis.Redis) -> None:
    """DB 블록 목록(id 오름차순)을 Redis 순서 인덱스에 반영.

    id 순서 = [BASE, 원본 블록…, 관리자 추가 블록(생성 순)…] → 조립 순서와 동일.
    """
    order = (
        await db.execute(
            select(PromptModuleConfig.block_id).order_by(PromptModuleConfig.id)
        )
    ).scalars().all()
    await r.set(PROMPT_ORDER_KEY, json.dumps(list(order), ensure_ascii=False))


async def sync_prompts_to_redis(db: AsyncSession) -> int:
    """DB 전체 프롬프트 블록 → Redis 미러 + 순서 인덱스 (부팅 시 1회).

    DB 가 SSOT 이므로 Redis 를 DB 로 덮어써 항상 일치시킨다. 관리자가 새로 만든
    블록은 vendor 파일에 원본이 없어 Redis 가 비면 사라지므로, 이 동기화가 필수다.
    반환값은 동기화한 블록 수(로그/헬스체크용).
    """
    rows = (
        await db.execute(select(PromptModuleConfig).order_by(PromptModuleConfig.id))
    ).scalars().all()
    if not rows:
        return 0

    mapping: dict[str, str] = {}
    order: list[str] = []
    for row in rows:
        order.append(row.block_id)
        mapping[f"runtime:prompt:{row.block_id}"] = json.dumps(
            {
                "content": row.content,
                "enabled": row.enabled,
                "trigger_config": row.trigger_config,
                "suppresses": row.suppresses,
            },
            ensure_ascii=False,
        )
    mapping[PROMPT_ORDER_KEY] = json.dumps(order, ensure_ascii=False)

    r = await _get_redis()
    async with r:
        await r.mset(mapping)
    logger.info("prompt_config.synced_to_redis", count=len(rows))
    return len(rows)


def _validate_new_block_id(block_id: str) -> str:
    """관리자 신규 블록 block_id 검증 → 정리된 값 반환. 위반 시 HTTP 422 {code}."""
    from fastapi import HTTPException

    bid = (block_id or "").strip()
    if not bid:
        raise HTTPException(status_code=422, detail={"code": "PROMPT_BLOCK_ID_EMPTY"})
    if len(bid) > MAX_BLOCK_ID_LEN:
        raise HTTPException(
            status_code=422,
            detail={"code": "PROMPT_BLOCK_ID_TOO_LONG", "max": MAX_BLOCK_ID_LEN},
        )
    # BASE·원본 블록 이름, 내부 예약 접두사(__), Redis 키 구분자(:) 금지.
    if bid == "BASE" or bid in BUILTIN_BLOCK_IDS or bid.startswith("__") or ":" in bid:
        raise HTTPException(status_code=422, detail={"code": "PROMPT_BLOCK_ID_RESERVED"})
    return bid


async def create_prompt_block(
    request: Request,
    block_id: str,
    content: str,
    enabled: bool,
    trigger_config: TriggerConfig | None,
    admin: User,
    db: AsyncSession,
    suppresses: list[str] | None = None,
) -> PromptUpdateResponse:
    """관리자가 새 프롬프트 블록을 직접 생성. 발동조건 필수(vendor 폴백 없음)."""
    from fastapi import HTTPException

    bid = _validate_new_block_id(block_id)

    if not content.strip():
        raise HTTPException(status_code=422, detail={"code": "PROMPT_CONTENT_EMPTY"})

    # 관리자 블록은 vendor 파일에 원본 발동조건이 없으므로 반드시 함께 받아야 한다.
    if trigger_config is None:
        raise HTTPException(status_code=422, detail={"code": "PROMPT_TRIGGER_REQUIRED"})
    _validate_trigger_config(bid, trigger_config)  # base 모드 금지·키워드 비어있음 검증 포함

    # 상호배제(예외처리) 대상 검증 — 대상은 이미 존재하는 다른 블록이어야 함(#95).
    new_suppresses = (
        await _validate_suppresses(db, bid, suppresses) if suppresses is not None else None
    )

    existing = (
        await db.execute(
            select(PromptModuleConfig).where(PromptModuleConfig.block_id == bid)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=422, detail={"code": "PROMPT_BLOCK_ID_DUPLICATE"})

    new_trigger = trigger_config.model_dump(exclude_none=True)
    now = datetime.now(tz=timezone.utc)
    row = PromptModuleConfig(
        block_id=bid,
        content=content,
        enabled=enabled,
        trigger_config=new_trigger,
        suppresses=new_suppresses,
        updated_by_admin_id=admin.id,
        updated_at=now,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    request.state.audit_target_type = "prompt_block"
    request.state.audit_target_id = bid
    request.state.audit_diff = {
        "created": {
            "content_hash": hashlib.sha256(content.encode()).hexdigest()[:12],
            "enabled": enabled,
            "trigger_mode": new_trigger.get("mode"),
        }
    }

    try:
        r = await _get_redis()
        async with r:
            await r.set(
                f"runtime:prompt:{bid}",
                json.dumps(
                    {
                        "content": content,
                        "enabled": enabled,
                        "trigger_config": new_trigger,
                        "suppresses": new_suppresses,
                    },
                    ensure_ascii=False,
                ),
            )
            await _rebuild_order_index(db, r)
    except Exception as e:
        logger.warning("prompt_config.redis_create_failed", block_id=bid, error=str(e))

    logger.info("prompt_config.created", block_id=bid)
    return PromptUpdateResponse(
        block_id=bid,
        content=content,
        enabled=enabled,
        trigger_config=TriggerConfig(**new_trigger),
        suppresses=new_suppresses,
        updated_at=row.updated_at,
    )


async def delete_prompt_block(
    request: Request,
    block_id: str,
    admin: User,
    db: AsyncSession,
) -> None:
    """관리자 생성 블록만 완전 삭제. 원본(빌트인) 블록은 끄기로만 처리(삭제 거부)."""
    from fastapi import HTTPException

    if block_id == "BASE" or block_id in BUILTIN_BLOCK_IDS:
        raise HTTPException(
            status_code=422, detail={"code": "PROMPT_BLOCK_BUILTIN_UNDELETABLE"}
        )

    row = (
        await db.execute(
            select(PromptModuleConfig).where(PromptModuleConfig.block_id == block_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=422, detail={"code": "PROMPT_BLOCK_NOT_FOUND"})

    await db.delete(row)
    await db.commit()

    request.state.audit_target_type = "prompt_block"
    request.state.audit_target_id = block_id
    request.state.audit_diff = {"deleted": {"block_id": block_id}}

    try:
        r = await _get_redis()
        async with r:
            await r.delete(f"runtime:prompt:{block_id}")
            await _rebuild_order_index(db, r)
    except Exception as e:
        logger.warning("prompt_config.redis_delete_failed", block_id=block_id, error=str(e))

    logger.info("prompt_config.deleted", block_id=block_id)


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


# =============================================================================
# 특정 프롬프트 모델 라우팅 — "이 프롬프트가 실제 주입된 질문만 다른 모델로"
#   SSOT: model_param_configs(key=prompt_model_route) → Redis runtime:prompt_model_route 미러.
#   저장 형태: {"routes": [{"block_id","model","enabled"}, ...]} — 목록 순서 = 우선순위.
#   런타임(query_runner)은 Redis 만 읽으므로, 저장 즉시 다음 질문부터 반영된다.
#   추가 OpenAI 호출·질문 복잡도 분석은 없다 — 프롬프트 조립 결과(주입 목록)만 본다.
# =============================================================================


def _routes_response(routes: list[dict]) -> PromptModelRoutesResponse:
    from api.src.services.runtime_config_service import (
        ALLOWED_CHAT_MODELS,
        DEFAULT_CHAT_MODEL,
        chat_model_catalog_payload,
    )

    return PromptModelRoutesResponse(
        routes=[PromptModelRouteItem(**r) for r in routes],
        allowed_models=list(ALLOWED_CHAT_MODELS),
        default_model=DEFAULT_CHAT_MODEL,
        models=chat_model_catalog_payload(),
    )


async def _load_routes(db: AsyncSession) -> list[dict]:
    from api.src.services.runtime_config_service import normalize_prompt_model_routes

    row = (
        await db.execute(
            select(ModelParamConfig).where(
                ModelParamConfig.key == PROMPT_MODEL_ROUTE_PARAM_KEY
            )
        )
    ).scalar_one_or_none()
    return normalize_prompt_model_routes(row.value_json if row is not None else None)


async def get_prompt_model_routes(db: AsyncSession) -> PromptModelRoutesResponse:
    """현재 지정 목록 + 허용 모델 목록 조회 (관리자 UI 드롭다운 옵션 소스)."""
    return _routes_response(await _load_routes(db))


async def _validate_prompt_model_routes(
    db: AsyncSession, items: list[PromptModelRouteItem]
) -> list[dict]:
    """저장 전 검증 → 정규화된 목록. 위반 시 HTTP 422 {code}.

    각 지정은 (1) 실존 블록, (2) BASE 아님, (3) 허용 모델, (4) 블록 중복 없음.
    """
    from fastapi import HTTPException

    from api.src.services.runtime_config_service import (
        ALLOWED_CHAT_MODELS,
        PROMPT_MODEL_ROUTES_MAX,
    )

    if len(items) > PROMPT_MODEL_ROUTES_MAX:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "PROMPT_MODEL_ROUTE_TOO_MANY",
                "max": PROMPT_MODEL_ROUTES_MAX,
            },
        )

    cleaned: list[dict] = []
    seen: set[str] = set()
    for item in items:
        block_id = (item.block_id or "").strip()
        model = (item.model or "").strip()

        if not block_id:
            raise HTTPException(
                status_code=422, detail={"code": "PROMPT_MODEL_ROUTE_BLOCK_REQUIRED"}
            )
        # BASE 는 모든 질문에 항상 포함되므로 "특정 프롬프트"가 될 수 없다.
        if block_id == "BASE":
            raise HTTPException(
                status_code=422,
                detail={"code": "PROMPT_MODEL_ROUTE_BLOCK_INVALID", "reason": "base"},
            )
        if block_id in seen:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "PROMPT_MODEL_ROUTE_BLOCK_DUPLICATE",
                    "block_id": block_id,
                },
            )
        if not model:
            raise HTTPException(
                status_code=422, detail={"code": "PROMPT_MODEL_ROUTE_MODEL_REQUIRED"}
            )
        if model not in ALLOWED_CHAT_MODELS:
            raise HTTPException(
                status_code=422,
                detail={"code": "PROMPT_MODEL_ROUTE_MODEL_INVALID", "model": model},
            )

        seen.add(block_id)
        cleaned.append(
            {"block_id": block_id, "model": model, "enabled": bool(item.enabled)}
        )

    if cleaned:
        existing = set(
            (
                await db.execute(
                    select(PromptModuleConfig.block_id).where(
                        PromptModuleConfig.block_id.in_([c["block_id"] for c in cleaned])
                    )
                )
            ).scalars().all()
        )
        for c in cleaned:
            if c["block_id"] not in existing:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "PROMPT_MODEL_ROUTE_BLOCK_INVALID",
                        "reason": "unknown",
                        "block_id": c["block_id"],
                    },
                )
    return cleaned


async def _mirror_prompt_model_routes_to_redis(routes: list[dict]) -> None:
    """지정 목록을 Redis 로 미러 — query_runner 가 매 질문마다 이 키를 읽는다."""
    from api.src.services.runtime_config_service import KEY_PROMPT_MODEL_ROUTE

    try:
        r = await _get_redis()
        async with r:
            await r.set(
                KEY_PROMPT_MODEL_ROUTE,
                json.dumps({"routes": routes}, ensure_ascii=False),
            )
    except Exception as e:
        logger.warning("prompt_config.model_route_redis_failed", error=str(e))


async def update_prompt_model_routes(
    request: Request,
    req: PromptModelRoutesUpdateRequest,
    admin: User,
    db: AsyncSession,
) -> PromptModelRoutesResponse:
    """지정 목록 전체 교체 (DB upsert → Redis 미러 → 감사 diff)."""
    routes = await _validate_prompt_model_routes(db, req.routes)

    existing = (
        await db.execute(
            select(ModelParamConfig).where(
                ModelParamConfig.key == PROMPT_MODEL_ROUTE_PARAM_KEY
            )
        )
    ).scalar_one_or_none()

    before = await _load_routes(db)
    value = {"routes": routes}
    now = datetime.now(tz=timezone.utc)
    if existing is not None:
        existing.value_json = value
        existing.updated_by_admin_id = admin.id
        existing.updated_at = now
    else:
        db.add(
            ModelParamConfig(
                key=PROMPT_MODEL_ROUTE_PARAM_KEY,
                value_json=value,
                updated_by_admin_id=admin.id,
                updated_at=now,
            )
        )
    await db.commit()

    # audit_logs.target_id 는 BIGINT 라 블록 이름(한글)을 넣을 수 없다.
    # 지정 내역은 diff_json(before/after)에 담겨 감사 화면에서 그대로 확인된다.
    request.state.audit_target_type = "prompt_model_route"
    request.state.audit_diff = {"before": before, "after": routes}

    await _mirror_prompt_model_routes_to_redis(routes)
    logger.info("prompt_config.model_routes_updated", count=len(routes), routes=routes)

    return _routes_response(routes)


async def sync_prompt_model_routes_to_redis(db: AsyncSession) -> list[dict]:
    """DB(SSOT) → Redis 미러 (부팅 시 1회).

    Redis 가 비거나 flush 돼도 관리자가 저장한 지정이 살아 있게 한다.
    DB 에 행이 없으면 빈 목록 → "모든 질문이 기본 모델" 상태를 보장한다.
    """
    routes = await _load_routes(db)
    await _mirror_prompt_model_routes_to_redis(routes)
    return routes

