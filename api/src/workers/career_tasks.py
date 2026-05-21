"""연차(years_of_experience) 자동 +1 가산 Celery 태스크.

정책:
- 매년 1월 1일 00:05 KST Beat 트리거(`career_tasks.annual_increment`).
- 대상: `years_of_experience IS NOT NULL` 이고 `experience_last_increment_year < <올해 KST 연도>` 인 회원.
- 갱신: `years_of_experience += (올해 - experience_last_increment_year)` (catch-up),
        `experience_last_increment_year = 올해`.
- 멱등성: 같은 KST 연도에 두 번 실행돼도 두 번째 실행은 0건 처리.
- 신규 가입자(올해 set_segment 한 회원)는 last_increment_year=올해 이므로 조건 미충족 → +1 안 됨.
- audit_logs INSERT 하지 않음(시스템 자동 동작·전체 회원 일괄 처리). structlog에만 기록.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.src.models.user import User
from api.src.settings import settings
from api.src.utils.korean_time import now_kst
from api.src.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(name="career_tasks.annual_increment")
def annual_increment() -> dict:
    """매년 1월 1일 00:05 KST 호출 — 동기 wrapper."""
    return asyncio.run(_annual_increment_async())


async def _annual_increment_async() -> dict[str, Any]:
    current_year = now_kst().year
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            # 대상 카운트 (로그용)
            target_count = (
                await session.execute(
                    select(func.count())
                    .select_from(User)
                    .where(
                        User.years_of_experience.is_not(None),
                        User.experience_last_increment_year.is_not(None),
                        User.experience_last_increment_year < current_year,
                    )
                )
            ).scalar_one()

            if target_count == 0:
                logger.info(
                    "career.annual_increment.empty",
                    current_year=current_year,
                )
                return {"incremented_count": 0, "current_year": current_year}

            now_utc = datetime.now(tz=timezone.utc)
            result = await session.execute(
                update(User)
                .where(
                    User.years_of_experience.is_not(None),
                    User.experience_last_increment_year.is_not(None),
                    User.experience_last_increment_year < current_year,
                )
                .values(
                    years_of_experience=(
                        User.years_of_experience
                        + (current_year - User.experience_last_increment_year)
                    ),
                    experience_last_increment_year=current_year,
                    updated_at=now_utc,
                )
            )
            await session.commit()

            logger.info(
                "career.annual_increment.done",
                incremented_count=result.rowcount,
                current_year=current_year,
            )
            return {
                "incremented_count": result.rowcount,
                "current_year": current_year,
            }
    finally:
        await engine.dispose()
