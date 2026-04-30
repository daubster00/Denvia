"""KillswitchService — 활성 mode 조회 / auto_free_only INSERT·해제 헬퍼."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.killswitch_state import (
    KillswitchState,
    MODE_AUTO_FREE_ONLY,
    MODE_MANUAL_TOTAL,
)


async def get_active_modes(session: AsyncSession) -> set[str]:
    rows = (await session.execute(
        select(KillswitchState.mode).where(KillswitchState.deactivated_at.is_(None))
    )).scalars().all()
    return set(rows)


async def is_auto_free_only_active(session: AsyncSession) -> bool:
    return MODE_AUTO_FREE_ONLY in await get_active_modes(session)


async def is_any_total_block_active(session: AsyncSession) -> bool:
    return MODE_MANUAL_TOTAL in await get_active_modes(session)
