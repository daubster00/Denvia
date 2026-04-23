"""유저 서비스 — DB 조회 래퍼."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.src.models.user import User


async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    """user_id로 활성 유저를 조회한다. 없으면 None."""
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
