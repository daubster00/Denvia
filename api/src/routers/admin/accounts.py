"""Story 10.3 — 관리자 계정 관리 라우터 `/api/v1/admin/accounts`.

6개 엔드포인트(모두 require_admin_grade('master','operator')):
- GET    /admin/accounts                       — 목록
- POST   /admin/accounts/{user_id}/approve     — pending → sub_operator/operator
- POST   /admin/accounts/{user_id}/block       — 일시 차단
- POST   /admin/accounts/{user_id}/unblock     — 차단 해제
- DELETE /admin/accounts/{user_id}             — 소프트 삭제
- PATCH  /admin/accounts/{user_id}             — 등급 변경

audit_logs INSERT 는 AuditMiddleware 가 처리한다. 각 라우트에서
request.state.audit_action / audit_target_type / audit_target_id / audit_diff 설정.

권한 가드 + 등급 제약은 admin_account_service 에 집약되어 있다.
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.deps.auth import require_admin_grade
from api.src.middleware.audit_actions import audit_action
from api.src.models.base import get_session
from api.src.models.user import User
from api.src.schemas.admin.log import (
    AdminLogDiffResponse,
    AdminLogListResponse,
)
from api.src.services import admin_account_service, admin_logs_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin/accounts", tags=["admin-accounts"])

# ── audit action 코드 (Story 10.3 신규) ─────────────────────────────────────
AUDIT_ADMIN_ACCOUNT_APPROVED = "admin.account.approved"
AUDIT_ADMIN_ACCOUNT_BLOCKED = "admin.account.blocked"
AUDIT_ADMIN_ACCOUNT_UNBLOCKED = "admin.account.unblocked"
AUDIT_ADMIN_ACCOUNT_DELETED = "admin.account.deleted"
AUDIT_ADMIN_ACCOUNT_GRADE_UPDATED = "admin.account.grade_updated"

GradeName = Literal["master", "operator", "sub_operator", "pending"]
ListFilterName = Literal["all", "pending", "active", "blocked"]


# ── 응답 스키마 ──────────────────────────────────────────────────────────────


class AdminAccountListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    admin_grade: GradeName
    grade_label: str
    phone_masked: str | None
    admin_blocked_until: datetime | None
    admin_block_reason: str | None
    admin_signup_at: datetime | None
    last_login_at: datetime | None
    created_at: datetime


class AdminAccountListResponse(BaseModel):
    items: list[AdminAccountListItem]
    total: int


class ApproveRequest(BaseModel):
    target_grade: Literal["sub_operator", "operator"]


class BlockRequest(BaseModel):
    blocked_until: datetime
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


class PatchRequest(BaseModel):
    admin_grade: GradeName | None = None


# ── 엔드포인트 ────────────────────────────────────────────────────────────────


@router.get("", response_model=AdminAccountListResponse)
async def list_accounts(
    request: Request,
    filter: ListFilterName = Query("all", description="all / pending / active / blocked"),
    admin: User = Depends(require_admin_grade("master", "operator")),
    db: AsyncSession = Depends(get_session),
) -> AdminAccountListResponse:
    """관리자 목록 — master/operator 모두 조회 가능. operator 도 master 행을 보지만
    프론트는 액션 버튼 비활성으로 처리(서비스 가드가 변경 액션을 거부)."""
    rows = await admin_account_service.list_admins(db, actor=admin, list_filter=filter)
    logger.info(
        "admin.accounts.listed",
        actor_user_id=admin.id,
        filter=filter,
        total=len(rows),
        trace_id=str(getattr(request.state, "trace_id", "")),
    )
    return AdminAccountListResponse(
        items=[AdminAccountListItem.model_validate(r) for r in rows],
        total=len(rows),
    )


@router.post("/{user_id}/approve", response_model=AdminAccountListItem)
@audit_action(AUDIT_ADMIN_ACCOUNT_APPROVED)
async def approve_account(
    request: Request,
    user_id: int,
    body: ApproveRequest,
    admin: User = Depends(require_admin_grade("master", "operator")),
    db: AsyncSession = Depends(get_session),
) -> AdminAccountListItem:
    result = await admin_account_service.approve_pending(
        db, actor=admin, target_user_id=user_id, target_grade=body.target_grade
    )
    await db.commit()

    request.state.audit_target_type = "user"
    request.state.audit_target_id = user_id
    request.state.audit_diff = result["diff"]
    return AdminAccountListItem.model_validate(result["row"])


@router.post("/{user_id}/block", response_model=AdminAccountListItem)
@audit_action(AUDIT_ADMIN_ACCOUNT_BLOCKED)
async def block_account(
    request: Request,
    user_id: int,
    body: BlockRequest,
    admin: User = Depends(require_admin_grade("master", "operator")),
    db: AsyncSession = Depends(get_session),
) -> AdminAccountListItem:
    result = await admin_account_service.block_admin(
        db,
        actor=admin,
        target_user_id=user_id,
        blocked_until=body.blocked_until,
        reason=body.reason,
    )
    await db.commit()

    request.state.audit_target_type = "user"
    request.state.audit_target_id = user_id
    request.state.audit_diff = result["diff"]
    return AdminAccountListItem.model_validate(result["row"])


@router.post("/{user_id}/unblock", response_model=AdminAccountListItem)
@audit_action(AUDIT_ADMIN_ACCOUNT_UNBLOCKED)
async def unblock_account(
    request: Request,
    user_id: int,
    admin: User = Depends(require_admin_grade("master", "operator")),
    db: AsyncSession = Depends(get_session),
) -> AdminAccountListItem:
    result = await admin_account_service.unblock_admin(
        db, actor=admin, target_user_id=user_id
    )
    await db.commit()

    request.state.audit_target_type = "user"
    request.state.audit_target_id = user_id
    request.state.audit_diff = result["diff"]
    return AdminAccountListItem.model_validate(result["row"])


@router.delete("/{user_id}", status_code=200)
@audit_action(AUDIT_ADMIN_ACCOUNT_DELETED)
async def delete_account(
    request: Request,
    user_id: int,
    admin: User = Depends(require_admin_grade("master", "operator")),
    db: AsyncSession = Depends(get_session),
) -> dict:
    result = await admin_account_service.delete_admin(
        db, actor=admin, target_user_id=user_id
    )
    await db.commit()

    request.state.audit_target_type = "user"
    request.state.audit_target_id = user_id
    request.state.audit_diff = result["diff"]
    return {"ok": True}


@router.patch("/{user_id}", response_model=AdminAccountListItem)
@audit_action(AUDIT_ADMIN_ACCOUNT_GRADE_UPDATED)
async def patch_account(
    request: Request,
    user_id: int,
    body: PatchRequest,
    admin: User = Depends(require_admin_grade("master", "operator")),
    db: AsyncSession = Depends(get_session),
) -> AdminAccountListItem:
    if body.admin_grade is None:
        raise HTTPException(
            422,
            detail={
                "code": "ADMIN_GRADE_REQUIRED",
                "message": "변경할 등급을 지정해주세요.",
            },
        )
    result = await admin_account_service.update_admin_grade(
        db, actor=admin, target_user_id=user_id, new_grade=body.admin_grade
    )
    await db.commit()

    request.state.audit_target_type = "user"
    request.state.audit_target_id = user_id
    request.state.audit_diff = result["diff"]
    return AdminAccountListItem.model_validate(result["row"])


# ── Story 10.4 — 활동 로그 조회 (GET-only, audit INSERT 0건) ─────────────────


def _parse_actor_id(actor_id: str | None) -> int | Literal["system"] | None:
    if actor_id is None or actor_id == "":
        return None
    if actor_id == "system":
        return "system"
    try:
        return int(actor_id)
    except ValueError as exc:
        raise HTTPException(
            422,
            detail={
                "code": "INVALID_ACTOR_ID",
                "message": "actor_id must be int or 'system'",
            },
        ) from exc


def _parse_action_in(action_in: str | None) -> list[str] | None:
    if not action_in:
        return None
    codes = [c.strip() for c in action_in.split(",") if c.strip()]
    if not codes:
        return None
    if len(codes) > 50:
        raise HTTPException(
            422,
            detail={
                "code": "INVALID_ACTION_IN",
                "message": "action_in supports up to 50 codes",
            },
        )
    return codes


@router.get("/logs", response_model=AdminLogListResponse)
async def list_logs(
    request: Request,
    actor_id: str | None = Query(None, description="int 또는 'system' 또는 미지정"),
    action_in: str | None = Query(None, description="comma-separated action codes"),
    from_at: datetime | None = Query(None),
    to_at: datetime | None = Query(None),
    target_id: int | None = Query(None),
    cursor: str | None = Query(None),
    limit: int = Query(100, ge=1, le=200),
    admin: User = Depends(require_admin_grade("master", "operator")),
    db: AsyncSession = Depends(get_session),
) -> AdminLogListResponse:
    parsed_actor_id = _parse_actor_id(actor_id)
    actions = _parse_action_in(action_in)
    result = await admin_logs_service.list_logs(
        db,
        actor=admin,
        actor_id=parsed_actor_id,
        action_in=actions,
        from_at=from_at,
        to_at=to_at,
        target_id=target_id,
        cursor=cursor,
        limit=limit,
    )
    logger.info(
        "admin.accounts.logs.listed",
        actor_user_id=admin.id,
        items=len(result["items"]),
        has_next=result["next_cursor"] is not None,
        trace_id=str(getattr(request.state, "trace_id", "")),
    )
    return AdminLogListResponse(**result)


@router.get("/logs/{log_id}/diff", response_model=AdminLogDiffResponse)
async def get_log_diff(
    log_id: int,
    admin: User = Depends(require_admin_grade("master", "operator")),
    db: AsyncSession = Depends(get_session),
) -> AdminLogDiffResponse:
    result = await admin_logs_service.get_log_diff(db, admin, log_id)
    return AdminLogDiffResponse(**result)


@router.get("/logs/export.xlsx")
async def export_logs(
    actor_id: str | None = Query(None),
    action_in: str | None = Query(None),
    from_at: datetime | None = Query(None),
    to_at: datetime | None = Query(None),
    target_id: int | None = Query(None),
    admin: User = Depends(require_admin_grade("master", "operator")),
    db: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    parsed_actor_id = _parse_actor_id(actor_id)
    actions = _parse_action_in(action_in)
    buf, filename, truncated = await admin_logs_service.export_logs_xlsx(
        db,
        actor=admin,
        actor_id=parsed_actor_id,
        action_in=actions,
        from_at=from_at,
        to_at=to_at,
        target_id=target_id,
    )
    headers: dict[str, str] = {
        "Content-Disposition": f'attachment; filename="{filename}"',
    }
    if truncated:
        headers["X-Truncated"] = "true"
    logger.info(
        "admin.accounts.logs.exported",
        actor_user_id=admin.id,
        truncated=truncated,
    )
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )
