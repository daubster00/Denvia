"""프롬프트 블록 + 모델 파라미터 관리 라우터 — Story 8.4 (A-404)."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.deps.auth import require_admin, require_admin_page
from api.src.middleware.audit_actions import (
    AUDIT_MODEL_PARAMS_EDIT,
    AUDIT_PROMPT_EDIT,
    audit_action,
)
from api.src.models.base import get_session
from api.src.models.user import User
from api.src.schemas.admin.prompts import (
    ModelParamsResponse,
    ModelParamsUpdateRequest,
    PromptsListResponse,
    PromptUpdateRequest,
    PromptUpdateResponse,
)
from api.src.services import prompt_config_service

router = APIRouter(
    prefix="/admin/rag",
    tags=["admin-rag"],
    dependencies=[Depends(require_admin_page("/admin/rag"))],
)


@router.get("/prompts", response_model=PromptsListResponse)
async def get_prompts(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> PromptsListResponse:
    return await prompt_config_service.get_prompts(db)


@router.put("/prompts/{block_id}", response_model=PromptUpdateResponse)
@audit_action(AUDIT_PROMPT_EDIT)
async def update_prompt(
    block_id: str,
    body: PromptUpdateRequest,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> PromptUpdateResponse:
    return await prompt_config_service.update_prompt(
        request, block_id, body.content, body.enabled, admin, db,
        trigger_config=body.trigger_config,
    )


@router.get("/model-params", response_model=ModelParamsResponse)
async def get_model_params(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> ModelParamsResponse:
    return await prompt_config_service.get_model_params(db)


@router.put("/model-params", response_model=ModelParamsResponse)
@audit_action(AUDIT_MODEL_PARAMS_EDIT)
async def update_model_params(
    body: ModelParamsUpdateRequest,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> ModelParamsResponse:
    return await prompt_config_service.update_model_params(request, body, admin, db)
