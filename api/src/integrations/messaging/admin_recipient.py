"""관리자 알림톡 수신자 resolve 헬퍼.

발송 대상은 DB의 운영 관리자 계정(`admin@denvia.ai.kr`) 단 하나만 본다.
환경변수 폴백·다중 폴백 모두 사용하지 않는다.

운영 관리자가 관리자 페이지에서 자기 계정의 phone을 직접 등록한다.
phone이 비어 있으면 silent skip — 알림톡 발송 건너뛴다(에러 안 던짐).

호출처: budget_tasks(예산 경고), routers.support(신규 1:1 문의 알림),
services.anomaly_service(이상탐지 차단 알림), workers.rag_tasks(RAG 재빌드 알림).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.user import User


ADMIN_RECIPIENT_EMAIL: str = "admin@denvia.ai.kr"


async def resolve_admin_target(
    session: AsyncSession,
) -> tuple[User | None, str | None]:
    user = (
        await session.execute(
            select(User).where(
                User.email == ADMIN_RECIPIENT_EMAIL,
                User.role == "admin",
                User.withdrawn_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if user and user.phone:
        return user, user.phone
    return None, None


__all__ = ["resolve_admin_target", "ADMIN_RECIPIENT_EMAIL"]
