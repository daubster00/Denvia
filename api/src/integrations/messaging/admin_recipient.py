"""관리자 알림톡 수신자 resolve 헬퍼.

Story 10.3 이후 마스터 식별은 `users.admin_grade='master'` DB 컬럼으로 한다
(partial UNIQUE 로 최대 1건 보장). 우선순위:
1) master 등급 활성 관리자의 users.phone — phone NOT NULL일 때.
2) settings.denvia_admin_phone (.env DENVIA_ADMIN_PHONE) — 운영 폴백.
   User row는 master 행이 있으면 master, 없으면 role='admin' 첫 행을 동봉.
3) DB에서 role='admin' AND phone IS NOT NULL인 가장 빠른 id의 row.

호출처: budget_tasks(예산 경고), routers.support(신규 1:1 문의 알림),
services.anomaly_service(이상탐지 차단 알림).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.user import User
from api.src.settings import settings


async def resolve_admin_target(
    session: AsyncSession,
) -> tuple[User | None, str | None]:
    # 1순위 — master 등급 활성 관리자의 휴대폰
    master = (
        await session.execute(
            select(User).where(
                User.admin_grade == "master",
                User.role == "admin",
                User.withdrawn_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if master and master.phone:
        return master, master.phone

    # 2순위 — .env DENVIA_ADMIN_PHONE (운영 폴백)
    env_phone = settings.denvia_admin_phone
    if env_phone:
        admin = master or (
            await session.execute(
                select(User).where(User.role == "admin").order_by(User.id).limit(1)
            )
        ).scalar_one_or_none()
        if admin:
            return admin, env_phone

    # 3순위 — role='admin' AND phone NOT NULL 첫 행
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
