"""관리자 등급 CRUD 라우터 — /api/v1/admin/grades.

엔드포인트:
- GET    /admin/grades              — 내장 + 커스텀 등급 목록 (master/operator 모두 조회 가능)
- POST   /admin/grades               — 커스텀 등급 추가 (master/operator)
- DELETE /admin/grades/{code}        — 커스텀 등급 삭제 (master/operator, 사용자 0명일 때만)

audit_logs INSERT 는 AuditMiddleware 가 처리.
"""

from __future__ import annotations

from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.deps.auth import require_admin_grade
from api.src.middleware.audit_actions import audit_action
from api.src.models.base import get_session
from api.src.models.user import User
from api.src.services import admin_grade_service


logger = structlog.get_logger(__name__)

AUDIT_ADMIN_GRADE_CREATED = "admin.grade.created"
AUDIT_ADMIN_GRADE_DELETED = "admin.grade.deleted"

router = APIRouter(prefix="/admin/grades", tags=["admin-grades"])


class GradeListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    label: str
    is_builtin: bool
    user_count: int
    created_at: datetime


class GradeListResponse(BaseModel):
    items: list[GradeListItem]


class CreateRequest(BaseModel):
    label: str = Field(min_length=1, max_length=32)

    @field_validator("label")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


@router.get("", response_model=GradeListResponse)
async def list_grades(
    request: Request,
    admin: User = Depends(require_admin_grade("master", "operator")),
    db: AsyncSession = Depends(get_session),
) -> GradeListResponse:
    rows = await admin_grade_service.list_grades(db)
    logger.info(
        "admin.grades.listed",
        actor_user_id=admin.id,
        total=len(rows),
        trace_id=str(getattr(request.state, "trace_id", "")),
    )
    return GradeListResponse(
        items=[GradeListItem.model_validate(r) for r in rows]
    )


@router.post("", response_model=GradeListItem, status_code=201)
@audit_action(AUDIT_ADMIN_GRADE_CREATED)
async def create_grade(
    request: Request,
    body: CreateRequest,
    admin: User = Depends(require_admin_grade("master", "operator")),
    db: AsyncSession = Depends(get_session),
) -> GradeListItem:
    result = await admin_grade_service.create_grade(
        db, actor=admin, label=body.label
    )
    await db.commit()

    request.state.audit_target_type = "admin_grade"
    request.state.audit_target_id = None
    request.state.audit_diff = result["diff"]
    return GradeListItem.model_validate(result["row"])


@router.delete("/{code}", status_code=200)
@audit_action(AUDIT_ADMIN_GRADE_DELETED)
async def delete_grade(
    request: Request,
    code: str,
    admin: User = Depends(require_admin_grade("master", "operator")),
    db: AsyncSession = Depends(get_session),
) -> dict:
    result = await admin_grade_service.delete_grade(
        db, actor=admin, code=code
    )
    await db.commit()

    request.state.audit_target_type = "admin_grade"
    request.state.audit_target_id = None
    request.state.audit_diff = result["diff"]
    return {"ok": True}
