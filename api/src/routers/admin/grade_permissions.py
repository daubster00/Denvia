"""Story 10.5 — 등급별 페이지 접근 권한 매트릭스 라우터.

- GET   /api/v1/admin/grade-permissions      — 매트릭스 조회 (master/operator)
- PATCH /api/v1/admin/grade-permissions      — 단일 셀 UPSERT (master 전용)

master 등급 행 자체는 본 테이블에 들어가지 않는다 — UI 도 master 컬럼을 노출하지 않는다.
audit_logs 는 AuditMiddleware 가 처리.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.deps.auth import require_admin_grade
from api.src.middleware.audit_actions import audit_action
from api.src.models.base import get_session
from api.src.models.user import User
from api.src.schemas.admin.grade_permission import (
    GradePermissionRow,
    MatrixResponse,
    PageMeta,
    UpdateRequest,
)
from api.src.services import admin_grade_permission_service


logger = structlog.get_logger(__name__)

AUDIT_ADMIN_GRADE_PERMISSION_UPDATED = "admin.grade_permission.updated"

router = APIRouter(prefix="/admin/grade-permissions", tags=["admin-grade-permissions"])


@router.get("", response_model=MatrixResponse)
async def get_grade_permissions(
    request: Request,
    admin: User = Depends(require_admin_grade("master", "operator")),
    db: AsyncSession = Depends(get_session),
) -> MatrixResponse:
    matrix = await admin_grade_permission_service.get_matrix(db)
    logger.info(
        "admin.grade_permission.listed",
        actor_user_id=admin.id,
        rows=len(matrix["rows"]),
        trace_id=str(getattr(request.state, "trace_id", "")),
    )
    return MatrixResponse(
        pages=[PageMeta(**p) for p in matrix["pages"]],
        grades=matrix["grades"],
        rows=[GradePermissionRow(**r) for r in matrix["rows"]],
    )


@router.patch("", response_model=GradePermissionRow)
@audit_action(AUDIT_ADMIN_GRADE_PERMISSION_UPDATED)
async def patch_grade_permission(
    request: Request,
    body: UpdateRequest,
    admin: User = Depends(require_admin_grade("master", "operator")),
    db: AsyncSession = Depends(get_session),
) -> GradePermissionRow:
    result = await admin_grade_permission_service.upsert_permission(
        db,
        actor=admin,
        admin_grade=body.admin_grade,
        page_route=body.page_route,
        allowed=body.allowed,
    )
    await db.commit()

    request.state.audit_target_type = "admin_grade_page_permission"
    # 행 식별을 위한 합성 target — "operator:/admin/users" 형태
    request.state.audit_target_id = None
    request.state.audit_diff = result["diff"]
    return GradePermissionRow(**result["row"])
