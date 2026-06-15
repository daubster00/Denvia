"""prompt_config_service 단위 테스트 — Story 8.4."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.src.rag_integration.prompt_injection import (
    PromptOverride,
    build_prompt_with_overrides,
    get_trigger_keywords,
)


# ──────────────────────────────────────────────────────────────────────────────
# get_trigger_keywords
# ──────────────────────────────────────────────────────────────────────────────

def test_get_trigger_keywords_base_returns_empty():
    result = get_trigger_keywords("BASE")
    assert result == []


def test_get_trigger_keywords_returns_nonempty_list():
    result = get_trigger_keywords("치식_위치")
    assert isinstance(result, list)
    assert len(result) >= 1


def test_get_trigger_keywords_unknown_block_returns_empty():
    result = get_trigger_keywords("존재안함")
    assert result == []


# ──────────────────────────────────────────────────────────────────────────────
# build_prompt_with_overrides
# ──────────────────────────────────────────────────────────────────────────────

def test_build_prompt_with_overrides_none_uses_vendor_default():
    """overrides=None → vendor/rag build_prompt_template 위임."""
    query = "보험임플란트 취소"
    result = build_prompt_with_overrides(query, None)
    assert "질문:" in result
    assert "{question}" in result
    assert "{context}" in result


def test_build_prompt_with_overrides_template_format():
    """조건부 모듈이 없는 일반 쿼리도 질문/문서/답변 형식 유지."""
    query = "보험임플란트 취소"
    overrides: dict[str, PromptOverride] = {}
    result = build_prompt_with_overrides(query, overrides)
    assert "질문: {question}" in result
    assert "문서:" in result
    assert "답변:" in result


def test_build_prompt_with_overrides_base_disabled():
    """BASE 블록을 disabled로 설정하면 BASE 콘텐츠 제외."""
    query = "보험임플란트 취소"
    overrides = {"BASE": PromptOverride(content="기본 내용", enabled=False)}
    result = build_prompt_with_overrides(query, overrides)
    assert "기본 내용" not in result
    assert "질문: {question}" in result


def test_build_prompt_with_overrides_base_content_override():
    """BASE 블록 콘텐츠 오버라이드가 실제 적용된다."""
    query = "보험임플란트 취소"
    custom_content = "커스텀 기본 프롬프트"
    overrides = {"BASE": PromptOverride(content=custom_content, enabled=True)}
    result = build_prompt_with_overrides(query, overrides)
    assert custom_content in result


def test_build_prompt_with_overrides_치식_query():
    """치식 관련 쿼리 시 치식_위치 모듈이 포함되며 템플릿 형식 유지."""
    query = "#14 치식 위치"
    result = build_prompt_with_overrides(query, None)
    assert "질문: {question}" in result
    assert "답변:" in result


# ──────────────────────────────────────────────────────────────────────────────
# update_model_params — 범위 검증
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_model_params_k_out_of_range():
    """k=0 → MODEL_PARAM_OUT_OF_RANGE 발생."""
    from fastapi import HTTPException

    from api.src.schemas.admin.prompts import ModelParamsUpdateRequest
    from api.src.services.prompt_config_service import update_model_params

    req_data = ModelParamsUpdateRequest(rag_k=0, rag_temperature=0.3, max_tokens=1024)
    request = MagicMock()
    request.state = MagicMock()
    admin = MagicMock()
    admin.id = 99
    db = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        await update_model_params(request, req_data, admin, db)

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == "MODEL_PARAM_OUT_OF_RANGE"


@pytest.mark.asyncio
async def test_update_model_params_temperature_too_high():
    """temperature=1.5 → MODEL_PARAM_OUT_OF_RANGE."""
    from fastapi import HTTPException

    from api.src.schemas.admin.prompts import ModelParamsUpdateRequest
    from api.src.services.prompt_config_service import update_model_params

    req_data = ModelParamsUpdateRequest(rag_k=5, rag_temperature=1.5, max_tokens=1024)
    request = MagicMock()
    request.state = MagicMock()
    admin = MagicMock()
    admin.id = 99
    db = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        await update_model_params(request, req_data, admin, db)

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == "MODEL_PARAM_OUT_OF_RANGE"


@pytest.mark.asyncio
async def test_update_model_params_success_upserts_4_keys():
    """정상 요청 → DB UPSERT 4건(rag_k/temp/max_tokens/max_question_chars) + Redis 갱신 시도."""
    from api.src.models.model_param_config import ModelParamConfig
    from api.src.schemas.admin.prompts import ModelParamsUpdateRequest
    from api.src.services.prompt_config_service import update_model_params

    req_data = ModelParamsUpdateRequest(
        rag_k=8, rag_temperature=0.3, max_tokens=2048, max_question_chars=1500
    )

    request = MagicMock()
    request.state = MagicMock()
    admin = MagicMock()
    admin.id = 99

    existing_k = MagicMock(spec=ModelParamConfig)
    existing_k.key = "rag_k"
    existing_k.value_json = 5

    existing_temp = MagicMock(spec=ModelParamConfig)
    existing_temp.key = "rag_temperature"
    existing_temp.value_json = 0.0

    existing_tokens = MagicMock(spec=ModelParamConfig)
    existing_tokens.key = "max_tokens"
    existing_tokens.value_json = 1024

    existing_qchars = MagicMock(spec=ModelParamConfig)
    existing_qchars.key = "max_question_chars"
    existing_qchars.value_json = 2000

    execute_results = []
    for existing in [existing_k, existing_temp, existing_tokens, existing_qchars]:
        r = MagicMock()
        r.scalar_one_or_none.return_value = existing
        execute_results.append(r)

    db = MagicMock()
    db.execute = AsyncMock(side_effect=execute_results)
    db.commit = AsyncMock()
    db.add = MagicMock()

    with patch("api.src.services.prompt_config_service._get_redis") as mock_get_redis:
        mock_redis = AsyncMock()
        mock_redis.__aenter__ = AsyncMock(return_value=mock_redis)
        mock_redis.__aexit__ = AsyncMock(return_value=False)
        mock_redis.mset = AsyncMock()
        mock_get_redis.return_value = mock_redis

        result = await update_model_params(request, req_data, admin, db)

    assert result.rag_k == 8
    assert result.rag_temperature == 0.3
    assert result.max_tokens == 2048
    assert result.max_question_chars == 1500
    db.commit.assert_awaited_once()
    # 기존 값이 있으므로 db.add는 호출되지 않음
    db.add.assert_not_called()
    # audit diff 설정 확인
    assert request.state.audit_target_type == "rag_model_params"


@pytest.mark.asyncio
async def test_update_prompt_block_not_found():
    """존재하지 않는 block_id → PROMPT_BLOCK_NOT_FOUND."""
    from fastapi import HTTPException

    from api.src.services.prompt_config_service import update_prompt

    r = MagicMock()
    r.scalar_one_or_none.return_value = None
    db = MagicMock()
    db.execute = AsyncMock(return_value=r)

    request = MagicMock()
    request.state = MagicMock()
    admin = MagicMock()
    admin.id = 99

    with pytest.raises(HTTPException) as exc_info:
        await update_prompt(request, "없음", "내용", True, admin, db)

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == "PROMPT_BLOCK_NOT_FOUND"


@pytest.mark.asyncio
async def test_update_prompt_empty_content():
    """빈 content → PROMPT_CONTENT_EMPTY."""
    from fastapi import HTTPException

    from api.src.models.prompt_module_config import PromptModuleConfig
    from api.src.services.prompt_config_service import update_prompt

    existing = MagicMock(spec=PromptModuleConfig)
    existing.block_id = "BASE"
    existing.content = "기존내용"
    existing.enabled = True

    r = MagicMock()
    r.scalar_one_or_none.return_value = existing
    db = MagicMock()
    db.execute = AsyncMock(return_value=r)

    request = MagicMock()
    request.state = MagicMock()
    admin = MagicMock()
    admin.id = 99

    with pytest.raises(HTTPException) as exc_info:
        await update_prompt(request, "BASE", "   ", True, admin, db)

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == "PROMPT_CONTENT_EMPTY"
