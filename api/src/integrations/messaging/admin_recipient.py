"""관리자 알림톡 수신자 resolve 헬퍼.

발송 대상은 DB 의 관리자 계정 두 개만 본다 — 환경변수 폴백은 사용하지 않는다.

우선순위(2-tier):
1) `btmdesign@naver.com` (개발자 본인 계정) 의 users.phone — 개발 중 알림톡 수신 테스트용.
2) `admin@denvia.ai.kr` (운영 관리자 계정) 의 users.phone — 클라이언트 인수 후 사용.

운영 전환 시 btmdesign 계정의 phone 을 NULL 로 비우면 자동으로 2순위로 폴백된다.

`uq_users_phone_admin` partial UNIQUE 제약 때문에 두 계정에 동일한 phone 을 동시에
넣을 수 없으므로 위 폴백 방식이 유일한 안전한 경로다.

호출처: budget_tasks(예산 경고), routers.support(신규 1:1 문의 알림),
services.anomaly_service(이상탐지 차단 알림), workers.rag_tasks(RAG 재빌드 알림).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.user import User


ADMIN_RECIPIENT_EMAILS: tuple[str, ...] = (
    "btmdesign@naver.com",
    "admin@denvia.ai.kr",
)


async def resolve_admin_target(
    session: AsyncSession,
) -> tuple[User | None, str | None]:
    for email in ADMIN_RECIPIENT_EMAILS:
        user = (
            await session.execute(
                select(User).where(
                    User.email == email,
                    User.role == "admin",
                    User.withdrawn_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if user and user.phone:
            return user, user.phone
    return None, None


__all__ = ["resolve_admin_target", "ADMIN_RECIPIENT_EMAILS"]
