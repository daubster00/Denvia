"""Story 6.2 — 이상탐지 자동 처리 Celery 태스크 모듈.

본 모듈은 Story 6.2에서 expire_blocks 1개 함수만 보유한다.
Story 6.5(이상탐지 자동 생성)에서 같은 모듈에 함수가 추가될 예정 — 모듈 골격을 본 스토리에서 마련.

`expire_blocks`:
- 매시간 정각 0분에 Celery Beat가 트리거 (celery_app.py).
- subscription_status='blocked' AND blocked_until <= now() 인 사용자를 free로 reset.
- 영구 차단(blocked_until IS NULL)은 자동 해제 대상에서 제외.
- 각 expire 사용자에 대해 audit_logs 'user.block_auto_expired' INSERT.
- actor_user_id는 첫 번째 admin user의 id 사용 (FK ON DELETE RESTRICT 정합).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.src.middleware.audit_actions import AUDIT_USER_BLOCK_AUTO_EXPIRED
from api.src.models.audit_log import AuditLog
from api.src.models.user import User
from api.src.settings import settings
from api.src.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(name="anomaly_tasks.expire_blocks")
def expire_blocks() -> dict:
    """매시간 정각 호출 — 동기 wrapper."""
    return asyncio.run(_expire_blocks_async())


async def _resolve_system_actor_id(session) -> int | None:
    """SYSTEM_ACTOR_USER_ID 결정.

    `audit_logs.actor_user_id`는 ON DELETE RESTRICT로 `users.id`를 강제한다.
    따라서 가상 ID(0)는 사용 불가 — 첫 번째 admin user의 id를 fallback으로 사용.
    `seed_admin`이 항상 admin user를 보장하므로(memory feedback_always_seed_admin)
    None은 비정상 상황이다.
    """
    row = (
        await session.execute(
            select(User.id)
            .where(User.role == "admin")
            .order_by(User.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    return row


async def _expire_blocks_async() -> dict[str, Any]:
    """차단 만료 일괄 처리.

    1. blocked_until <= now() AND subscription_status='blocked' 인 user 조회 (id+email)
    2. 일괄 update (status=free, blocked_until=NULL, block_reason=NULL)
    3. 각 expire user 마다 audit_logs INSERT
    """
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            now = datetime.now(tz=timezone.utc)

            # 1) 만료 후보 SELECT — id/email/pre_block_status 포함 (복원 상태 판단용)
            target_rows = (
                await session.execute(
                    select(User.id, User.email, User.pre_block_status).where(
                        User.subscription_status == "blocked",
                        User.blocked_until.is_not(None),
                        User.blocked_until <= now,
                    )
                )
            ).all()

            if not target_rows:
                logger.info("anomaly.expire_blocks.empty")
                return {"expired_count": 0}

            target_ids = [row.id for row in target_rows]

            # 2) actor_user_id resolve — admin user 첫 번째 id (캐시 단순화: 매 실행마다 1쿼리)
            actor_id = await _resolve_system_actor_id(session)
            if actor_id is None:
                logger.error(
                    "anomaly.expire_blocks.no_system_actor",
                    candidate_ids=target_ids,
                )
                return {"expired_count": 0, "error": "no_system_actor"}

            # 3) 차단 전 상태별로 분리해 일괄 UPDATE (pro 복원 vs free 복원)
            pro_ids = [row.id for row in target_rows if row.pre_block_status == "pro"]
            free_ids = [row.id for row in target_rows if row.pre_block_status != "pro"]

            base_values: dict = {
                "blocked_until": None,
                "block_reason": None,
                "pre_block_status": None,
                "updated_at": now,
            }
            if pro_ids:
                await session.execute(
                    update(User)
                    .where(User.id.in_(pro_ids))
                    .values(subscription_status="pro", **base_values)
                )
            if free_ids:
                await session.execute(
                    update(User)
                    .where(User.id.in_(free_ids))
                    .values(subscription_status="free", **base_values)
                )

            # 4) audit_logs INSERT — 각 user 마다 1행 (실제 복원 상태 반영)
            for row in target_rows:
                restored_status = "pro" if row.pre_block_status == "pro" else "free"
                session.add(
                    AuditLog(
                        actor_user_id=actor_id,
                        action=AUDIT_USER_BLOCK_AUTO_EXPIRED,
                        target_type="user",
                        target_id=row.id,
                        diff_json={
                            "before": {"subscription_status": "blocked"},
                            "after": {"subscription_status": restored_status},
                        },
                        ip=None,
                        ua=None,
                        trace_id=None,
                    )
                )

            await session.commit()

            logger.info(
                "anomaly.expire_blocks.done",
                expired_count=len(target_ids),
                actor_user_id=actor_id,
            )
            return {"expired_count": len(target_ids), "actor_user_id": actor_id}
    finally:
        await engine.dispose()
