"""Story 6.2 — 이상탐지 자동 처리 Celery 태스크 모듈.

본 모듈은 Story 6.2에서 expire_blocks 1개 함수로 시작했고,
Story 10.3(2026-05-27)에서 동일 핸들러에 관리자 차단 자동 만료 분기가 추가됐다.

`expire_blocks`:
- 매시간 30분에 Celery Beat가 트리거 (celery_app.py).
- 사용자 분기 — subscription_status='blocked' AND blocked_until <= now() 인 사용자를 free/pro로 복원.
- 관리자 분기 — role='admin' AND admin_blocked_until <= now() 인 관리자의 차단을 해제.
- 영구 차단(*blocked_until IS NULL*)은 자동 해제 대상에서 제외.
- 사용자 분기는 'user.block_auto_expired' / 관리자 분기는 'admin.account.unblocked' audit_logs INSERT.
- actor_user_id는 첫 번째 admin user의 id 사용 (FK ON DELETE RESTRICT 정합 — NULL 불가).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.src.middleware.audit_actions import (
    AUDIT_ADMIN_ACCOUNT_UNBLOCKED,
    AUDIT_USER_BLOCK_AUTO_EXPIRED,
)
from api.src.models.audit_log import AuditLog
from api.src.models.inbox_message import InboxMessage
from api.src.models.user import User
from api.src.services import admin_account_service
from api.src.settings import settings
from api.src.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(name="anomaly_tasks.expire_blocks")
def expire_blocks() -> dict:
    """매시간 30분 호출 — 동기 wrapper."""
    block_result = asyncio.run(_expire_blocks_async())
    lock_result = asyncio.run(_expire_login_locks_async())
    return {**block_result, "login_lock_expired_count": lock_result.get("expired_count", 0)}


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
                # 사용자 분기는 비어있어도 관리자 차단 자동 만료는 별도 처리.
                actor_id_only = await _resolve_system_actor_id(session)
                admin_result = (
                    await _expire_admin_blocks(actor_id_only)
                    if actor_id_only is not None
                    else {"expired_count": 0, "expired_ids": []}
                )
                return {
                    "expired_count": 0,
                    "admin_expired_count": admin_result["expired_count"],
                    "admin_expired_ids": admin_result["expired_ids"],
                }

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

            # 5) 차단 해제 쪽지 발송
            inbox_msgs = [
                InboxMessage(
                    user_id=row.id,
                    notice_id=None,
                    popup_id=None,
                    type="system",
                    title="계정 차단 해제 안내",
                    body_html=(
                        "<p>기간 만료로 계정 <strong>차단이 자동 해제</strong>되었습니다.</p>"
                        "<p>이제 정상적으로 서비스를 이용하실 수 있습니다.</p>"
                    ),
                    is_read=False,
                )
                for row in target_rows
            ]
            if inbox_msgs:
                session.add_all(inbox_msgs)
                await session.commit()

            # 6) 관리자 차단 자동 만료 (Story 10.3) — 분리 트랜잭션으로 처리해
            #    사용자 분기 commit 후 admin 분기가 실패해도 사용자 복원이 롤백되지 않게 한다.
            admin_result = await _expire_admin_blocks(actor_id)

            logger.info(
                "anomaly.expire_blocks.done",
                expired_count=len(target_ids),
                actor_user_id=actor_id,
                admin_expired_count=admin_result["expired_count"],
            )
            return {
                "expired_count": len(target_ids),
                "actor_user_id": actor_id,
                "admin_expired_count": admin_result["expired_count"],
                "admin_expired_ids": admin_result["expired_ids"],
            }
    finally:
        await engine.dispose()


async def _expire_admin_blocks(actor_id: int) -> dict[str, Any]:
    """Story 10.3 — 관리자 admin_blocked_until 자동 만료 해제 + 알림톡 enqueue + 감사 기록.

    별도 엔진/세션을 사용해 사용자 분기와 격리한다.
    """
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            result = await admin_account_service.expire_admin_blocks(
                session, system_actor_id=actor_id
            )
            for admin_id in result.get("expired_ids", []):
                session.add(
                    AuditLog(
                        actor_user_id=actor_id,
                        action=AUDIT_ADMIN_ACCOUNT_UNBLOCKED,
                        target_type="user",
                        target_id=admin_id,
                        diff_json={
                            "before": {"admin_blocked": True},
                            "after": {"admin_blocked": False, "source": "auto_expire"},
                        },
                        ip=None,
                        ua=None,
                        trace_id=None,
                    )
                )
            await session.commit()
            return result
    finally:
        await engine.dispose()


async def _expire_login_locks_async() -> dict[str, Any]:
    """login_locked_until <= now 인 사용자 잠금 기록 초기화 + 쪽지 발송.

    분리 트랜잭션 — 계정 차단 만료 분기와 독립적으로 동작한다.
    """
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            now = datetime.now(tz=timezone.utc)

            target_rows = (
                await session.execute(
                    select(User.id).where(
                        and_(
                            User.login_locked_until.is_not(None),
                            User.login_locked_until <= now,
                        )
                    )
                )
            ).all()

            if not target_rows:
                return {"expired_count": 0}

            target_ids = [row.id for row in target_rows]

            await session.execute(
                update(User)
                .where(User.id.in_(target_ids))
                .values(login_locked_until=None, updated_at=now)
            )

            inbox_msgs = [
                InboxMessage(
                    user_id=uid,
                    notice_id=None,
                    popup_id=None,
                    type="system",
                    title="로그인 잠금 해제 안내",
                    body_html=(
                        "<p>잠금 기간이 만료되어 <strong>로그인 잠금이 자동 해제</strong>되었습니다.</p>"
                        "<p>이제 정상적으로 로그인하실 수 있습니다.</p>"
                    ),
                    is_read=False,
                )
                for (uid,) in target_rows
            ]
            session.add_all(inbox_msgs)
            await session.commit()

            logger.info(
                "anomaly.expire_login_locks.done",
                expired_count=len(target_ids),
            )
            return {"expired_count": len(target_ids), "expired_ids": target_ids}
    finally:
        await engine.dispose()
