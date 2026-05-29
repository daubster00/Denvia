"""Story 6.5 — 이상 이벤트 list/filter/mark + 자동 탐지 hook helper.

본 모듈은 다음을 담당한다:
- list_anomaly_events: GET /admin/anomaly — 분류·상태·기간 필터 + 페이지네이션
- mark_anomaly_reviewed: PATCH /admin/anomaly/{id} — status='reviewed' 전이
- mark_anomaly_actioned: 차단 endpoint(6.2 PATCH /admin/users/{id})에서 호출 — status='actioned'
- check_concurrent_ip_login: auth_service 로그인 성공 직후 hook (편차 3)
- check_rapid_followup_questions: qa_service.preflight 직후 hook — 답변 직후 3초 연속 질의 탐지
- check_repeated_question: qa_service.preflight 직후 hook — 동일 텍스트 3회 연속 질의 탐지
- _publish_anomaly_alert: SSE admin:events 채널 publish (편차 6, severity='high'만)
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from fastapi import HTTPException
from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.anomaly_event import AnomalyEvent
from api.src.models.inbox_message import InboxMessage
from api.src.models.user import User
from api.src.models.user_watch_flag import UserWatchFlag
from api.src.settings import REDIS_DB_RUNTIME_CONFIG, settings
from api.src.utils.html_sanitize import sanitize_body_html

# Runtime Config(DB 3) Redis 연결 — 관리자 편집 임계값 동적 조회용. 호출 시점에 새로 열고
# context manager 로 닫는다(테스트 격리 + 연결 누수 방지).
_RUNTIME_URL = f"{settings.redis_url}/{REDIS_DB_RUNTIME_CONFIG}"


def _make_redis_runtime():
    """Runtime DB 3 (관리자 편집 임계값) — 호출자가 ``async with`` 로 닫는다."""
    from redis.asyncio import Redis as _Redis

    return _Redis.from_url(_RUNTIME_URL, decode_responses=True)


async def _resolve_concurrent_ip_threshold() -> int:
    """동일 IP N명 임계. fail-safe 폴백 = 3."""
    try:
        from api.src.services import runtime_config_service as _rc

        async with _make_redis_runtime() as r:
            return await _rc.get_concurrent_ip_threshold(r)
    except Exception:
        return 3


async def _resolve_concurrent_ip_window_seconds() -> int:
    """동일 IP 추적 윈도우(초). fail-safe 폴백 = 600."""
    try:
        from api.src.services import runtime_config_service as _rc

        async with _make_redis_runtime() as r:
            return await _rc.get_concurrent_ip_window_seconds(r)
    except Exception:
        return 600


async def _resolve_repeated_question_threshold() -> int:
    """동일 질문 N회 임계. fail-safe 폴백 = 3."""
    try:
        from api.src.services import runtime_config_service as _rc

        async with _make_redis_runtime() as r:
            return await _rc.get_repeated_question_threshold(r)
    except Exception:
        return 3


async def _resolve_rapid_followup_window_seconds() -> float:
    """답변 직후 N초 임계. fail-safe 폴백 = 3.0."""
    try:
        from api.src.services import runtime_config_service as _rc

        async with _make_redis_runtime() as r:
            return float(await _rc.get_rapid_followup_window_seconds(r))
    except Exception:
        return 3.0


async def _resolve_rapid_followup_threshold() -> int:
    """답변 직후 연속 N회 임계. fail-safe 폴백 = 3."""
    try:
        from api.src.services import runtime_config_service as _rc

        async with _make_redis_runtime() as r:
            return await _rc.get_rapid_followup_threshold(r)
    except Exception:
        return 3

logger = structlog.get_logger(__name__)

ANOMALY_TYPES: tuple[str, ...] = (
    "login_brute_force",
    "concurrent_ip_login",
    "repeated_question",
    "recovery_abuse",
    "rapid_followup_questions",
    "sms_abuse",
)
ANOMALY_STATUSES: tuple[str, ...] = ("new", "reviewed", "actioned", "unblocked")

# admin.anomaly_detected 알림톡 본문 {anomaly_type} 변수에 들어가는 한국어 라벨.
# ENUM 값을 그대로 노출하면 관리자가 알아보기 어려워 한국어로 변환한다.
ANOMALY_TYPE_LABELS_KO: dict[str, str] = {
    "login_brute_force": "비밀번호 반복 실패",
    "concurrent_ip_login": "동일 IP 다중 로그인",
    "repeated_question": "동일 질문 반복",
    "recovery_abuse": "비밀번호 찾기 남용",
    "rapid_followup_questions": "답변 직후 연속 질문",
    "sms_abuse": "휴대폰 인증 남용",
}

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

# 동일 질문 반복 탐지 — 정확히 같은 텍스트(trim) 가 연속 3회 시 자동 throttle.
# rapid_followup 과 동일 조치 — anomaly INSERT(actioned) + users.anomaly_throttled_at SET.
REPEATED_QUESTION_STREAK_THRESHOLD = 3
REPEATED_QUESTION_WINDOW_SECONDS = 3600  # 1h — 그 이상 텀이면 streak 리셋
_REPEATED_QUESTION_LAST_KEY = "qa:last_question:user:{user_id}"
_REPEATED_QUESTION_STREAK_KEY = "qa:repeated_question_streak:user:{user_id}"
_REPEATED_QUESTION_TTL = REPEATED_QUESTION_WINDOW_SECONDS

_AUTO_THROTTLE_INBOX_REASONS: dict[str, str] = {
    "rapid_followup_questions": (
        "답변 직후 3초 이내에 새 질문을 연속 3회 이상 보내셔서"
    ),
    "repeated_question": "같은 질문을 연속 3회 이상 보내셔서",
}


def _build_auto_throttle_inbox_message(
    *, user_id: int, anomaly_type: str
) -> InboxMessage:
    """자동 제한(쿨다운) 적용 시 사용자 쪽지함에 발송하는 안내.

    만료 시각 없이 관리자 수동 해제 전까지 지속된다.
    """
    reason_phrase = _AUTO_THROTTLE_INBOX_REASONS.get(
        anomaly_type, "비정상적인 질의 패턴이 감지되어"
    )
    body = (
        f"<p>{reason_phrase} 자동 제한이 적용되었습니다.</p>"
        "<p>질문은 계속 보낼 수 있지만 응답이 평소보다 천천히 진행됩니다.</p>"
        "<p>관리자가 해제할 때까지 적용됩니다.</p>"
    )
    return InboxMessage(
        user_id=user_id,
        notice_id=None,
        popup_id=None,
        type="system",
        title="자동 제한이 적용되었습니다.",
        body_html=sanitize_body_html(body),
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
    redis_rl=None,
) -> dict[str, Any]:
    """epics AC-4 — 분류·상태·기간 필터 + 페이지네이션.

    같은 (target_user_id, type) — target_user_id 가 NULL 이면 (ip, type) — 조합은
    하나의 row 로 묶어 가장 최근 이벤트만 노출한다. 누적 횟수(occurrence_count)와
    가장 최근 발생 시각(last_occurred_at)을 함께 동봉하여 상세 드로어에서 history 를
    펼쳐볼 수 있게 한다.

    상태 필터는 그룹 대표(가장 최근) 이벤트의 status 기준으로 적용된다.
    'unblocked' 상태도 보존 — 자동제한/차단 해제 후에도 리스트에서 추적 가능.
    """
    # target_user_id 가 있으면 user 기준, 없으면 ip 기준 그룹핑.
    group_key = func.coalesce(
        cast(AnomalyEvent.target_user_id, String),
        func.concat("ip:", func.coalesce(AnomalyEvent.ip, "unknown")),
    )

    # 1) 그룹 전체 통계 (필터 무관) — 누적 횟수 + 마지막 발생 시각.
    totals_subq = (
        select(
            AnomalyEvent.type.label("g_type"),
            group_key.label("g_key"),
            func.count().label("oc"),
            func.max(AnomalyEvent.created_at).label("la"),
        )
        .group_by(AnomalyEvent.type, group_key)
    ).subquery("anomaly_group_totals")

    # 2) 필터 적용 후 그룹별 최신 1건 선정 (row_number).
    ranked_q = (
        select(
            AnomalyEvent.id.label("event_id"),
            AnomalyEvent.type.label("ev_type"),
            group_key.label("g_key"),
            func.row_number().over(
                partition_by=[AnomalyEvent.type, group_key],
                order_by=[AnomalyEvent.created_at.desc(), AnomalyEvent.id.desc()],
            ).label("rn"),
        )
        .outerjoin(User, AnomalyEvent.target_user_id == User.id)
        .where(or_(AnomalyEvent.target_user_id.is_(None), User.role != "admin"))
    )

    if status_in is None or len(status_in) == 0:
        ranked_q = ranked_q.where(AnomalyEvent.status == "new")
    else:
        ranked_q = ranked_q.where(AnomalyEvent.status.in_(status_in))

    if type_in:
        ranked_q = ranked_q.where(AnomalyEvent.type.in_(type_in))

    if target_user_id is not None:
        ranked_q = ranked_q.where(AnomalyEvent.target_user_id == target_user_id)

    if from_dt is not None:
        ranked_q = ranked_q.where(AnomalyEvent.created_at >= from_dt)
    if to_dt is not None:
        ranked_q = ranked_q.where(AnomalyEvent.created_at <= to_dt)

    ranked_subq = ranked_q.subquery("anomaly_ranked")

    base_q = (
        select(AnomalyEvent, totals_subq.c.oc, totals_subq.c.la)
        .join(ranked_subq, ranked_subq.c.event_id == AnomalyEvent.id)
        .join(
            totals_subq,
            and_(
                totals_subq.c.g_type == ranked_subq.c.ev_type,
                totals_subq.c.g_key == ranked_subq.c.g_key,
            ),
        )
        .where(ranked_subq.c.rn == 1)
    )

    count_q = select(func.count()).select_from(base_q.subquery())
    total = (await db.execute(count_q)).scalar_one()

    items_q = (
        base_q.order_by(AnomalyEvent.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    rows = (await db.execute(items_q)).all()

    user_ids = {
        r.AnomalyEvent.target_user_id
        for r in rows
        if r.AnomalyEvent.target_user_id is not None
    }
    # 사용자별 현재 차단/자동제한 상태를 함께 가져온다 — 리스트 배지 라벨이
    # 사건 발생 시점이 아닌 "지금 이 사용자에게 어떤 제재가 걸려 있는가" 를 보여줘야 하기 때문.
    user_map: dict[int, dict[str, Any]] = {}
    if user_ids:
        # 탈퇴 사용자는 마스킹된 이메일도 노출하지 않는다 (Story 6.1 검색 정책 일관).
        user_rows = (
            await db.execute(
                select(
                    User.id,
                    User.email,
                    User.subscription_status,
                    User.blocked_until,
                    User.anomaly_throttled_at,
                )
                .where(User.id.in_(user_ids))
                .where(User.withdrawn_at.is_(None))
            )
        ).all()
        user_map = {
            row.id: {
                "email": row.email,
                "subscription_status": row.subscription_status,
                "blocked_until": row.blocked_until,
                "anomaly_throttled_at": row.anomaly_throttled_at,
            }
            for row in user_rows
        }

    # login_brute_force 의 Redis 자동 락아웃도 자동제한으로 본다 — 이메일별 lockout/hard_lock
    # 키 존재 여부를 한 번에 조회한다.
    lbf_locked_emails: set[str] = set()
    if redis_rl is not None:
        lbf_emails = [
            user_map[r.AnomalyEvent.target_user_id]["email"]
            for r in rows
            if r.AnomalyEvent.type == "login_brute_force"
            and r.AnomalyEvent.target_user_id is not None
            and r.AnomalyEvent.target_user_id in user_map
        ]
        for email in set(lbf_emails):
            try:
                exists_lockout = await redis_rl.exists(
                    _LOGIN_LOCKOUT_KEY.format(email=email)
                )
                exists_hard = await redis_rl.exists(
                    _LOGIN_HARD_LOCK_KEY.format(email=email)
                )
                if exists_lockout or exists_hard:
                    lbf_locked_emails.add(email)
            except Exception:
                logger.error(
                    "anomaly.list.lbf_lockout_read_failed",
                    email=email,
                    exc_info=True,
                )

    now_dt = datetime.now(tz=timezone.utc)

    # 주의 계정(watch list) 등록 여부 — target_user_id 가 있는 행에 한해 채운다.
    watched_user_ids: set[int] = set()
    if user_ids:
        watched_rows = (
            await db.execute(
                select(UserWatchFlag.user_id).where(
                    UserWatchFlag.user_id.in_(user_ids)
                )
            )
        ).scalars().all()
        watched_user_ids = {int(x) for x in watched_rows}

    items = []
    for r in rows:
        ev = r.AnomalyEvent
        user_data = (
            user_map.get(ev.target_user_id) if ev.target_user_id is not None else None
        )

        blocked_now = False
        throttled_now = False
        if user_data is not None:
            bu = user_data["blocked_until"]
            blocked_now = (
                (bu is not None and bu > now_dt)
                or user_data["subscription_status"] == "blocked"
            )
            throttled_now = user_data["anomaly_throttled_at"] is not None
            if (
                ev.type == "login_brute_force"
                and user_data["email"] in lbf_locked_emails
            ):
                throttled_now = True

        items.append(
            {
                "id": ev.id,
                "type": ev.type,
                "target_user_id": ev.target_user_id,
                "target_user_email_masked": (
                    _mask_email(user_data["email"]) if user_data is not None else None
                ),
                "ip": ev.ip,
                "ua": ev.ua,
                "details": ev.details or {},
                "status": ev.status,
                "reviewed_by_admin_id": ev.reviewed_by_admin_id,
                "reviewed_at": ev.reviewed_at,
                "created_at": ev.created_at,
                "occurrence_count": int(r.oc or 1),
                "last_occurred_at": r.la,
                "user_blocked_now": blocked_now,
                "user_auto_throttled_now": throttled_now,
                "is_watched": (
                    ev.target_user_id is not None
                    and ev.target_user_id in watched_user_ids
                ),
            }
        )

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
    redis_rl=None,
) -> dict[str, Any]:
    """이상탐지 상세 드로어용 — 단건 + 누적 통계 + 대상 사용자 현황.

    반환 dict 키:
      - id, type, target_user_id, target_user_email_masked, ip, ua, details, status,
        reviewed_by_admin_id, reviewed_at, created_at, admin_memo
      - auto_actioned, occurrence_count, last_occurred_at
      - user_subscription_status, user_blocked_until, user_block_reason,
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
    # login_brute_force 도 탐지 즉시 Redis 락아웃이 자동 적용되므로 auto_actioned 으로 본다.
    # 상태 배지가 '신규' 가 아니라 '자동제한' 으로 표시되도록 일관성을 맞춤.
    base["auto_actioned"] = bool(
        details_dict.get("auto_actioned")
        or event.type
        in ("rapid_followup_questions", "repeated_question", "login_brute_force")
    )

    # 누적 탐지 — 같은 (target_user_id, type) 조합, target_user_id 가 NULL 이면 (ip, type) 로.
    history_q = select(AnomalyEvent).where(AnomalyEvent.type == event.type)
    if event.target_user_id is not None:
        history_q = history_q.where(
            AnomalyEvent.target_user_id == event.target_user_id
        )
    elif event.ip is not None:
        history_q = history_q.where(AnomalyEvent.ip == event.ip)
    else:
        # target_user_id / ip 모두 없는 예외 케이스는 자기 자신만.
        history_q = history_q.where(AnomalyEvent.id == event.id)
    history_q = history_q.order_by(
        AnomalyEvent.created_at.desc(), AnomalyEvent.id.desc()
    )
    history_rows = (await db.execute(history_q)).scalars().all()

    base["occurrence_count"] = len(history_rows)
    base["last_occurred_at"] = (
        history_rows[0].created_at if history_rows else event.created_at
    )
    base["history"] = [
        {
            "id": h.id,
            "status": h.status,
            "ip": h.ip,
            "ua": h.ua,
            "details": h.details or {},
            "reviewed_by_admin_id": h.reviewed_by_admin_id,
            "reviewed_at": h.reviewed_at,
            "created_at": h.created_at,
        }
        for h in history_rows
    ]

    # 주의 계정(watch list) 등록 여부 — target_user_id 가 있는 경우만 의미.
    base["is_watched"] = False
    if event.target_user_id is not None:
        watched_row = (
            await db.execute(
                select(UserWatchFlag.id).where(
                    UserWatchFlag.user_id == event.target_user_id
                )
            )
        ).scalar_one_or_none()
        base["is_watched"] = watched_row is not None

    # 대상 사용자 현황.
    user_email: str | None = None
    if event.target_user_id is not None:
        user_row = (
            await db.execute(select(User).where(User.id == event.target_user_id))
        ).scalar_one_or_none()
        if user_row is not None:
            base["user_subscription_status"] = user_row.subscription_status
            base["user_blocked_until"] = user_row.blocked_until
            base["user_block_reason"] = user_row.block_reason
            base["user_anomaly_throttled_at"] = user_row.anomaly_throttled_at
            user_email = user_row.email
        else:
            base["user_subscription_status"] = None
    else:
        base["user_subscription_status"] = None

    # login_brute_force 의 Redis 자동 락아웃 상태. anomaly_event 만으로는 보이지 않아
    # 관리자가 "신규" 만 보고 끝나는 문제가 있어 상세에 함께 노출한다.
    base["login_auto_lockout_until"] = None
    base["login_hard_locked"] = False
    if (
        event.type == "login_brute_force"
        and user_email is not None
        and redis_rl is not None
    ):
        state = await _read_login_lockout_state(redis_rl, user_email)
        base["login_auto_lockout_until"] = state["lockout_until"]
        base["login_hard_locked"] = state["hard_locked"]

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
    10분 윈도우 ZCARD ≥ 3 시 관련 사용자별로 AnomalyEvent INSERT.

    관리자가 사용자별로 개별 차단할 수 있도록 사용자당 한 row를 만든다.
    멱등 키: `concurrent_ip_user_flagged:{ip}:{user_id}` 10분 NX — 같은 IP 같은 사용자는
    10분 안에 두 번 기록되지 않는다. 임계 도달 후 합류한 추가 사용자(4번째 이후)도
    각자의 NX 키가 비어 있다면 새로 INSERT 된다.
    """
    if ip is None:
        return

    # 관리자 편집 임계 — 윈도우/명수. fail-safe 폴백.
    window_seconds = await _resolve_concurrent_ip_window_seconds()
    threshold = await _resolve_concurrent_ip_threshold()

    ip_key = f"login:ip:{ip}"
    now_ts = time.time()
    window_start = now_ts - window_seconds

    try:
        await redis_rl.zadd(ip_key, {str(user_id): now_ts})
        await redis_rl.zremrangebyscore(ip_key, "-inf", window_start)
        await redis_rl.expire(ip_key, window_seconds)
        members = await redis_rl.zrange(ip_key, 0, -1)
        distinct_user_ids = sorted({int(m) for m in members})

        if len(distinct_user_ids) < threshold:
            return

        inserted: list[AnomalyEvent] = []
        for uid in distinct_user_ids:
            user_flag_key = f"concurrent_ip_user_flagged:{ip}:{uid}"
            flag_ok = await redis_rl.set(user_flag_key, "1", ex=window_seconds, nx=True)
            if not flag_ok:
                continue

            co_user_ids = [other for other in distinct_user_ids if other != uid][:10]
            event = AnomalyEvent(
                type="concurrent_ip_login",
                target_user_id=uid,
                ip=ip,
                # UA는 이 호출에서 직접 로그인한 사용자(user_id)만 알 수 있다.
                # 다른 user_id 의 UA는 이전 호출 컨텍스트라 현재 호출에서는 알 수 없으므로 None.
                ua=ua if uid == user_id else None,
                details={
                    "distinct_user_count": len(distinct_user_ids),
                    "co_user_ids": co_user_ids,
                },
                status="new",
                created_at=datetime.now(tz=timezone.utc),
            )
            db.add(event)
            inserted.append(event)

        if not inserted:
            return

        try:
            await db.flush()
        except Exception:
            await db.rollback()
            logger.error("anomaly.concurrent_ip_login.insert_failed", exc_info=True)
            return

        for event in inserted:
            logger.info(
                "anomaly.concurrent_ip_login.detected",
                ip=ip,
                target_user_id=event.target_user_id,
                distinct_user_count=len(distinct_user_ids),
                anomaly_id=event.id,
            )

            await schedule_admin_anomaly_alimtalk(
                db=db,
                anomaly_id=event.id,
                anomaly_type="concurrent_ip_login",
                target_user_id=event.target_user_id,
                ip=ip,
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
    ip: str | None = None,
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

    # 관리자 편집 가능 임계 — 윈도우(초) + 연속 횟수. fail-safe 폴백.
    window_seconds = await _resolve_rapid_followup_window_seconds()
    streak_threshold = await _resolve_rapid_followup_threshold()

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

    if delta > window_seconds or delta < 0:
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

    if streak < streak_threshold:
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
            # 신규 throttle 적용 시점에 사용자 쪽지함으로 안내. 멱등 보강 — 이미
            # throttled 상태였다면(중복 발생) 쪽지 중복 발송 방지로 skip.
            db.add(
                _build_auto_throttle_inbox_message(
                    user_id=user_id, anomaly_type="rapid_followup_questions"
                )
            )

        # rapid_followup 은 시스템이 즉시 자동조치(throttle)를 적용하므로
        # 등록 시점에 바로 actioned + 자동검토 처리. reviewed_by_admin_id=None 이
        # "시스템 자동조치" 표식 — 24h/7d/영구차단 액션 분기와 구분된다.
        now_dt2 = datetime.now(tz=timezone.utc)
        event = AnomalyEvent(
            type="rapid_followup_questions",
            target_user_id=user_id,
            ip=ip,
            ua=None,
            details={
                "streak": int(streak),
                "window_seconds": float(window_seconds),
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

        await schedule_admin_anomaly_alimtalk(
            db=db,
            anomaly_id=event.id,
            anomaly_type="rapid_followup_questions",
            target_user_id=user_id,
            ip=ip,
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


async def check_repeated_question(
    *,
    user_id: int,
    subscription_status: str,
    question_text: str,
    redis_quota,
    db: AsyncSession,
    ip: str | None = None,
) -> bool:
    """qa_service.preflight 내 hook. admin 은 skip.

    동작:
      1. ``question_text.strip()`` 을 직전 질문과 비교.
      2. 동일하면 streak INCR (1h TTL). 다르면 streak=1 으로 리셋.
      3. streak >= 3 도달 시 anomaly 발생 — rapid_followup_questions 와 동일 조치
         (AnomalyEvent type='repeated_question' INSERT(actioned) + users.anomaly_throttled_at SET).

    반환: 본 호출에서 throttle 이 새로 적용되었는지(True/False).
    이미 적용 중인 사용자는 False (qa_service 가 user.anomaly_throttled_at 으로 적용 분기).
    """
    if subscription_status == "admin":
        return False

    normalized = (question_text or "").strip()
    if not normalized:
        return False

    # 관리자 편집 가능 임계. fail-safe 폴백.
    streak_threshold = await _resolve_repeated_question_threshold()

    last_key = _REPEATED_QUESTION_LAST_KEY.format(user_id=user_id)
    streak_key = _REPEATED_QUESTION_STREAK_KEY.format(user_id=user_id)

    try:
        prev = await redis_quota.get(last_key)
    except Exception:
        logger.error("anomaly.repeated_question.redis_read_failed", exc_info=True)
        return False

    if isinstance(prev, bytes):
        prev = prev.decode("utf-8", errors="replace")

    try:
        if prev == normalized:
            streak = await redis_quota.incr(streak_key)
        else:
            await redis_quota.set(streak_key, "1", ex=_REPEATED_QUESTION_TTL)
            streak = 1
        await redis_quota.set(last_key, normalized, ex=_REPEATED_QUESTION_TTL)
        if streak == 1:
            await redis_quota.expire(streak_key, _REPEATED_QUESTION_TTL)
    except Exception:
        logger.error("anomaly.repeated_question.streak_incr_failed", exc_info=True)
        return False

    if streak < streak_threshold:
        return False

    try:
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
            # 신규 throttle 적용 시점에 사용자 쪽지함으로 안내. 이미 throttled 라면
            # 중복 발송 방지로 skip — rapid_followup 분기와 동일 규칙.
            db.add(
                _build_auto_throttle_inbox_message(
                    user_id=user_id, anomaly_type="repeated_question"
                )
            )

        now_dt2 = datetime.now(tz=timezone.utc)
        # rapid_followup 과 동일 — 시스템 즉시 자동조치이므로 INSERT 시점에 actioned 처리.
        event = AnomalyEvent(
            type="repeated_question",
            target_user_id=user_id,
            ip=ip,
            ua=None,
            details={
                "streak": int(streak),
                "question_excerpt": normalized[:80],
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
            logger.error("anomaly.repeated_question.insert_failed", exc_info=True)
            return False

        # 재발 시 다시 0부터.
        try:
            await redis_quota.delete(streak_key)
            await redis_quota.delete(last_key)
        except Exception:
            pass

        logger.info(
            "anomaly.repeated_question.detected",
            user_id=user_id,
            streak=int(streak),
            already_throttled=already_throttled,
            anomaly_id=event.id,
        )

        await schedule_admin_anomaly_alimtalk(
            db=db,
            anomaly_id=event.id,
            anomaly_type="repeated_question",
            target_user_id=user_id,
            ip=ip,
        )

        return not already_throttled
    except Exception:
        logger.error("anomaly.repeated_question.hook_failed", exc_info=True)
        return False


# ── login_brute_force 자동 락아웃(이메일 기반) ─────────────────────────────────
# auth_service 의 _LOGIN_LOCKOUT_KEY / _LOGIN_HARD_LOCK_KEY / _LOGIN_STAGE_KEY /
# _LOGIN_FAIL_KEY 와 키 패턴을 공유한다. 직접 import 하지 않고 동일한 문자열을 쓰는 것은
# 순환 import(auth_service → anomaly_service → auth_service) 방지를 위함.
_LOGIN_FAIL_KEY = "login_fail:{email}"
_LOGIN_LOCKOUT_KEY = "login_lockout:{email}"
_LOGIN_STAGE_KEY = "login_stage:{email}"
_LOGIN_HARD_LOCK_KEY = "login_hard_lock:{email}"


async def _read_login_lockout_state(redis_rl, email: str) -> dict[str, Any]:
    """이메일별 1차/2차 락아웃 상태를 읽어 상세 응답에 동봉할 형태로 반환한다.

    - lockout_until: 1차(10분) 잠금이 활성이면 만료 시각(UTC), 아니면 None.
    - hard_locked: 2차(비번찾기 전까지) 잠금 활성 여부.
    """
    try:
        lockout_ttl = await redis_rl.ttl(_LOGIN_LOCKOUT_KEY.format(email=email))
        hard_exists = await redis_rl.exists(_LOGIN_HARD_LOCK_KEY.format(email=email))
    except Exception:
        logger.error("anomaly.login_lockout.read_failed", exc_info=True)
        return {"lockout_until": None, "hard_locked": False}

    lockout_until: datetime | None = None
    # redis-py: 키 미존재 → -2, TTL 없음(영구) → -1, 그 외 양수 → 남은 초.
    if isinstance(lockout_ttl, int) and lockout_ttl > 0:
        lockout_until = datetime.now(tz=timezone.utc).replace(
            microsecond=0
        ) + timedelta(seconds=lockout_ttl)
    return {
        "lockout_until": lockout_until,
        "hard_locked": bool(hard_exists),
    }


async def clear_user_login_lockout(
    *,
    email: str,
    redis_rl,
) -> dict[str, bool]:
    """login_brute_force 자동 락아웃을 수동 해제. 호출자: 라우터 DELETE
    /admin/users/{id}/login-lockout.

    fail counter / stage 표식 / 1차 lockout / 2차 hard_lock 키를 모두 정리한다.
    이미 해제 상태였더라도 멱등으로 동작한다.

    반환: 어떤 키가 실제로 지워졌는지(감사 로그 보조 목적).
    """
    cleared = {
        "fail": False,
        "lockout": False,
        "stage": False,
        "hard_lock": False,
    }
    pairs = (
        ("fail", _LOGIN_FAIL_KEY.format(email=email)),
        ("lockout", _LOGIN_LOCKOUT_KEY.format(email=email)),
        ("stage", _LOGIN_STAGE_KEY.format(email=email)),
        ("hard_lock", _LOGIN_HARD_LOCK_KEY.format(email=email)),
    )
    for label, key in pairs:
        try:
            removed = await redis_rl.delete(key)
            cleared[label] = bool(removed)
        except Exception:
            logger.error("anomaly.login_lockout.clear_failed", key=key, exc_info=True)
    return cleared


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

    # NOTE: actioned anomaly 이력은 그대로 보존한다. 자동제한/차단 해제 이후에도
    # 이상탐지 리스트에서 사라지지 않게 — 현재 적용 여부는 user_anomaly_throttled_at /
    # user_subscription_status 필드로 상세 드로어에서 확인할 수 있다.

    if redis_quota is not None:
        for key in (
            _RAPID_FOLLOWUP_STREAK_KEY.format(user_id=user_id),
            _REPEATED_QUESTION_STREAK_KEY.format(user_id=user_id),
            _REPEATED_QUESTION_LAST_KEY.format(user_id=user_id),
        ):
            try:
                await redis_quota.delete(key)
            except Exception:
                pass

    return True


# ── 관리자 알림톡 schedule (admin.anomaly_detected / UH_9849) ─────────────────


async def schedule_admin_anomaly_alimtalk(
    *,
    db: AsyncSession,
    anomaly_id: int,
    anomaly_type: str,
    target_user_id: int | None,
    ip: str | None = None,
) -> None:
    """이상탐지 발생 시 관리자에게 알림톡 발송을 예약한다 (template: admin.anomaly_detected).

    notification_queue 에 status='queued' INSERT — Celery dispatch_queued (5분 간격)가
    실제 발송을 담당한다. 같은 DB 세션에서 anomaly_event INSERT 와 함께 커밋된다.

    수신자: resolve_admin_target — admin 또는 phone 없으면 silent skip.
    멱등 키: f"anomaly:{anomaly_id}:admin_alert" — 동일 anomaly 중복 enqueue 차단
    (UNIQUE index uq_notification_queue_idempotency 파셜 인덱스 ON CONFLICT DO NOTHING).

    호출 위치: 각 AnomalyEvent INSERT 직후 (db.flush() 로 event.id 확보 후).
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from api.src.integrations.messaging.admin_recipient import resolve_admin_target
    from api.src.models.notification_queue import (
        CHANNEL_ALIMTALK,
        STATUS_QUEUED,
        NotificationQueue,
    )

    try:
        admin, admin_phone = await resolve_admin_target(db)
    except Exception:
        logger.error("anomaly.admin_alimtalk.resolve_failed", exc_info=True)
        return

    if admin is None or not admin_phone:
        logger.info(
            "anomaly.admin_alimtalk.skip_no_admin_phone",
            anomaly_id=anomaly_id,
            anomaly_type=anomaly_type,
        )
        return

    label = ANOMALY_TYPE_LABELS_KO.get(anomaly_type, anomaly_type)
    user_identifier = await _resolve_anomaly_user_identifier(
        db, target_user_id=target_user_id, ip=ip
    )

    now_dt = datetime.now(tz=timezone.utc).replace(tzinfo=None)
    stmt = (
        pg_insert(NotificationQueue)
        .values(
            user_id=admin.id,
            template_code="admin.anomaly_detected",
            variables={
                "anomaly_type": label,
                "user_identifier": user_identifier,
            },
            channel=CHANNEL_ALIMTALK,
            status=STATUS_QUEUED,
            attempts=0,
            idempotency_key=f"anomaly:{anomaly_id}:admin_alert",
            created_at=now_dt,
        )
        .on_conflict_do_nothing(
            index_elements=["user_id", "template_code", "idempotency_key"],
            index_where=NotificationQueue.user_id.is_not(None),
        )
    )
    try:
        await db.execute(stmt)
        logger.info(
            "anomaly.admin_alimtalk.enqueued",
            anomaly_id=anomaly_id,
            anomaly_type=anomaly_type,
            admin_user_id=admin.id,
        )
    except Exception:
        # 큐 INSERT 실패는 silent — 이상탐지 자체는 이미 기록됐고 알림톡은 best-effort.
        logger.error(
            "anomaly.admin_alimtalk.enqueue_failed",
            anomaly_id=anomaly_id,
            exc_info=True,
        )


async def _resolve_anomaly_user_identifier(
    db: AsyncSession,
    *,
    target_user_id: int | None,
    ip: str | None,
) -> str:
    """알림톡 본문 {user_identifier} 변수 결정. email > user_id > IP > "비로그인 사용자"."""
    if target_user_id is not None:
        try:
            email = (
                await db.execute(
                    select(User.email).where(User.id == target_user_id)
                )
            ).scalar_one_or_none()
            if email:
                return email
        except Exception:
            pass
        return f"user_id:{target_user_id}"
    if ip:
        return f"IP:{ip}"
    return "비로그인 사용자"


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
        "is_watched": False,
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
    "ANOMALY_TYPE_LABELS_KO",
    "RAPID_FOLLOWUP_WINDOW_SECONDS",
    "RAPID_FOLLOWUP_STREAK_THRESHOLD",
    "REPEATED_QUESTION_STREAK_THRESHOLD",
    "REPEATED_QUESTION_WINDOW_SECONDS",
    "list_anomaly_events",
    "get_anomaly_detail",
    "update_anomaly_memo",
    "mark_anomaly_reviewed",
    "mark_anomaly_actioned",
    "check_concurrent_ip_login",
    "check_rapid_followup_questions",
    "check_repeated_question",
    "record_stream_done",
    "clear_user_anomaly_throttle",
    "clear_user_login_lockout",
    "schedule_admin_anomaly_alimtalk",
]
