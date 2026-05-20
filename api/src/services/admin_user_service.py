"""Story 6.1 — Admin 사용자 통합 검색·상세 도메인 로직.

본 모듈은 두 가지 진입점을 제공한다:
- search_users(...): 이메일/휴대폰/카드 뒷4자리 OR-검색 + 필터 + 페이지네이션
- get_user_detail(user_id): Drawer 4 섹션(기본/결제/최근 QA/이상 이벤트) 단건 조회

설계 결정:
- OR-검색은 단일 WHERE 절(or_)로 작성. q가 비어있거나 미지정이면 OR 분기 자체를 SQL에서 제외.
- card_last4 매칭은 q 길이가 정확히 4이고 모두 숫자일 때만 EXISTS billing_keys 분기 평가
  (불필요한 join 비용 절감, NFR-P5).
- 활성 빌링키 LEFT JOIN 은 user당 1건 제약을 service 레이어에서 강제하지 않고
  중복 시 MAX(card_last4) 결정론적 선택 + structlog warn 로그(0건이면 침묵).
- total은 동일 WHERE 절을 적용한 SELECT COUNT(*) 1쿼리, items는 페이지네이션 적용된
  본 SELECT 1쿼리 — 합 2쿼리(N+1 금지).
- 정렬은 (subscription_status='blocked')::int DESC, withdrawn_at IS NULL DESC, created_at DESC.
  CASE WHEN 패턴으로 인덱스 호환성 확보.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

import structlog
from fastapi import HTTPException
from sqlalchemy import case, exists, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.anomaly_event import AnomalyEvent
from api.src.models.billing_key import BillingKey
from api.src.models.qa_log import QALog
from api.src.models.subscription import Subscription
from api.src.models.user import User
from api.src.schemas.admin.users import (
    RecentAnomalyEvent,
    RecentQALog,
    SubscriptionSummary,
    UserDetailResponse,
    UserSearchItem,
    UserSearchListResponse,
)

logger = structlog.get_logger(__name__)

_RECENT_QA_LIMIT = 5
_RECENT_ANOMALY_LIMIT = 3
_KST = ZoneInfo("Asia/Seoul")


def _kst_created_range(
    f: date | None, t: date | None
) -> tuple[datetime | None, datetime | None]:
    """가입일(created_at) from/to 날짜를 KST [시작, 끝+1일) datetime 범위로 변환.

    admin_support_service._kst_date_range와 동일 패턴. 종료일은 그날 끝까지
    포함되도록 다음날 00:00 KST를 exclusive upper bound로 사용한다.
    """
    start_dt: datetime | None = None
    end_dt: datetime | None = None
    if f is not None:
        start_dt = datetime.combine(f, time.min).replace(tzinfo=_KST)
    if t is not None:
        end_dt = datetime.combine(t + timedelta(days=1), time.min).replace(tzinfo=_KST)
    return start_dt, end_dt


def _is_card_last4_query(q: str) -> bool:
    """q가 카드 뒷4자리 매칭 분기를 평가할 가치가 있는지 결정.

    정확히 4자리이고 모두 숫자일 때만 billing_keys 서브쿼리를 평가한다.
    """
    return len(q) == 4 and q.isdigit()


def _build_or_clause(q: str | None) -> Any | None:
    """q OR-검색 절(이메일 ILIKE / 휴대폰 LIKE / card_last4 EXISTS)을 생성.

    q가 비어있거나 미지정이면 None을 반환해 호출자가 WHERE 절에서 제외하도록 한다.
    """
    if not q:
        return None
    pattern = f"%{q}%"
    branches = [
        func.lower(User.email).like(func.lower(pattern)),
    ]
    # 휴대폰은 NULL 가능 — LIKE 자체가 NULL을 자동 제외함
    branches.append(User.phone.like(pattern))

    if _is_card_last4_query(q):
        billing_exists = (
            select(literal(1))
            .where(
                BillingKey.user_id == User.id,
                BillingKey.is_active.is_(True),
                BillingKey.card_last4 == q,
            )
            .exists()
        )
        branches.append(billing_exists)

    return or_(*branches)


async def _resolve_active_billing_keys(
    db: AsyncSession, user_ids: list[int]
) -> dict[int, tuple[str | None, str | None]]:
    """해당 user_id 집합의 활성 빌링키를 user_id → (card_last4, card_company) dict로 반환.

    한 user에 활성 빌링키가 2건 이상이면 MAX(card_last4) 결정론적 선택 + warn 로그.
    """
    if not user_ids:
        return {}
    rows = (
        await db.execute(
            select(BillingKey.user_id, BillingKey.card_last4, BillingKey.card_company)
            .where(BillingKey.user_id.in_(user_ids), BillingKey.is_active.is_(True))
            .order_by(BillingKey.user_id, BillingKey.card_last4)
        )
    ).all()

    grouped: dict[int, list[tuple[str | None, str | None]]] = {}
    for row in rows:
        grouped.setdefault(row.user_id, []).append((row.card_last4, row.card_company))

    result: dict[int, tuple[str | None, str | None]] = {}
    for uid, entries in grouped.items():
        if len(entries) > 1:
            logger.warning(
                "admin.users.duplicate_active_billing_key",
                target_user_id=uid,
                active_count=len(entries),
            )
            entries.sort(key=lambda t: (t[0] or ""), reverse=True)
        result[uid] = entries[0]
    return result


def _serialize_user(
    user: User, billing: tuple[str | None, str | None] | None
) -> UserSearchItem:
    """User ORM + 빌링키 튜플을 응답 schema로 직렬화."""
    card_last4, card_company = billing if billing else (None, None)
    is_blocked = user.subscription_status == "blocked"
    return UserSearchItem(
        user_id=user.id,
        email=user.email,
        phone=user.phone,
        segment=user.segment,
        years_of_experience=user.years_of_experience,
        subscription_status=user.subscription_status,  # type: ignore[arg-type]
        is_blocked=is_blocked,
        block_until=None,  # Story 6.2 채움
        daily_quota_override=user.daily_quota_override,
        free_delay_override=(
            float(user.free_delay_override) if user.free_delay_override is not None else None
        ),
        created_at=user.created_at,
        last_login_at=None,  # Story 6.2 채움
        withdrawn_at=user.withdrawn_at,
        pro_since=None,  # Story 6.2-followup
        card_last4=card_last4,
        card_company=card_company,
    )


async def search_users(
    db: AsyncSession,
    *,
    q: str | None = None,
    segment: Literal["doctor", "hygienist", "student_other"] | None = None,
    subscription_status: Literal["free", "pro", "blocked"] | None = None,
    blocked: bool | None = None,
    created_from: date | None = None,
    created_to: date | None = None,
    page: int = 1,
    per_page: int = 20,
) -> UserSearchListResponse:
    """이메일/휴대폰/카드 뒷4자리 OR-검색 + 필터 + 페이지네이션.

    blocked=True 면 subscription_status='blocked'만, blocked=False 면 그 외만,
    None이면 모든 상태를 포함한다.

    created_from/created_to 는 KST 기준 가입일 범위 필터(양 끝일 포함). 한쪽만
    지정해도 동작한다.
    """
    # 1. WHERE 절 구성 — None인 필터는 SQL에서 제외 (불필요한 분기 회피)
    conditions: list[Any] = [User.role != "admin"]  # 관리자 계정 제외
    if segment is not None:
        conditions.append(User.segment == segment)
    if subscription_status is not None:
        conditions.append(User.subscription_status == subscription_status)
    if blocked is True:
        conditions.append(User.subscription_status == "blocked")
    elif blocked is False:
        conditions.append(User.subscription_status != "blocked")

    start_dt, end_dt = _kst_created_range(created_from, created_to)
    if start_dt is not None:
        conditions.append(User.created_at >= start_dt)
    if end_dt is not None:
        conditions.append(User.created_at < end_dt)

    or_clause = _build_or_clause((q or "").strip() or None)
    if or_clause is not None:
        conditions.append(or_clause)

    # 2. total 카운트 1쿼리 (페이지네이션 메타)
    total_stmt = select(func.count()).select_from(User)
    if conditions:
        total_stmt = total_stmt.where(*conditions)
    total = (await db.execute(total_stmt)).scalar_one()

    # 3. items 페이지 SELECT 1쿼리 — 정렬 키 CASE WHEN으로 인덱스 호환
    blocked_first = case((User.subscription_status == "blocked", 0), else_=1)
    withdrawn_last = case((User.withdrawn_at.is_(None), 0), else_=1)

    items_stmt = (
        select(User)
        .order_by(blocked_first.asc(), withdrawn_last.asc(), User.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    if conditions:
        items_stmt = items_stmt.where(*conditions)

    user_rows = (await db.execute(items_stmt)).scalars().all()

    # 4. 활성 빌링키 1쿼리 — user_id 집합으로 IN 쿼리 (N+1 방지)
    user_ids = [u.id for u in user_rows]
    billing_map = await _resolve_active_billing_keys(db, user_ids)

    items = [_serialize_user(u, billing_map.get(u.id)) for u in user_rows]

    return UserSearchListResponse(
        items=items, page=page, per_page=per_page, total=int(total)
    )


async def get_user_detail(db: AsyncSession, user_id: int) -> UserDetailResponse:
    """단건 사용자 상세 — 기본 정보 + 결제 요약 + 최근 QA 5 + 이상 이벤트 3.

    존재하지 않으면 404 ADMIN_USER_NOT_FOUND.
    """
    user = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "ADMIN_USER_NOT_FOUND",
                "message": "사용자를 찾을 수 없습니다.",
            },
        )

    billing_map = await _resolve_active_billing_keys(db, [user.id])
    billing = billing_map.get(user.id)
    user_item = _serialize_user(user, billing)

    # subscriptions: status='active'인 단일 행 (없으면 NULL 자리)
    subscription = (
        await db.execute(
            select(Subscription)
            .where(Subscription.user_id == user_id, Subscription.status == "active")
            .limit(1)
        )
    ).scalar_one_or_none()

    subscription_summary = SubscriptionSummary(
        current_status=user.subscription_status,  # type: ignore[arg-type]
        billing_key_active=billing is not None,
        card_last4=billing[0] if billing else None,
        card_company=billing[1] if billing else None,
        subscription_started_at=subscription.started_at if subscription else None,
        next_charge_at=subscription.next_charge_at if subscription else None,
    )

    # 최근 QA 5건
    qa_rows = (
        await db.execute(
            select(QALog)
            .where(QALog.user_id == user_id)
            .order_by(QALog.created_at.desc())
            .limit(_RECENT_QA_LIMIT)
        )
    ).scalars().all()
    recent_qa = [
        RecentQALog(
            qa_log_id=row.id,
            question_excerpt=row.question_text or "",
            answer_excerpt=row.answer_text if row.answer_text else None,
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
            cost_usd=row.cost_usd,
            status=row.status,
            created_at=row.created_at,
        )
        for row in qa_rows
    ]

    # 최근 이상 이벤트 3건
    anomaly_rows = (
        await db.execute(
            select(AnomalyEvent)
            .where(AnomalyEvent.target_user_id == user_id)
            .order_by(AnomalyEvent.created_at.desc())
            .limit(_RECENT_ANOMALY_LIMIT)
        )
    ).scalars().all()
    recent_anomaly = [
        RecentAnomalyEvent(
            id=row.id,
            type=row.type,
            ip=row.ip,
            status=row.status,
            created_at=row.created_at,
        )
        for row in anomaly_rows
    ]

    return UserDetailResponse(
        user=user_item,
        subscription_summary=subscription_summary,
        recent_qa=recent_qa,
        recent_anomaly_events=recent_anomaly,
    )


__all__ = ["search_users", "get_user_detail"]
