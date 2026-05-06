"""감사 로그 조회 엔드포인트 — Story 5.1 (AC-7) + Story 6.2 (action_in/target_id/email JOIN).

Story 6.2 신규 기능:
- action_in: 콤마 구분 액션 다중 필터 (예: user.permission_edit,user.block_auto_expired).
  단일 LIKE 기반 action_filter는 backward-compat 유지 — action_in 우선.
- target_id: 정확 매칭 필터 (UserDetailDrawer "이력 보기" 진입 시).
- actor_email/target_email: 응답에 users JOIN 결과 포함 (N+1 회피 — 페이지 단위 IN 1쿼리).
"""

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


def _parse_action_in(action_in: str | None) -> list[str]:
    """콤마 구분 문자열 → 액션 리스트. 빈 토큰은 제거."""
    if not action_in:
        return []
    return [token.strip() for token in action_in.split(",") if token.strip()]


@router.get("/audit-logs", response_model=AuditLogListResponse)
async def list_audit_logs(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    action_filter: str = Query(""),
    action_in: str | None = Query(
        None,
        description="콤마 구분 액션 다중 필터 (Story 6.2). 우선순위 > action_filter.",
    ),
    actor_filter: int | None = Query(None),
    target_id: int | None = Query(
        None, description="target_id 정확 매칭 (Story 6.2 — UserDetailDrawer 이력 진입)"
    ),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """감사 로그 목록 조회 — 이 엔드포인트 자체는 audit_logs에 INSERT하지 않음."""
    base_q = select(AuditLog)

    actions = _parse_action_in(action_in)
    if actions:
        base_q = base_q.where(AuditLog.action.in_(actions))
        if action_filter:
            logger.warning(
                "admin.audit_logs.both_filters_specified",
                action_in=actions,
                action_filter=action_filter,
                resolution="action_in_wins",
            )
    elif action_filter:
        base_q = base_q.where(AuditLog.action.like(f"%{action_filter}%"))

    if actor_filter is not None:
        base_q = base_q.where(AuditLog.actor_user_id == actor_filter)

    if target_id is not None:
        base_q = base_q.where(AuditLog.target_id == target_id)

    count_q = select(func.count()).select_from(base_q.subquery())
    total_result = await db.execute(count_q)
    total = total_result.scalar_one()

    items_q = (
        base_q.order_by(AuditLog.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    rows = await db.execute(items_q)
    items = list(rows.scalars().all())

    # 응답 직렬화 — actor_email / target_email JOIN (N+1 회피, page 단위 IN 1쿼리)
    user_ids: set[int] = set()
    for log in items:
        user_ids.add(log.actor_user_id)
        if log.target_type == "user" and log.target_id is not None:
            user_ids.add(log.target_id)

    email_map: dict[int, str] = {}
    if user_ids:
        email_rows = (
            await db.execute(
                select(User.id, User.email).where(User.id.in_(user_ids))
            )
        ).all()
        email_map = {row.id: row.email for row in email_rows}

    response_items: list[AuditLogItem] = []
    for log in items:
        actor_email = email_map.get(log.actor_user_id)
        target_email: str | None = None
        if log.target_type == "user" and log.target_id is not None:
            target_email = email_map.get(log.target_id)
        # ip 컬럼은 INET 타입 → ipaddress.IPv4Address/IPv6Address 객체 — 응답은 str로 직렬화
        ip_str: str | None = str(log.ip) if log.ip is not None else None
        response_items.append(
            AuditLogItem(
                id=log.id,
                actor_user_id=log.actor_user_id,
                actor_email=actor_email,
                action=log.action,
                target_type=log.target_type,
                target_id=log.target_id,
                target_email=target_email,
                diff_json=log.diff_json,
                ip=ip_str,
                ua=log.ua,
                trace_id=log.trace_id,
                created_at=log.created_at,
            )
        )

    logger.info("admin.audit_logs.queried", page=page, total=total)

    return AuditLogListResponse(
        items=response_items,
        page=page,
        per_page=per_page,
        total=total,
    )
