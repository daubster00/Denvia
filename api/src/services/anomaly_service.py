"""Story 6.5 — 이상 이벤트 list/filter/mark + 자동 탐지 hook helper.

본 모듈은 다음을 담당한다:
- list_anomaly_events: GET /admin/anomaly — 분류·상태·기간 필터 + 페이지네이션
- mark_anomaly_reviewed: PATCH /admin/anomaly/{id} — status='reviewed' 전이
- mark_anomaly_actioned: 차단 endpoint(6.2 PATCH /admin/users/{id})에서 호출 — status='actioned'
- check_concurrent_ip_login: auth_service 로그인 성공 직후 hook (편차 3)
- check_rapid_followup_questions: qa_service.preflight 직후 hook — 답변 직후 3초 연속 질의 탐지
- _publish_anomaly_alert: SSE admin:events 채널 publish (편차 6, severity='high'만)
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
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
    "concurrent_ip_login",
    "repeated_question",
    "recovery_abuse",
    "rapid_followup_questions",
)
ANOMALY_STATUSES: tuple[str, ...] = ("new", "reviewed", "actioned", "unblocked")

_HIGH_SEVERITY_TYPES: frozenset[str] = frozenset(
    {"repeated_question", "concurrent_ip_login"}
)

# 후속 질문 패턴 탐지 — 답변 완료 시각 기준 윈도우와 연속 임계.
RAPID_FOLLOWUP_WINDOW_SECONDS = 3.0
RAPID_FOLLOWUP_STREAK_THRESHOLD = 3
# Redis 키. last_done 은 한 시간만 유지하면 충분 — 이후 어차피 streak 이 리셋됨.
_RAPID_FOLLOWUP_LAST_DONE_KEY = "qa:last_done:user:{user_id}"
_RAPID_FOLLOWUP_STREAK_KEY = "qa:rapid_followup_streak:user:{user_id}"
_RAPID_FOLLOWUP_LAST_DONE_TTL = 3600
_RAPID_FOLLOWUP_STREAK_TTL = 3600


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
        # 'unblocked' 는 종결 상태 — 정책상 리스트에 노출하지 않는다.
        # 어떤 status_in 이 들어와도 항상 제외.
        .where(AnomalyEvent.status != "unblocked")
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


async def get_anomaly_detail(
    db: AsyncSession,
    *,
    anomaly_id: int,
) -> dict[str, Any]:
    """이상탐지 상세 드로어용 — 단건 + 누적 통계 + 대상 사용자 현황.

    반환 dict 키:
      - id, type, target_user_id, target_user_email_masked, ip, ua, details, status,
        reviewed_by_admin_id, reviewed_at, created_at, admin_memo
      - auto_actioned, occurrence_count, last_occurred_at
      - user_subscription_status, user_blocked_until, user_block_reason,
        user_question_blocked_until, user_question_block_reason,
        user_anomaly_throttled_at
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

    base = await _serialize_event_with_email(db, event)
    base["admin_memo"] = event.admin_memo
    details_dict = event.details or {}
    base["auto_actioned"] = bool(
        details_dict.get("auto_actioned") or event.type == "rapid_followup_questions"
    )

    # 누적 탐지 — 같은 (target_user_id, type) 조합, target_user_id 가 NULL 이면 (ip, type) 로.
    count_q = select(func.count()).select_from(AnomalyEvent).where(
        AnomalyEvent.type == event.type
    )
    last_q = select(func.max(AnomalyEvent.created_at)).where(
        AnomalyEvent.type == event.type
    )
    if event.target_user_id is not None:
        count_q = count_q.where(AnomalyEvent.target_user_id == event.target_user_id)
        last_q = last_q.where(AnomalyEvent.target_user_id == event.target_user_id)
    elif event.ip is not None:
        count_q = count_q.where(AnomalyEvent.ip == event.ip)
        last_q = last_q.where(AnomalyEvent.ip == event.ip)

    occurrence_count = int((await db.execute(count_q)).scalar_one() or 0)
    last_at = (await db.execute(last_q)).scalar_one()
    base["occurrence_count"] = occurrence_count
    base["last_occurred_at"] = last_at

    # 대상 사용자 현황.
    if event.target_user_id is not None:
        user_row = (
            await db.execute(select(User).where(User.id == event.target_user_id))
        ).scalar_one_or_none()
        if user_row is not None:
            base["user_subscription_status"] = user_row.subscription_status
            base["user_blocked_until"] = user_row.blocked_until
            base["user_block_reason"] = user_row.block_reason
            base["user_question_blocked_until"] = user_row.question_blocked_until
            base["user_question_block_reason"] = user_row.question_block_reason
            base["user_anomaly_throttled_at"] = user_row.anomaly_throttled_at
        else:
            base["user_subscription_status"] = None
    else:
        base["user_subscription_status"] = None

    return base


async def update_anomaly_memo(
    db: AsyncSession,
    *,
    anomaly_id: int,
    memo: str,
) -> AnomalyEvent:
    """메모 저장 — 빈 문자열은 NULL 로 정규화."""
    event = await db.get(AnomalyEvent, anomaly_id)
    if event is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "ANOMALY_NOT_FOUND",
                "message": "이상 이벤트를 찾을 수 없습니다.",
            },
        )
    normalized = memo.strip()
    event.admin_memo = normalized if normalized else None
    await db.flush()
    return event


async def mark_anomaly_unblocked(
    db: AsyncSession,
    *,
    anomaly_id: int,
) -> AnomalyEvent | None:
    """이상탐지 UI 에서 차단 해제 호출 시 — 'actioned' → 'unblocked' 전이.

    - None 반환: anomaly_id 미존재 또는 'actioned' 가 아닌 상태(멱등 noop).
    - reviewed_by_admin_id / reviewed_at 은 actioned 시점 값을 그대로 유지한다
      (해제 이력은 audit_logs 의 user.permission_edit 에서 추적).
    """
    event = await db.get(AnomalyEvent, anomaly_id)
    if event is None or event.status != "actioned":
        return None
    event.status = "unblocked"
    return event


async def mark_user_anomalies_unblocked(
    db: AsyncSession,
    *,
    user_id: int,
    type_in: list[str] | None = None,
) -> int:
    """대상 사용자의 'actioned' anomaly 를 'unblocked' 로 일괄 전이.

    호출 시점: ``user_service._apply_unblock`` 직후. 사용자관리 페이지에서 해제하든
    이상탐지 페이지에서 해제하든, 그 사용자에 대한 차단 적용 이력은 모두 종결 상태로
    옮긴다(이상탐지 리스트에서 자동 제외 — 종결 상태는 노출하지 않는 정책).

    ``type_in`` 지정 시 해당 타입의 이벤트만 전이 — 쿨다운(throttle) 해제는
    `rapid_followup_questions` 만 unblocked 처리하고 별개의 24h/7d/영구차단 이력은
    그대로 둔다.

    반환: 전이된 행 수.
    """
    from sqlalchemy import update as sa_update

    stmt = (
        sa_update(AnomalyEvent)
        .where(AnomalyEvent.target_user_id == user_id)
        .where(AnomalyEvent.status == "actioned")
    )
    if type_in:
        stmt = stmt.where(AnomalyEvent.type.in_(type_in))
    stmt = stmt.values(status="unblocked")
    result = await db.execute(stmt)
    return int(result.rowcount or 0)


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


# ── 답변 완료 후 3초 이내 후속 질의 연속 탐지 ──────────────────────────────────


async def check_rapid_followup_questions(
    *,
    user_id: int,
    subscription_status: str,
    redis_quota,
    db: AsyncSession,
    redis_pubsub=None,
) -> bool:
    """qa_service.preflight 내 hook. admin 은 skip.

    동작:
      1. Redis 에서 직전 답변 완료 시각 (``qa:last_done:user:{id}``) 조회.
      2. last_done 이 없거나 (now - last_done) > 3초 → streak 카운터 리셋(DEL) 후 return.
      3. (now - last_done) <= 3초 → streak INCR (24h TTL). 3 도달 시 anomaly 발생.

    Anomaly 발생 시:
      - INSERT AnomalyEvent(type='rapid_followup_questions', target_user_id=user_id)
      - UPDATE users SET anomaly_throttled_at = NOW() (이미 채워져 있으면 유지)
      - DEL streak 키 (재발 시 새로 카운트)
      - 관리자 알림톡 schedule

    반환: 본 호출에서 throttle 이 새로 적용되었는지(True/False). 이미 적용 중인
    사용자는 False (qa_service 가 user.anomaly_throttled_at 으로 적용 분기).
    """
    if subscription_status == "admin":
        return False

    last_done_key = _RAPID_FOLLOWUP_LAST_DONE_KEY.format(user_id=user_id)
    streak_key = _RAPID_FOLLOWUP_STREAK_KEY.format(user_id=user_id)

    try:
        raw_last_done = await redis_quota.get(last_done_key)
    except Exception:
        logger.error("anomaly.rapid_followup.redis_read_failed", exc_info=True)
        return False

    if raw_last_done is None:
        # 직전 답변이 없으면 신규 세션 — streak 리셋.
        try:
            await redis_quota.delete(streak_key)
        except Exception:
            pass
        return False

    try:
        last_done_ts = float(raw_last_done)
    except (TypeError, ValueError):
        last_done_ts = 0.0

    now_ts = time.time()
    delta = now_ts - last_done_ts

    if delta > RAPID_FOLLOWUP_WINDOW_SECONDS or delta < 0:
        # 윈도우 밖 — streak 리셋. 다음 답변 완료 시점부터 새로 시작.
        try:
            await redis_quota.delete(streak_key)
        except Exception:
            pass
        return False

    # 윈도우 안 → streak INCR.
    try:
        streak = await redis_quota.incr(streak_key)
        if streak == 1:
            await redis_quota.expire(streak_key, _RAPID_FOLLOWUP_STREAK_TTL)
    except Exception:
        logger.error("anomaly.rapid_followup.streak_incr_failed", exc_info=True)
        return False

    if streak < RAPID_FOLLOWUP_STREAK_THRESHOLD:
        return False

    # 임계 도달 — anomaly 기록 + throttle 적용.
    try:
        # 사용자 throttle flag 가 이미 채워져 있으면 멱등: anomaly INSERT 만 skip.
        from sqlalchemy import update as sa_update

        from api.src.models.user import User as _User

        user_row = (
            await db.execute(select(_User).where(_User.id == user_id))
        ).scalar_one_or_none()
        if user_row is None:
            return False

        already_throttled = user_row.anomaly_throttled_at is not None
        if not already_throttled:
            now_dt = datetime.now(tz=timezone.utc)
            await db.execute(
                sa_update(_User)
                .where(_User.id == user_id)
                .values(anomaly_throttled_at=now_dt)
            )

        # rapid_followup 은 시스템이 즉시 자동조치(throttle)를 적용하므로
        # 등록 시점에 바로 actioned + 자동검토 처리. reviewed_by_admin_id=None 이
        # "시스템 자동조치" 표식 — 24h/7d/영구차단 액션 분기와 구분된다.
        now_dt2 = datetime.now(tz=timezone.utc)
        event = AnomalyEvent(
            type="rapid_followup_questions",
            target_user_id=user_id,
            ip=None,
            ua=None,
            details={
                "streak": int(streak),
                "window_seconds": RAPID_FOLLOWUP_WINDOW_SECONDS,
                "last_done_delta_seconds": round(delta, 3),
                "already_throttled": already_throttled,
                "auto_actioned": True,
            },
            status="actioned",
            reviewed_by_admin_id=None,
            reviewed_at=now_dt2,
            created_at=now_dt2,
        )
        db.add(event)
        try:
            await db.flush()
        except Exception:
            await db.rollback()
            logger.error("anomaly.rapid_followup.insert_failed", exc_info=True)
            return False

        # 재발 시 다시 0부터 카운트.
        try:
            await redis_quota.delete(streak_key)
        except Exception:
            pass

        logger.info(
            "anomaly.rapid_followup.detected",
            user_id=user_id,
            streak=int(streak),
            delta_seconds=round(delta, 3),
            already_throttled=already_throttled,
            anomaly_id=event.id,
        )

        # severity='medium' — SSE publish skip.
        return not already_throttled
    except Exception:
        logger.error("anomaly.rapid_followup.hook_failed", exc_info=True)
        return False


async def record_stream_done(
    *,
    user_id: int,
    subscription_status: str,
    redis_quota,
) -> None:
    """qa_service.stream 의 stream 종료 직후 호출 — 마지막 답변 완료 시각 기록.

    admin 은 throttle 대상이 아니므로 기록하지 않는다 (Redis 키 증가 방지).
    """
    if subscription_status == "admin":
        return
    key = _RAPID_FOLLOWUP_LAST_DONE_KEY.format(user_id=user_id)
    try:
        await redis_quota.set(key, str(time.time()), ex=_RAPID_FOLLOWUP_LAST_DONE_TTL)
    except Exception:
        # last_done 기록 실패는 silent — 다음 답변 완료에서 다시 채워진다.
        logger.error("anomaly.rapid_followup.record_done_failed", exc_info=True)


async def clear_user_anomaly_throttle(
    *,
    user_id: int,
    db: AsyncSession,
    redis_quota=None,
) -> bool:
    """관리자 수동 해제 — users.anomaly_throttled_at = NULL + Redis streak/last_done 정리.

    호출자: 라우터 (/admin/users/{id}/anomaly-throttle DELETE) 또는 user_service.unblock.
    반환: 실제 해제가 이루어졌는지(True=이전에 throttled, False=원래 NULL).
    """
    from sqlalchemy import update as sa_update

    from api.src.models.user import User as _User

    user_row = (
        await db.execute(select(_User).where(_User.id == user_id))
    ).scalar_one_or_none()
    if user_row is None or user_row.anomaly_throttled_at is None:
        return False

    await db.execute(
        sa_update(_User)
        .where(_User.id == user_id)
        .values(anomaly_throttled_at=None)
    )

    # rapid_followup_questions actioned 이벤트도 동반 unblocked 처리 →
    # 이상탐지 리스트에서 자동 제외. 다른 타입(IP·반복질문 등)으로 인한
    # actioned 이력은 건드리지 않는다.
    await mark_user_anomalies_unblocked(
        db, user_id=user_id, type_in=["rapid_followup_questions"]
    )

    if redis_quota is not None:
        try:
            await redis_quota.delete(
                _RAPID_FOLLOWUP_STREAK_KEY.format(user_id=user_id)
            )
        except Exception:
            pass

    return True


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
    "RAPID_FOLLOWUP_WINDOW_SECONDS",
    "RAPID_FOLLOWUP_STREAK_THRESHOLD",
    "list_anomaly_events",
    "get_anomaly_detail",
    "update_anomaly_memo",
    "mark_anomaly_reviewed",
    "mark_anomaly_actioned",
    "mark_anomaly_unblocked",
    "mark_user_anomalies_unblocked",
    "check_concurrent_ip_login",
    "check_rapid_followup_questions",
    "record_stream_done",
    "clear_user_anomaly_throttle",
]
