"""이상탐지 "주의 계정" (watch list) 서비스.

이상탐지 리스트의 별 모양 버튼으로 관리자가 특정 계정을 주의 계정 목록에 올린다.
계정당 한 행(user_id UNIQUE) — 같은 계정을 두 번 등록하면 ON CONFLICT DO NOTHING.

핵심 함수:
- add_watch_from_anomaly: 이상 이벤트를 기준으로 주의 계정 등록.
- remove_watch: 주의 계정 해제.
- list_watched: GET /admin/anomaly/watched.
- get_watched_user_ids: 이상 이벤트 목록 응답에 ``is_watched`` 값을 채우기 위한 헬퍼.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.anomaly_event import AnomalyEvent
from api.src.models.user import User
from api.src.models.user_watch_flag import UserWatchFlag

logger = structlog.get_logger(__name__)


def _mask_email(email: str | None) -> str | None:
    if email is None or "@" not in email:
        return email
    local, _, domain = email.partition("@")
    if len(local) <= 1:
        return email
    return f"{local[0]}**@{domain}"


async def add_watch_from_anomaly(
    db: AsyncSession,
    *,
    anomaly_id: int,
    actor_admin_id: int,
) -> dict[str, Any]:
    """이상 이벤트의 target_user 를 주의 계정으로 등록한다.

    target_user_id 가 NULL 이면 422. 이미 등록된 사용자는 멱등 (ON CONFLICT DO NOTHING).
    """
    event = await db.get(AnomalyEvent, anomaly_id)
    if event is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "ANOMALY_NOT_FOUND",
                "message": "이상 이벤트를 찾을 수 없습니다.",
            },
        )
    if event.target_user_id is None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "WATCH_TARGET_REQUIRED",
                "message": "대상 사용자가 식별되지 않은 이상 이벤트는 주의 계정으로 등록할 수 없습니다.",
            },
        )

    stmt = (
        pg_insert(UserWatchFlag)
        .values(
            user_id=event.target_user_id,
            flagged_by_admin_id=actor_admin_id,
            source_anomaly_id=event.id,
            anomaly_type=event.type,
            created_at=datetime.now(tz=timezone.utc),
        )
        .on_conflict_do_nothing(index_elements=["user_id"])
    )
    await db.execute(stmt)
    await db.flush()
    return {"user_id": event.target_user_id, "is_watched": True}


async def remove_watch(
    db: AsyncSession,
    *,
    user_id: int,
) -> dict[str, Any]:
    """주의 계정 해제 — 멱등. 행이 없어도 200/{is_watched: False}."""
    row = (
        await db.execute(
            select(UserWatchFlag).where(UserWatchFlag.user_id == user_id)
        )
    ).scalar_one_or_none()
    if row is not None:
        await db.delete(row)
        await db.flush()
    return {"user_id": user_id, "is_watched": False}


async def list_watched(
    db: AsyncSession,
    *,
    page: int = 1,
    per_page: int = 50,
) -> dict[str, Any]:
    """주의 계정 리스트 — 최근 등록 순.

    탈퇴 사용자(users.withdrawn_at IS NOT NULL) 는 제외한다.
    각 사용자에 대해 anomaly_events 에서 type 별 최신 1건씩 모아 ``anomalies`` 로
    내려준다(최근 발생 순). 화면에서는 한 줄씩 표시되고 각 항목에 "상세보기"가 붙는다.
    """
    base_q = (
        select(UserWatchFlag, User)
        .join(User, User.id == UserWatchFlag.user_id)
        .where(User.withdrawn_at.is_(None))
    )

    count_q = select(func.count()).select_from(base_q.subquery())
    total = (await db.execute(count_q)).scalar_one()

    items_q = (
        base_q.order_by(UserWatchFlag.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    rows = (await db.execute(items_q)).all()

    user_ids = [r.User.id for r in rows]

    # type별 최신 이벤트 — PostgreSQL DISTINCT ON (target_user_id, type).
    anomalies_by_user: dict[int, list[dict[str, Any]]] = {}
    if user_ids:
        anomaly_q = (
            select(
                AnomalyEvent.target_user_id,
                AnomalyEvent.type,
                AnomalyEvent.id,
                AnomalyEvent.created_at,
            )
            .where(AnomalyEvent.target_user_id.in_(user_ids))
            .order_by(
                AnomalyEvent.target_user_id,
                AnomalyEvent.type,
                AnomalyEvent.created_at.desc(),
                AnomalyEvent.id.desc(),
            )
            .distinct(AnomalyEvent.target_user_id, AnomalyEvent.type)
        )
        anomaly_rows = (await db.execute(anomaly_q)).all()
        for ar in anomaly_rows:
            anomalies_by_user.setdefault(ar.target_user_id, []).append(
                {
                    "anomaly_id": ar.id,
                    "type": ar.type,
                    "created_at": ar.created_at,
                }
            )
        for lst in anomalies_by_user.values():
            lst.sort(key=lambda x: x["created_at"], reverse=True)

    now_dt = datetime.now(tz=timezone.utc)
    items: list[dict[str, Any]] = []
    for r in rows:
        flag: UserWatchFlag = r.UserWatchFlag
        user: User = r.User
        bu = user.blocked_until
        blocked_now = (
            (bu is not None and bu > now_dt)
            or user.subscription_status == "blocked"
        )
        items.append(
            {
                "user_id": user.id,
                "email_masked": _mask_email(user.email),
                "anomalies": anomalies_by_user.get(user.id, []),
                "user_subscription_status": user.subscription_status,
                "user_blocked_now": blocked_now,
                "user_auto_throttled_now": user.anomaly_throttled_at is not None,
                "flagged_by_admin_id": flag.flagged_by_admin_id,
                "flagged_at": flag.created_at,
            }
        )
    return {"items": items, "page": page, "per_page": per_page, "total": total}


async def get_watched_user_ids(
    db: AsyncSession,
    *,
    user_ids: list[int] | set[int],
) -> set[int]:
    """주어진 user_id 들 중 주의 계정으로 등록된 id 집합을 반환."""
    ids = list(user_ids)
    if not ids:
        return set()
    rows = (
        await db.execute(
            select(UserWatchFlag.user_id).where(UserWatchFlag.user_id.in_(ids))
        )
    ).scalars().all()
    return {int(x) for x in rows}


async def is_watched(db: AsyncSession, *, user_id: int) -> bool:
    """단건 — 상세 응답용."""
    row = (
        await db.execute(
            select(UserWatchFlag.id).where(UserWatchFlag.user_id == user_id)
        )
    ).scalar_one_or_none()
    return row is not None


__all__ = [
    "add_watch_from_anomaly",
    "remove_watch",
    "list_watched",
    "get_watched_user_ids",
    "is_watched",
]
