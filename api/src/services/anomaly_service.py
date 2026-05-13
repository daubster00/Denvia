"""Story 6.5 — 이상 이벤트 list/filter/mark + 자동 탐지 hook helper.

본 모듈은 다음을 담당한다:
- list_anomaly_events: GET /admin/anomaly — 분류·상태·기간 필터 + 페이지네이션
- mark_anomaly_reviewed: PATCH /admin/anomaly/{id} — status='reviewed' 전이
- mark_anomaly_actioned: 차단 endpoint(6.2 PATCH /admin/users/{id})에서 호출 — status='actioned'
- check_concurrent_ip_login: auth_service 로그인 성공 직후 hook (편차 3)
- check_rapid_questions: qa_service.preflight 직후 hook (편차 4)
- _publish_anomaly_alert: SSE admin:events 채널 publish (편차 6, severity='high'만)
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.anomaly_event import AnomalyEvent
from api.src.models.user import User

logger = structlog.get_logger(__name__)

ANOMALY_TYPES: tuple[str, ...] = (
    "login_brute_force",
    "rapid_questions",
    "concurrent_ip_login",
    "repeated_question",
    "recovery_abuse",
)
ANOMALY_STATUSES: tuple[str, ...] = ("new", "reviewed", "actioned")

_HIGH_SEVERITY_TYPES: frozenset[str] = frozenset(
    {"repeated_question", "concurrent_ip_login"}
)


# ── List + filter ──────────────────────────────────────────────────────────────


async def list_anomaly_events(
    db: AsyncSession,
    *,
    type_in: list[str] | None = None,
    status_in: list[str] | None = None,
    target_user_id: int | None = None,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
    page: int = 1,
    per_page: int = 20,
) -> dict[str, Any]:
    """epics AC-4 — 분류·상태·기간 필터 + 페이지네이션.

    기본 정렬 created_at DESC, status_in 미지정 시 'new' 단독.
    """
    base_q = (
        select(AnomalyEvent)
        .outerjoin(User, AnomalyEvent.target_user_id == User.id)
        .where(or_(AnomalyEvent.target_user_id.is_(None), User.role != "admin"))
    )

    if status_in is None or len(status_in) == 0:
        base_q = base_q.where(AnomalyEvent.status == "new")
    else:
        base_q = base_q.where(AnomalyEvent.status.in_(status_in))

    if type_in:
        base_q = base_q.where(AnomalyEvent.type.in_(type_in))

    if target_user_id is not None:
        base_q = base_q.where(AnomalyEvent.target_user_id == target_user_id)

    if from_dt is not None:
        base_q = base_q.where(AnomalyEvent.created_at >= from_dt)
    if to_dt is not None:
        base_q = base_q.where(AnomalyEvent.created_at <= to_dt)

    count_q = select(func.count()).select_from(base_q.subquery())
    total = (await db.execute(count_q)).scalar_one()

    items_q = (
        base_q.order_by(AnomalyEvent.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    rows = (await db.execute(items_q)).scalars().all()

    user_ids = {r.target_user_id for r in rows if r.target_user_id is not None}
    email_map: dict[int, str] = {}
    if user_ids:
        # 탈퇴 사용자는 마스킹된 이메일도 노출하지 않는다 (Story 6.1 검색 정책 일관).
        email_rows = (
            await db.execute(
                select(User.id, User.email)
                .where(User.id.in_(user_ids))
                .where(User.withdrawn_at.is_(None))
            )
        ).all()
        email_map = {row.id: row.email for row in email_rows}

    items = [
        {
            "id": r.id,
            "type": r.type,
            "target_user_id": r.target_user_id,
            "target_user_email_masked": (
                _mask_email(email_map.get(r.target_user_id))
                if r.target_user_id
                else None
            ),
            "ip": r.ip,
            "ua": r.ua,
            "details": r.details or {},
            "status": r.status,
            "reviewed_by_admin_id": r.reviewed_by_admin_id,
            "reviewed_at": r.reviewed_at,
            "created_at": r.created_at,
        }
        for r in rows
    ]

    return {"items": items, "page": page, "per_page": per_page, "total": total}


# ── Status transitions ────────────────────────────────────────────────────────


async def mark_anomaly_reviewed(
    db: AsyncSession,
    *,
    anomaly_id: int,
    actor_admin_id: int,
) -> dict[str, Any]:
    """epics AC-6 — status='reviewed' 전이.

    - 'actioned' 상태는 변경 불가(409).
    - 'reviewed' 상태는 멱등 — 직렬화만 반환하고 `transitioned=False`로 표식 (라우터에서 audit skip).

    응답: ``{"event": <serialized>, "transitioned": <bool>}``
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

    if event.status == "actioned":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "ANOMALY_ALREADY_ACTIONED",
                "message": "이미 차단 액션이 적용된 이벤트입니다.",
            },
        )

    if event.status == "reviewed":
        serialized = await _serialize_event_with_email(db, event)
        return {"event": serialized, "transitioned": False}

    event.status = "reviewed"
    event.reviewed_by_admin_id = actor_admin_id
    event.reviewed_at = datetime.now(tz=timezone.utc)
    await db.flush()
    serialized = await _serialize_event_with_email(db, event)
    return {"event": serialized, "transitioned": True}


async def mark_anomaly_actioned(
    db: AsyncSession,
    *,
    anomaly_id: int,
    actor_admin_id: int | None,
) -> AnomalyEvent | None:
    """차단 액션 적용 시 user_service.update_permission이 호출.

    - None 반환: anomaly_id 미존재 또는 이미 actioned 상태.
    - 멱등 보존(편차 보강): 사전에 다른 admin이 'reviewed'로 표식했다면 ``reviewed_by_admin_id``/
      ``reviewed_at``을 그대로 유지한다 (P11). 'new' 상태에서 직접 'actioned'로 전이하는 경우만
      현재 admin id로 채운다.
    """
    event = await db.get(AnomalyEvent, anomaly_id)
    if event is None or event.status == "actioned":
        return None
    if event.reviewed_by_admin_id is None:
        # 'new' → 'actioned' 직접 전이 — actor 식별 필요.
        event.reviewed_by_admin_id = actor_admin_id
        event.reviewed_at = datetime.now(tz=timezone.utc)
    # 'reviewed' → 'actioned' 전이: 원래 reviewer/at 보존.
    event.status = "actioned"
    return event


# ── Auto-detection hooks ───────────────────────────────────────────────────────


async def check_concurrent_ip_login(
    *,
    ip: str | None,
    user_id: int,
    ua: str | None,
    redis_rl,
    db: AsyncSession,
    redis_pubsub=None,
) -> None:
    """편차 3 — 로그인 성공 직후 hook. ip is None 시 skip.

    Redis ZSET `login:ip:{ip}`에 (score=ts, member=user_id) ZADD →
    10분 윈도우 ZCARD ≥ 3 시 멱등 INSERT (`concurrent_ip_flagged:{ip}` 10분 NX).
    target_user_id=None — 다중 계정 표지.
    """
    if ip is None:
        return

    ip_key = f"login:ip:{ip}"
    now_ts = time.time()
    window_start = now_ts - 600

    try:
        await redis_rl.zadd(ip_key, {str(user_id): now_ts})
        await redis_rl.zremrangebyscore(ip_key, "-inf", window_start)
        await redis_rl.expire(ip_key, 600)
        members = await redis_rl.zrange(ip_key, 0, -1)
        distinct_user_ids = sorted({int(m) for m in members})

        if len(distinct_user_ids) < 3:
            return

        flag_key = f"concurrent_ip_flagged:{ip}"
        flag_ok = await redis_rl.set(flag_key, "1", ex=600, nx=True)
        if not flag_ok:
            return

        event = AnomalyEvent(
            type="concurrent_ip_login",
            target_user_id=None,
            ip=ip,
            ua=ua,
            details={
                "distinct_user_count": len(distinct_user_ids),
                "user_ids": distinct_user_ids[:10],
            },
            status="new",
            created_at=datetime.now(tz=timezone.utc),
        )
        db.add(event)
        try:
            await db.flush()
        except Exception:
            await db.rollback()
            logger.error("anomaly.concurrent_ip_login.insert_failed", exc_info=True)
            return

        logger.info(
            "anomaly.concurrent_ip_login.detected",
            ip=ip,
            distinct_user_count=len(distinct_user_ids),
            anomaly_id=event.id,
        )

        if redis_pubsub is not None:
            await _publish_anomaly_alert(
                redis_pubsub,
                anomaly_id=event.id,
                anomaly_type="concurrent_ip_login",
                severity="high",
            )
    except Exception:
        logger.error("anomaly.concurrent_ip_login.hook_failed", exc_info=True)


async def check_rapid_questions(
    *,
    user_id: int,
    subscription_status: str,
    redis_quota,
    db: AsyncSession,
    redis_pubsub=None,
) -> None:
    """편차 4 — qa_service.preflight 내 hook. admin은 skip.

    Redis fixed window `rapid:user:{id}:{minute_bucket}` INCR →
    임계 3건/1분 도달 시 멱등 INSERT (`rapid_flagged:user:{id}` 60초 NX).

    멱등 flag TTL은 60초 — fixed window 길이와 동일. 5분 TTL은 다음 정상 burst까지
    탐지를 가려 어뷰저 우대 효과가 있으므로(P13) 단일 윈도우 단위로만 묶는다.
    """
    if subscription_status == "admin":
        return

    minute_bucket = int(time.time() // 60)
    rapid_key = f"rapid:user:{user_id}:{minute_bucket}"

    try:
        rapid_count = await redis_quota.incr(rapid_key)
        if rapid_count == 1:
            await redis_quota.expire(rapid_key, 65)

        if rapid_count < 3:
            return

        flag_key = f"rapid_flagged:user:{user_id}"
        flag_ok = await redis_quota.set(flag_key, "1", ex=60, nx=True)
        if not flag_ok:
            return

        event = AnomalyEvent(
            type="rapid_questions",
            target_user_id=user_id,
            ip=None,
            ua=None,
            details={
                "count_in_window": int(rapid_count),
                "window_minute_bucket": minute_bucket,
            },
            status="new",
            created_at=datetime.now(tz=timezone.utc),
        )
        db.add(event)
        try:
            await db.flush()
        except Exception:
            await db.rollback()
            logger.error("anomaly.rapid_questions.insert_failed", exc_info=True)
            return

        logger.info(
            "anomaly.rapid_questions.detected",
            user_id=user_id,
            count_in_window=int(rapid_count),
            anomaly_id=event.id,
        )
        # rapid_questions는 severity='medium' — publish skip (편차 6)
    except Exception:
        logger.error("anomaly.rapid_questions.hook_failed", exc_info=True)


# ── SSE publish ────────────────────────────────────────────────────────────────


async def _publish_anomaly_alert(
    redis_pubsub,
    *,
    anomaly_id: int,
    anomaly_type: str,
    severity: str,
) -> None:
    """편차 6 — admin:events 채널에 anomaly_alert publish (severity='high'만).

    redis_pubsub이 None이거나 publish 실패 시 silent — 알림은 best-effort.
    """
    if redis_pubsub is None:
        return
    if anomaly_type not in _HIGH_SEVERITY_TYPES:
        return
    try:
        payload = json.dumps(
            {
                "type": "anomaly_alert",
                "anomaly_id": anomaly_id,
                "severity": severity,
                "anomaly_type": anomaly_type,
            }
        )
        await redis_pubsub.publish("admin:events", payload)
    except Exception:
        logger.error("anomaly.publish_failed", exc_info=True)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _mask_email(email: str | None) -> str | None:
    """앞 1자 + ** + @도메인. 1자/@ 미포함은 그대로 (6.4 _mask_email 동일 정의)."""
    if email is None or "@" not in email:
        return email
    local, _, domain = email.partition("@")
    if len(local) <= 1:
        return email
    return f"{local[0]}**@{domain}"


def _serialize_event(event: AnomalyEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "type": event.type,
        "target_user_id": event.target_user_id,
        "target_user_email_masked": None,
        "ip": event.ip,
        "ua": event.ua,
        "details": event.details or {},
        "status": event.status,
        "reviewed_by_admin_id": event.reviewed_by_admin_id,
        "reviewed_at": event.reviewed_at,
        "created_at": event.created_at,
    }


async def _serialize_event_with_email(
    db: AsyncSession, event: AnomalyEvent
) -> dict[str, Any]:
    """단건 응답용 직렬화 — target_user_id가 있으면 마스킹된 이메일 동봉.

    탈퇴 사용자는 이메일을 노출하지 않는다 (Story 6.1 검색 정책 일관, P5).
    """
    serialized = _serialize_event(event)
    if event.target_user_id is None:
        return serialized
    email_row = (
        await db.execute(
            select(User.email)
            .where(User.id == event.target_user_id)
            .where(User.withdrawn_at.is_(None))
        )
    ).scalar_one_or_none()
    serialized["target_user_email_masked"] = _mask_email(email_row)
    return serialized


__all__ = [
    "ANOMALY_TYPES",
    "ANOMALY_STATUSES",
    "list_anomaly_events",
    "mark_anomaly_reviewed",
    "mark_anomaly_actioned",
    "check_concurrent_ip_login",
    "check_rapid_questions",
]
