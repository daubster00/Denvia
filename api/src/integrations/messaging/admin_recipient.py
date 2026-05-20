"""관리자 알림톡 수신자 resolve 헬퍼.

denvia 관리자 단일 운영(메모리: project_denvia_ssot_hierarchy). 우선순위:
1) settings.denvia_admin_phone (.env) — User row는 role='admin' 첫 행을 동봉.
2) 환경변수 미설정 시 DB에서 role='admin' AND phone IS NOT NULL 첫 행.

호출처: budget_tasks(예산 경고), routers.support(신규 1:1 문의 알림),
services.anomaly_service(이상탐지 알림). budget_tasks 는 자체 동일 패턴을 유지하므로
중복은 후속 정리 시 일원화.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.user import User
from api.src.settings import settings


async def resolve_admin_target(
    session: AsyncSession,
) -> tuple[User | None, str | None]:
    env_phone = settings.denvia_admin_phone
    if env_phone:
        admin = (
            await session.execute(
                select(User).where(User.role == "admin").order_by(User.id).limit(1)
            )
        ).scalar_one_or_none()
        if admin:
            return admin, env_phone
    admin = (
        await session.execute(
            select(User)
            .where(User.role == "admin", User.phone.is_not(None))
            .order_by(User.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    return admin, (admin.phone if admin else None)


__all__ = ["resolve_admin_target"]
