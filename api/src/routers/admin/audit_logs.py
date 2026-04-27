"""감사 로그 조회 엔드포인트 — Story 5.1 (AC-7)."""

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.deps.auth import require_admin
from api.src.models.audit_log import AuditLog
from api.src.models.base import get_session
from api.src.models.user import User
from api.src.schemas.admin.audit_log import AuditLogItem, AuditLogListResponse

logger = structlog.get_logger()

router = APIRouter(prefix="/admin", tags=["admin-audit-logs"])


@router.get("/audit-logs", response_model=AuditLogListResponse)
async def list_audit_logs(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    action_filter: str = Query(""),
    actor_filter: int | None = Query(None),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """감사 로그 목록 조회 — 이 엔드포인트 자체는 audit_logs에 INSERT하지 않음."""
    base_q = select(AuditLog)
    if action_filter:
        base_q = base_q.where(AuditLog.action.like(f"%{action_filter}%"))
    if actor_filter is not None:
        base_q = base_q.where(AuditLog.actor_user_id == actor_filter)

    count_q = select(func.count()).select_from(base_q.subquery())
    total_result = await db.execute(count_q)
    total = total_result.scalar_one()

    items_q = (
        base_q.order_by(AuditLog.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    rows = await db.execute(items_q)
    items = rows.scalars().all()

    logger.info("admin.audit_logs.queried", page=page, total=total)

    return AuditLogListResponse(
        items=[AuditLogItem.model_validate(item) for item in items],
        page=page,
        per_page=per_page,
        total=total,
    )
