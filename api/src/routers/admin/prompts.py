"""프롬프트 블록 + 모델 파라미터 관리 라우터 — Story 8.4 (A-404)."""

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.deps.auth import require_admin, require_admin_page
from api.src.middleware.audit_actions import (
    AUDIT_MODEL_PARAMS_EDIT,
    AUDIT_PROMPT_CREATE,
    AUDIT_PROMPT_DELETE,
    AUDIT_PROMPT_EDIT,
    AUDIT_PROMPT_MODEL_ROUTE_UPDATE,
    audit_action,
)
from api.src.models.base import get_session
from api.src.models.user import User
from api.src.schemas.admin.prompts import (
    ModelParamsResponse,
    ModelParamsUpdateRequest,
    PromptCreateRequest,
    PromptModelRoutesResponse,
    PromptModelRoutesUpdateRequest,
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


@router.post(
    "/prompts",
    response_model=PromptUpdateResponse,
    status_code=status.HTTP_201_CREATED,
)
@audit_action(AUDIT_PROMPT_CREATE)
async def create_prompt(
    body: PromptCreateRequest,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> PromptUpdateResponse:
    return await prompt_config_service.create_prompt_block(
        request,
        body.block_id,
        body.content,
        body.enabled,
        body.trigger_config,
        admin,
        db,
        suppresses=body.suppresses,
    )


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
        suppresses=body.suppresses,
    )


@router.delete("/prompts/{block_id}", status_code=status.HTTP_204_NO_CONTENT)
@audit_action(AUDIT_PROMPT_DELETE)
async def delete_prompt(
    block_id: str,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> None:
    await prompt_config_service.delete_prompt_block(request, block_id, admin, db)


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


# ── 특정 프롬프트 모델 라우팅 ─────────────────────────────────────────────────
# 관리자가 고른 프롬프트 블록이 사용자 질문으로 "실제 주입"됐을 때만 다른 모델을 쓴다.
# 지정은 여러 개 가능하며, 목록 순서가 우선순위다(둘 이상 동시 주입 시 앞쪽이 이김).
# 그 외 모든 질문은 기존 기본 모델(runtime:chat_model) 그대로.


@router.get("/prompt-model-routes", response_model=PromptModelRoutesResponse)
async def get_prompt_model_routes(
    response: Response,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> PromptModelRoutesResponse:
    """현재 지정 목록 + 허용 모델 목록 조회 (프론트 드롭다운 옵션 소스)."""
    response.headers["Cache-Control"] = "no-store"
    return await prompt_config_service.get_prompt_model_routes(db)


@router.put("/prompt-model-routes", response_model=PromptModelRoutesResponse)
@audit_action(AUDIT_PROMPT_MODEL_ROUTE_UPDATE)
async def update_prompt_model_routes(
    body: PromptModelRoutesUpdateRequest,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> PromptModelRoutesResponse:
    """지정 목록 전체 교체 — 검증 위반 시 422 {code}. 저장 즉시 다음 질문부터 반영."""
    return await prompt_config_service.update_prompt_model_routes(
        request, body, admin, db
    )

