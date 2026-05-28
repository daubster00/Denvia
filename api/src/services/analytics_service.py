"""AnalyticsService — Story 5.3 가입자 추세 / 구독 분포, Story 5.4 피드백 분석 도메인 로직.

users 테이블 기존 컬럼(created_at, withdrawn_at, subscription_status)만 SELECT.
신규 마이그레이션 0건. 모든 시간 버킷은 KST(Asia/Seoul) 기준 자정.

집계 패턴:
- get_signups_buckets:
  1) SQL 한 번으로 KST 기준 일별 가입 수 / 일별 탈퇴 수 / 일별 차단 수를 집계.
  2) Python에서 unit(day/week/month/year) 버킷 경계 생성 + prefix-sum으로
     cumulative/active/withdrawn 변환. 빈 버킷은 0으로 채움.
  - 권장 패턴 2 (PR 본문 EXPLAIN ANALYZE 첨부) 채택.
- get_subscriber_counts: status GROUP BY 1쿼리 + withdrawn count 1쿼리.
- get_feedback_summary/series/items/total: qa_feedback JOIN qa_logs JOIN users.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Literal

from typing import Any

from redis.asyncio import Redis as AsyncRedis
from sqlalchemy import and_, case, select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.anomaly_event import AnomalyEvent
from api.src.models.login_event import LoginEvent
from api.src.models.payment import Payment
from api.src.models.payment_event import PaymentEvent
from api.src.models.qa_feedback import QAFeedback
from api.src.models.qa_log import QALog
from api.src.models.subscription import Subscription
from api.src.models.user import User
from api.src.services import runtime_config_service
from api.src.services.budget_service import KST
from api.src.utils.mask import mask_email

Unit = Literal["day", "week", "month", "year"]


@dataclass(frozen=True)
class SignupsBucket:
    bucket_start: date
    cumulative: int
    active: int
    withdrawn: int
    new_signups: int = 0


def _default_window(unit: Unit) -> tuple[date, date]:
    """unit 별 기본 from/to KST 기준 날짜.

    - day:   최근 30일
    - week:  최근 12주
    - month: 최근 12개월(현재 달 포함)
    - year:  최근 5년(현재 연 포함)
    """
    today_kst = datetime.now(KST).date()
    if unit == "day":
        return today_kst - timedelta(days=30), today_kst
    if unit == "week":
        return today_kst - timedelta(weeks=12), today_kst
    if unit == "month":
        start_year = today_kst.year - 1
        start_month = today_kst.month
        return date(start_year, start_month, 1), today_kst
    return date(today_kst.year - 4, 1, 1), today_kst


def _truncate_to_unit(d: date, unit: Unit) -> date:
    """주/월/연 시작일로 d를 내린다 (day는 그대로)."""
    if unit == "day":
        return d
    if unit == "week":
        # 일요일 시작 (Python isoweekday: 월=1, 일=7)
        return d - timedelta(days=d.isoweekday() % 7)
    if unit == "month":
        return date(d.year, d.month, 1)
    return date(d.year, 1, 1)


def _next_bucket(start: date, unit: Unit) -> date:
    if unit == "day":
        return start + timedelta(days=1)
    if unit == "week":
        return start + timedelta(weeks=1)
    if unit == "month":
        if start.month == 12:
            return date(start.year + 1, 1, 1)
        return date(start.year, start.month + 1, 1)
    return date(start.year + 1, 1, 1)


def _bucket_starts(from_: date, to: date, unit: Unit) -> list[date]:
    """from~to 범위에 포함되는 모든 버킷의 시작일 리스트."""
    cur = _truncate_to_unit(from_, unit)
    end_anchor = _truncate_to_unit(to, unit)
    out: list[date] = []
    while cur <= end_anchor:
        out.append(cur)
        cur = _next_bucket(cur, unit)
    return out


async def _daily_counts_kst(
    session: AsyncSession,
    column,
    extra_where=None,
) -> dict[date, int]:
    """주어진 timestamp 컬럼 기준 KST 일별 카운트를 dict[date]→int로 반환."""
    day_expr = func.date(func.timezone("Asia/Seoul", column))
    stmt = select(day_expr.label("d"), func.count(User.id))
    if extra_where is not None:
        stmt = stmt.where(extra_where)
    stmt = stmt.where(column.is_not(None)).group_by(day_expr)
    rows = (await session.execute(stmt)).all()
    out: dict[date, int] = {}
    for d_val, n in rows:
        if isinstance(d_val, datetime):
            d_val = d_val.date()
        out[d_val] = int(n)
    return out


async def get_signups_buckets(
    session: AsyncSession,
    unit: Unit,
    from_: date | None,
    to: date | None,
) -> tuple[list[SignupsBucket], date, date]:
    """unit/from/to 기반 KST 버킷별 cumulative/active/withdrawn 반환.

    cumulative = bucket_end 시점까지의 누적 가입자(탈퇴 포함)
    withdrawn  = bucket_end 시점까지의 누적 탈퇴자
    active     = 해당 시점에 살아있던 사용자 (cumulative - withdrawn - blocked).
                 단, blocked는 subscription_status='blocked' AND withdrawn_at IS NULL.
    """
    if from_ is None and to is None:
        from_, to = _default_window(unit)
    elif from_ is None:
        default_from, _ = _default_window(unit)
        from_ = default_from
    elif to is None:
        _, default_to = _default_window(unit)
        to = default_to

    bucket_starts = _bucket_starts(from_, to, unit)
    if not bucket_starts:
        return [], from_, to

    daily_signups = await _daily_counts_kst(session, User.created_at, extra_where=User.role != "admin")
    daily_withdrawals = await _daily_counts_kst(session, User.withdrawn_at, extra_where=User.role != "admin")
    # 차단 사용자 (현재 시점). 시간 흐름 추적이 어려우므로 마지막 버킷에만 반영.
    blocked_now: int = (await session.execute(
        select(func.count(User.id)).where(
            User.subscription_status == "blocked",
            User.withdrawn_at.is_(None),
            User.role != "admin",
        )
    )).scalar_one()

    # bucket_starts 직전까지의 누적 (from 이전 데이터)
    first_start = bucket_starts[0]
    prior_signups = sum(n for d, n in daily_signups.items() if d < first_start)
    prior_withdrawals = sum(n for d, n in daily_withdrawals.items() if d < first_start)

    cum_signups_running = prior_signups
    cum_withdrawals_running = prior_withdrawals

    buckets: list[SignupsBucket] = []
    for idx, start in enumerate(bucket_starts):
        nxt = _next_bucket(start, unit)
        bucket_end_exclusive = nxt  # bucket includes [start, nxt)

        cum_before = cum_signups_running
        for d, n in daily_signups.items():
            if start <= d < bucket_end_exclusive:
                cum_signups_running += n
        for d, n in daily_withdrawals.items():
            if start <= d < bucket_end_exclusive:
                cum_withdrawals_running += n

        # blocked는 시점별 스냅샷이 없으므로 마지막 버킷에만 반영.
        # (이전 버킷에서는 0으로 처리 — Dev Notes에 한계 명시)
        is_last = idx == len(bucket_starts) - 1
        blocked_for_bucket = blocked_now if is_last else 0

        cumulative = cum_signups_running
        withdrawn = cum_withdrawals_running
        active = max(cumulative - withdrawn - blocked_for_bucket, 0)
        new_signups = cumulative - cum_before

        buckets.append(SignupsBucket(
            bucket_start=start,
            cumulative=cumulative,
            active=active,
            withdrawn=withdrawn,
            new_signups=new_signups,
        ))

    return buckets, from_, to


# =============================================================================
# 접속 통계 — 로그인 이벤트 기반 일/주/월/년 집계
# =============================================================================


@dataclass(frozen=True)
class AccessBucket:
    bucket_start: date
    visitors: int  # 해당 버킷에서 로그인한 고유 회원 수
    visits: int    # 해당 버킷의 로그인 횟수


@dataclass(frozen=True)
class AccessSummary:
    buckets: list[AccessBucket]
    from_: date
    to: date
    # 구간 전체 누적
    total_visitors: int  # 구간 내 고유 회원 수 (DISTINCT user_id)
    total_visits: int    # 구간 내 로그인 횟수 합


async def get_access_buckets(
    session: AsyncSession,
    unit: Unit,
    from_: date | None,
    to: date | None,
) -> AccessSummary:
    """unit/from/to 기반 KST 버킷별 접속자 수 + 접속횟수.

    visitors = COUNT(DISTINCT user_id) per bucket
    visits   = COUNT(*)                per bucket
    빈 버킷은 0으로 채움.
    """
    if from_ is None and to is None:
        from_, to = _default_window(unit)
    elif from_ is None:
        from_, _ = _default_window(unit)
    elif to is None:
        _, to = _default_window(unit)

    bucket_starts = _bucket_starts(from_, to, unit)
    if not bucket_starts:
        return AccessSummary(buckets=[], from_=from_, to=to, total_visitors=0, total_visits=0)

    # KST 기준 day 단위 (user_id, day) 집계 → Python에서 버킷 묶음.
    day_expr = func.date(func.timezone("Asia/Seoul", LoginEvent.created_at))
    range_start_kst = _kst_datetime(bucket_starts[0])
    range_end_exclusive_kst = _kst_datetime(_next_bucket(bucket_starts[-1], unit))
    stmt = (
        select(
            day_expr.label("d"),
            LoginEvent.user_id,
            func.count(LoginEvent.id).label("n"),
        )
        .where(
            LoginEvent.created_at >= range_start_kst,
            LoginEvent.created_at < range_end_exclusive_kst,
        )
        .group_by(day_expr, LoginEvent.user_id)
    )
    rows = (await session.execute(stmt)).all()

    # (date, user_id) -> visits
    by_day_user: dict[tuple[date, int], int] = {}
    for d_val, uid, n in rows:
        if isinstance(d_val, datetime):
            d_val = d_val.date()
        by_day_user[(d_val, int(uid))] = int(n)

    buckets: list[AccessBucket] = []
    total_visits = 0
    total_users: set[int] = set()
    for start in bucket_starts:
        nxt = _next_bucket(start, unit)
        visits = 0
        users: set[int] = set()
        for (d, uid), n in by_day_user.items():
            if start <= d < nxt:
                visits += n
                users.add(uid)
        total_visits += visits
        total_users |= users
        buckets.append(AccessBucket(bucket_start=start, visitors=len(users), visits=visits))

    return AccessSummary(
        buckets=buckets,
        from_=from_,
        to=to,
        total_visitors=len(total_users),
        total_visits=total_visits,
    )


PENDING_CANCELLATIONS_LIST_LIMIT = 100


async def get_subscriber_counts(
    session: AsyncSession,
) -> dict[str, Any]:
    """현재 시점 free/pro/blocked/withdrawn 카운트 + 해지 예약 목록.

    pending_cancellations: status='cancel_pending' 구독을 current_period_end ASC로 정렬.
    pending_cancellation_count: 전체 cancel_pending 건수 (목록 limit과 무관).
    """
    rows = (await session.execute(
        select(User.subscription_status, func.count(User.id))
        .where(User.withdrawn_at.is_(None), User.role != "admin")
        .group_by(User.subscription_status)
    )).all()
    counts = {status: 0 for status in ("free", "pro", "blocked")}
    for status, n in rows:
        if status in counts:
            counts[status] = int(n)

    withdrawn_count = (await session.execute(
        select(func.count(User.id)).where(User.withdrawn_at.is_not(None), User.role != "admin")
    )).scalar_one()

    pending_total = (await session.execute(
        select(func.count(Subscription.id)).where(Subscription.status == "cancel_pending")
    )).scalar_one()

    pending_rows = (await session.execute(
        select(
            Subscription.user_id,
            User.email,
            Subscription.canceled_at,
            Subscription.current_period_end,
        )
        .join(User, User.id == Subscription.user_id)
        .where(Subscription.status == "cancel_pending")
        .order_by(Subscription.current_period_end.asc())
        .limit(PENDING_CANCELLATIONS_LIST_LIMIT)
    )).all()

    pending_cancellations = [
        {
            "user_id": int(user_id),
            "email_masked": mask_email(email),
            "canceled_at": canceled_at,
            "current_period_end": current_period_end,
        }
        for user_id, email, canceled_at, current_period_end in pending_rows
    ]

    return {
        "free_count": counts["free"],
        "pro_count": counts["pro"],
        "blocked_count": counts["blocked"],
        "withdrawn_count": int(withdrawn_count),
        "pending_cancellation_count": int(pending_total),
        "pending_cancellations": pending_cancellations,
    }


# =============================================================================
# Story 5.4 — 피드백 분석 (GOOD/BAD 비율 + 시계열 + 리스트)
# =============================================================================

RatingFilter = Literal["good", "bad", "all"]


def _kst_datetime(d: date) -> datetime:
    """date → KST 자정 datetime."""
    return datetime(d.year, d.month, d.day, tzinfo=KST)


def _feedback_default_window(unit: Literal["day", "week", "month"]) -> tuple[date, date]:
    today = datetime.now(KST).date()
    if unit == "day":
        return today - timedelta(days=30), today
    if unit == "week":
        return today - timedelta(weeks=12), today
    # month
    start_year = today.year - 1
    return date(start_year, today.month, 1), today


def _feedback_conditions(
    start_kst: datetime,
    end_exclusive_kst: datetime,
    q_like: str | None,
):
    """summary/series 공통 WHERE 조건 리스트."""
    conds = [
        QAFeedback.created_at >= start_kst,
        QAFeedback.created_at < end_exclusive_kst,
    ]
    if q_like:
        conds.append(
            or_(
                QALog.question_text.ilike(q_like),
                QALog.answer_text.ilike(q_like),
            )
        )
    return conds


async def get_feedback_summary(
    session: AsyncSession,
    start_kst: datetime,
    end_exclusive_kst: datetime,
    q_like: str | None = None,
) -> dict[str, int | float | None]:
    conds = _feedback_conditions(start_kst, end_exclusive_kst, q_like)
    rows = (await session.execute(
        select(QAFeedback.rating, func.count(QAFeedback.id))
        .join(QALog, QAFeedback.qa_log_id == QALog.id)
        .outerjoin(User, QALog.user_id == User.id)
        .where(*conds)
        .where(or_(QALog.user_id.is_(None), User.role != "admin"))
        .group_by(QAFeedback.rating)
    )).all()
    counts: dict[str, int] = {"good": 0, "bad": 0}
    for rating, n in rows:
        if rating in counts:
            counts[rating] = int(n)
    total = counts["good"] + counts["bad"]
    return {
        "good_count": counts["good"],
        "bad_count": counts["bad"],
        "good_ratio": round(counts["good"] / total, 3) if total else None,
    }


async def get_feedback_series(
    session: AsyncSession,
    unit: Literal["day", "week", "month"],
    start_kst: datetime,
    end_exclusive_kst: datetime,
    q_like: str | None = None,
) -> list[dict]:
    """unit별 KST 버킷 GOOD/BAD 카운트, 빈 버킷 0 채움."""
    conds = _feedback_conditions(start_kst, end_exclusive_kst, q_like)

    if unit == "day":
        trunc_expr = func.date(func.timezone("Asia/Seoul", QAFeedback.created_at))
    elif unit == "week":
        # DATE_TRUNC('week', ...) 월요일 기준 → 일요일 기준으로 보정
        trunc_expr = func.date(
            func.timezone("Asia/Seoul", func.date_trunc("week", QAFeedback.created_at))
        )
    else:
        trunc_expr = func.date(
            func.timezone("Asia/Seoul", func.date_trunc("month", QAFeedback.created_at))
        )

    rows = (await session.execute(
        select(
            trunc_expr.label("bucket"),
            QAFeedback.rating,
            func.count(QAFeedback.id).label("cnt"),
        )
        .join(QALog, QAFeedback.qa_log_id == QALog.id)
        .outerjoin(User, QALog.user_id == User.id)
        .where(*conds)
        .where(or_(QALog.user_id.is_(None), User.role != "admin"))
        .group_by("bucket", QAFeedback.rating)
        .order_by("bucket")
    )).all()

    raw: dict[date, dict[str, int]] = {}
    for bucket, rating, cnt in rows:
        if isinstance(bucket, datetime):
            bucket = bucket.date()
        if bucket not in raw:
            raw[bucket] = {"good": 0, "bad": 0}
        if rating in ("good", "bad"):
            raw[bucket][rating] = int(cnt)

    # 빈 버킷 채우기
    from_date = start_kst.date()
    to_date = (end_exclusive_kst - timedelta(seconds=1)).date()
    all_starts = _bucket_starts(from_date, to_date, unit if unit != "month" else "month")  # type: ignore[arg-type]
    result = []
    for bs in all_starts:
        counts = raw.get(bs, {"good": 0, "bad": 0})
        result.append({
            "bucket_start": bs.isoformat(),
            "good": counts["good"],
            "bad": counts["bad"],
        })
    return result


async def get_feedback_items_total(
    session: AsyncSession,
    start_kst: datetime,
    end_exclusive_kst: datetime,
    rating_filter: RatingFilter,
    q_like: str | None = None,
) -> int:
    conds = _feedback_conditions(start_kst, end_exclusive_kst, q_like)
    if rating_filter != "all":
        conds.append(QAFeedback.rating == rating_filter)
    total = (await session.execute(
        select(func.count(QAFeedback.id))
        .join(QALog, QAFeedback.qa_log_id == QALog.id)
        .outerjoin(User, QALog.user_id == User.id)
        .where(*conds)
        .where(or_(QALog.user_id.is_(None), User.role != "admin"))
    )).scalar_one()
    return int(total)


async def get_feedback_items(
    session: AsyncSession,
    start_kst: datetime,
    end_exclusive_kst: datetime,
    rating_filter: RatingFilter,
    page: int,
    per_page: int,
    q_like: str | None = None,
) -> list[dict]:
    conds = _feedback_conditions(start_kst, end_exclusive_kst, q_like)
    if rating_filter != "all":
        conds.append(QAFeedback.rating == rating_filter)

    rows = (await session.execute(
        select(
            QAFeedback.qa_log_id,
            QALog.question_text,
            QALog.answer_text,
            QAFeedback.rating,
            User.segment,
            QALog.user_id,
            User.email,
            QAFeedback.created_at,
        )
        .join(QALog, QAFeedback.qa_log_id == QALog.id)
        .outerjoin(User, QALog.user_id == User.id)
        .where(*conds)
        .where(or_(QALog.user_id.is_(None), User.role != "admin"))
        .order_by(QAFeedback.created_at.desc())
        .limit(per_page)
        .offset((page - 1) * per_page)
    )).all()

    result = []
    for (
        qa_log_id,
        question_text,
        answer_text,
        rating,
        segment,
        user_id,
        email,
        created_at,
    ) in rows:
        if created_at.tzinfo is None:
            from datetime import timezone
            created_at = created_at.replace(tzinfo=timezone.utc)
        kst_dt = created_at.astimezone(KST)
        result.append({
            "qa_log_id": qa_log_id,
            "question_text": question_text,
            "answer_text": answer_text,
            "rating": rating,
            "segment": segment,
            "user_id": user_id,
            "email": email,
            "created_at": kst_dt.isoformat(),
        })
    return result


async def get_feedback_export_rows(
    session: AsyncSession,
    start_kst: datetime,
    end_exclusive_kst: datetime,
    rating_filter: RatingFilter,
    q_like: str | None = None,
    max_rows: int = 10_000,
) -> tuple[list[dict], bool]:
    """엑셀 export용 전체 행. (rows, truncated) 반환."""
    conds = _feedback_conditions(start_kst, end_exclusive_kst, q_like)
    if rating_filter != "all":
        conds.append(QAFeedback.rating == rating_filter)

    rows = (await session.execute(
        select(
            QAFeedback.qa_log_id,
            QALog.question_text,
            QALog.answer_text,
            QAFeedback.rating,
            User.segment,
            QALog.user_id,
            User.email,
            QAFeedback.created_at,
        )
        .join(QALog, QAFeedback.qa_log_id == QALog.id)
        .outerjoin(User, QALog.user_id == User.id)
        .where(*conds)
        .where(or_(QALog.user_id.is_(None), User.role != "admin"))
        .order_by(QAFeedback.created_at.desc())
        .limit(max_rows + 1)
    )).all()

    truncated = len(rows) > max_rows
    rows = rows[:max_rows]

    result = []
    for (
        qa_log_id,
        question_text,
        answer_text,
        rating,
        segment,
        user_id,
        email,
        created_at,
    ) in rows:
        if created_at.tzinfo is None:
            from datetime import timezone
            created_at = created_at.replace(tzinfo=timezone.utc)
        kst_dt = created_at.astimezone(KST)
        result.append({
            "qa_log_id": qa_log_id,
            "question_text": question_text,
            "answer_text": answer_text,
            "rating": rating,
            "segment": segment,
            "user_id": user_id,
            "email": email,
            "created_at_kst": kst_dt.strftime("%Y-%m-%d %H:%M:%S"),
        })
    return result, truncated


# =============================================================================
# 질문 분석 — qa_logs 기반 일/주/월/년 집계 + 정렬·상세·엑셀
# =============================================================================

QuestionsSort = Literal["latest", "tokens", "email"]
QUESTIONS_EXPORT_LIMIT = 10_000


@dataclass(frozen=True)
class QuestionsBucket:
    bucket_start: date
    count: int


@dataclass(frozen=True)
class QuestionsSummary:
    buckets: list[QuestionsBucket]
    from_: date
    to: date
    total_count: int


async def get_questions_summary(
    session: AsyncSession,
    unit: Unit,
    from_: date | None,
    to: date | None,
) -> QuestionsSummary:
    """unit/from/to 기반 KST 버킷별 질문 수 + 전체 합계.

    qa_logs 한 행 = 질문 1건. admin 사용자 행은 제외.
    """
    if from_ is None and to is None:
        from_, to = _default_window(unit)
    elif from_ is None:
        from_, _ = _default_window(unit)
    elif to is None:
        _, to = _default_window(unit)

    bucket_starts = _bucket_starts(from_, to, unit)
    if not bucket_starts:
        return QuestionsSummary(buckets=[], from_=from_, to=to, total_count=0)

    day_expr = func.date(func.timezone("Asia/Seoul", QALog.created_at))
    range_start_kst = _kst_datetime(bucket_starts[0])
    range_end_exclusive_kst = _kst_datetime(_next_bucket(bucket_starts[-1], unit))

    stmt = (
        select(day_expr.label("d"), func.count(QALog.id).label("n"))
        .outerjoin(User, QALog.user_id == User.id)
        .where(
            QALog.created_at >= range_start_kst,
            QALog.created_at < range_end_exclusive_kst,
            or_(QALog.user_id.is_(None), User.role != "admin"),
        )
        .group_by(day_expr)
    )
    rows = (await session.execute(stmt)).all()

    by_day: dict[date, int] = {}
    for d_val, n in rows:
        if isinstance(d_val, datetime):
            d_val = d_val.date()
        by_day[d_val] = int(n)

    buckets: list[QuestionsBucket] = []
    total = 0
    for start in bucket_starts:
        nxt = _next_bucket(start, unit)
        count = sum(n for d, n in by_day.items() if start <= d < nxt)
        total += count
        buckets.append(QuestionsBucket(bucket_start=start, count=count))

    return QuestionsSummary(
        buckets=buckets, from_=from_, to=to, total_count=total
    )


def _questions_items_base(
    start_kst: datetime,
    end_exclusive_kst: datetime,
    q_like: str | None,
):
    """items/total/export 공통 select base (정렬·페이지 미적용)."""
    conds = [
        QALog.created_at >= start_kst,
        QALog.created_at < end_exclusive_kst,
        or_(QALog.user_id.is_(None), User.role != "admin"),
    ]
    if q_like:
        conds.append(
            or_(
                QALog.question_text.ilike(q_like),
                QALog.answer_text.ilike(q_like),
            )
        )
    return conds


async def get_questions_items_total(
    session: AsyncSession,
    start_kst: datetime,
    end_exclusive_kst: datetime,
    q_like: str | None = None,
) -> int:
    conds = _questions_items_base(start_kst, end_exclusive_kst, q_like)
    total = (await session.execute(
        select(func.count(QALog.id))
        .outerjoin(User, QALog.user_id == User.id)
        .where(*conds)
    )).scalar_one()
    return int(total)


def _questions_order_by(sort: QuestionsSort):
    """정렬 키 → SQLAlchemy ORDER BY 절."""
    if sort == "tokens":
        # NULL을 0으로 처리해서 합산 후 내림차순
        token_sum = (
            func.coalesce(QALog.input_tokens, 0)
            + func.coalesce(QALog.output_tokens, 0)
        )
        return [token_sum.desc(), QALog.created_at.desc()]
    if sort == "email":
        # NULL(비회원) 마지막으로 보내고, 그 다음 이메일 가나다, 같은 계정은 최신순
        return [
            func.coalesce(User.email, "~").asc(),
            QALog.created_at.desc(),
        ]
    # latest (default)
    return [QALog.created_at.desc()]


async def get_questions_items(
    session: AsyncSession,
    start_kst: datetime,
    end_exclusive_kst: datetime,
    sort: QuestionsSort,
    page: int,
    per_page: int,
    q_like: str | None = None,
) -> list[dict]:
    conds = _questions_items_base(start_kst, end_exclusive_kst, q_like)
    order = _questions_order_by(sort)

    rows = (await session.execute(
        select(
            QALog.id,
            QALog.question_text,
            QALog.answer_text,
            QALog.input_tokens,
            QALog.output_tokens,
            QALog.cost_usd,
            QALog.status,
            QALog.user_id,
            User.email,
            User.segment,
            QALog.created_at,
        )
        .outerjoin(User, QALog.user_id == User.id)
        .where(*conds)
        .order_by(*order)
        .limit(per_page)
        .offset((page - 1) * per_page)
    )).all()

    from datetime import timezone

    result: list[dict] = []
    for (
        qa_id,
        question_text,
        answer_text,
        input_tokens,
        output_tokens,
        cost_usd,
        status,
        user_id,
        email,
        segment,
        created_at,
    ) in rows:
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        in_t = int(input_tokens or 0)
        out_t = int(output_tokens or 0)
        result.append({
            "qa_log_id": int(qa_id),
            "question_text": question_text,
            "answer_text": answer_text,
            "input_tokens": in_t,
            "output_tokens": out_t,
            "total_tokens": in_t + out_t,
            "cost_usd": str(cost_usd) if cost_usd is not None else None,
            "status": status,
            "user_id": int(user_id) if user_id is not None else None,
            "email": email,
            "segment": segment,
            "created_at": created_at.astimezone(KST).isoformat(),
        })
    return result


async def get_questions_export_rows(
    session: AsyncSession,
    start_kst: datetime,
    end_exclusive_kst: datetime,
    sort: QuestionsSort,
    q_like: str | None = None,
    max_rows: int = QUESTIONS_EXPORT_LIMIT,
) -> tuple[list[dict], bool]:
    """엑셀 export용 전체 행. (rows, truncated) 반환."""
    conds = _questions_items_base(start_kst, end_exclusive_kst, q_like)
    order = _questions_order_by(sort)

    rows = (await session.execute(
        select(
            QALog.id,
            QALog.question_text,
            QALog.answer_text,
            QALog.input_tokens,
            QALog.output_tokens,
            QALog.cost_usd,
            QALog.status,
            QALog.user_id,
            User.email,
            User.segment,
            QALog.created_at,
        )
        .outerjoin(User, QALog.user_id == User.id)
        .where(*conds)
        .order_by(*order)
        .limit(max_rows + 1)
    )).all()

    truncated = len(rows) > max_rows
    rows = rows[:max_rows]

    from datetime import timezone

    result: list[dict] = []
    for (
        qa_id,
        question_text,
        answer_text,
        input_tokens,
        output_tokens,
        cost_usd,
        status,
        user_id,
        email,
        segment,
        created_at,
    ) in rows:
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        kst_dt = created_at.astimezone(KST)
        in_t = int(input_tokens or 0)
        out_t = int(output_tokens or 0)
        result.append({
            "qa_log_id": int(qa_id),
            "question_text": question_text,
            "answer_text": answer_text or "",
            "input_tokens": in_t,
            "output_tokens": out_t,
            "total_tokens": in_t + out_t,
            "cost_usd": str(cost_usd) if cost_usd is not None else "",
            "status": status or "",
            "user_id": int(user_id) if user_id is not None else "",
            "email": email or "",
            "segment": segment or "",
            "created_at_kst": kst_dt.strftime("%Y-%m-%d %H:%M:%S"),
        })
    return result, truncated


# =============================================================================
# Story 6.4 — 가입유형별 통계 + 연차 히스토그램
# =============================================================================

VALID_SEGMENTS_CANONICAL = ("doctor", "hygienist", "student_other")
SEGMENT_LABELS_KR = {
    "doctor": "치과의사",
    "hygienist": "치과위생사",
    "student_other": "학생/기타",
}
EXPERIENCE_BUCKET_ORDER = ("0-2", "3-5", "6-10", "11-20", "20+")
EXPORT_DETAIL_LIMIT = 5_000


def _bucket_years(years: int) -> str:
    if years <= 2:
        return "0-2"
    if years <= 5:
        return "3-5"
    if years <= 10:
        return "6-10"
    if years <= 20:
        return "11-20"
    return "20+"


def _mask_email(email: str) -> str:
    if "@" not in email:
        return email
    local, _, domain = email.partition("@")
    if len(local) <= 1:
        return email
    return f"{local[0]}**@{domain}"


@dataclass(frozen=True)
class SegmentRow:
    segment: str
    count: int
    active_count: int
    pro_count: int


@dataclass(frozen=True)
class ExperienceRow:
    segment: str
    years_bucket: str
    count: int


async def get_segment_stats(
    session: AsyncSession,
    *,
    include_withdrawn: bool = False,
    include_blocked: bool = False,
) -> dict[str, Any]:
    """가입유형별 카운트 + 연차 5버킷 히스토그램.

    by_segment: 3 segment 고정 순서 (NULL은 응답에서 제외, total에는 포함).
    by_experience: doctor/hygienist만, years 5 버킷.
    total: 필터 적용 후 모든 사용자(NULL segment 포함).
    """
    base_conds = [User.role != "admin"]
    if not include_withdrawn:
        base_conds.append(User.withdrawn_at.is_(None))
    if not include_blocked:
        base_conds.append(User.subscription_status != "blocked")

    stmt = select(
        User.segment,
        func.count().label("cnt"),
        func.count()
        .filter(
            and_(User.withdrawn_at.is_(None), User.subscription_status != "blocked")
        )
        .label("active_cnt"),
        func.count()
        .filter(
            and_(User.withdrawn_at.is_(None), User.subscription_status == "pro")
        )
        .label("pro_cnt"),
    ).group_by(User.segment)
    if base_conds:
        stmt = stmt.where(*base_conds)
    rows = (await session.execute(stmt)).all()

    by_seg_map: dict[str, SegmentRow] = {}
    total = 0
    for seg, cnt, active_cnt, pro_cnt in rows:
        total += int(cnt)
        if seg in VALID_SEGMENTS_CANONICAL:
            by_seg_map[seg] = SegmentRow(
                segment=seg,
                count=int(cnt),
                active_count=int(active_cnt),
                pro_count=int(pro_cnt),
            )

    by_segment = [
        by_seg_map.get(s, SegmentRow(segment=s, count=0, active_count=0, pro_count=0))
        for s in VALID_SEGMENTS_CANONICAL
    ]

    exp_conds = list(base_conds)
    exp_conds.append(User.segment.in_(("doctor", "hygienist")))
    exp_conds.append(User.years_of_experience.is_not(None))

    exp_stmt = (
        select(User.segment, User.years_of_experience, func.count())
        .where(*exp_conds)
        .group_by(User.segment, User.years_of_experience)
    )
    exp_rows = (await session.execute(exp_stmt)).all()

    bucket_map: dict[tuple[str, str], int] = {}
    for seg, years, cnt in exp_rows:
        bucket = _bucket_years(int(years))
        bucket_map[(seg, bucket)] = bucket_map.get((seg, bucket), 0) + int(cnt)

    by_experience = [
        ExperienceRow(segment=seg, years_bucket=b, count=bucket_map.get((seg, b), 0))
        for seg in ("doctor", "hygienist")
        for b in EXPERIENCE_BUCKET_ORDER
    ]

    return {
        "applied_filters": {
            "include_withdrawn": include_withdrawn,
            "include_blocked": include_blocked,
        },
        "total": total,
        "by_segment": by_segment,
        "by_experience": by_experience,
    }


async def get_segment_export_rows(
    session: AsyncSession,
    *,
    include_withdrawn: bool = False,
    include_blocked: bool = False,
    limit: int = EXPORT_DETAIL_LIMIT,
) -> tuple[list[dict], bool]:
    """Detail 시트용 user-row 직렬화 + truncated 플래그 (limit+1 fetch)."""
    conds = [User.role != "admin"]
    if not include_withdrawn:
        conds.append(User.withdrawn_at.is_(None))
    if not include_blocked:
        conds.append(User.subscription_status != "blocked")

    stmt = (
        select(User)
        .where(*conds)
        .order_by(
            User.segment.asc().nullslast(),
            User.years_of_experience.asc().nullslast(),
            User.created_at.desc(),
        )
        .limit(limit + 1)
    )
    users = (await session.execute(stmt)).scalars().all()
    truncated = len(users) > limit
    users = users[:limit]

    rows = [
        {
            "user_id": u.id,
            "email_masked": _mask_email(u.email),
            "segment": u.segment or "",
            "segment_label": SEGMENT_LABELS_KR.get(u.segment or "", ""),
            "years_of_experience": u.years_of_experience or "",
            "subscription_status": u.subscription_status,
            "created_at_kst": (
                u.created_at.astimezone(KST).isoformat(timespec="minutes")
                if u.created_at.tzinfo is not None
                else u.created_at.replace(tzinfo=KST).isoformat(timespec="minutes")
            ),
        }
        for u in users
    ]
    return rows, truncated


# =============================================================================
# Story 5.5 — 매출 + 토큰비용 차액 (A-106) + xlsx export (A-107)
# 9.1 finance_service / 5.4 analytics 패턴 그대로 차용. 신규 마이그레이션 0건.
# =============================================================================

YEAR_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
ALLOWED_SERIES_MONTHS = (3, 6, 12, 24)
EXPORT_DETAIL_LIMIT_REVENUE = 10_000  # 9.1 finance_service.EXPORT_DETAIL_LIMIT과 동일 값, 모듈 분리


def _kst_month_bounds_from_str(year_month: str) -> tuple[datetime, datetime]:
    """YYYY-MM → (kst_start, kst_end_exclusive). 422 가드는 라우터에서."""
    y_str, m_str = year_month.split("-")
    y, m = int(y_str), int(m_str)
    start = datetime(y, m, 1, tzinfo=KST)
    if m == 12:
        end_excl = datetime(y + 1, 1, 1, tzinfo=KST)
    else:
        end_excl = datetime(y, m + 1, 1, tzinfo=KST)
    return start, end_excl


async def get_revenue_variance_month(
    session: AsyncSession,
    *,
    redis_runtime: AsyncRedis,
    year_month: str,
) -> dict[str, Any]:
    """단월 매출·환불·순매출·토큰비용·차액·에러·이상 카운트.

    - revenue_krw / gross_revenue_krw: payment_events.event_type='charge_success' 가
      발생한 payments.amount_krw SUM (gross 기준, payment_id 단위 dedupe).
      revenue_krw 는 하위호환 alias.
    - refund_krw: 위 gross 대상 결제 중 payment.status='refunded' 인 결제의
      amount_krw SUM. 결제와 같은 달로 차감되어 "원 결제 월"의 순매출이 줄어든다.
    - net_revenue_krw: gross_revenue_krw − refund_krw.
    - token_cost_usd: qa_logs.cost_usd SUM (NULL 자동 제외)
    - token_cost_krw: round(token_cost_usd × usd_to_krw)
    - variance_krw: net_revenue_krw − token_cost_krw  (음수 가능)
    - error_count: payment_events.event_type='charge_failed' COUNT
    - anomaly_count: anomaly_events COUNT
    """
    start, end_excl = _kst_month_bounds_from_str(year_month)

    charge_success_payment_ids = (
        select(PaymentEvent.payment_id)
        .where(
            PaymentEvent.event_type == "charge_success",
            PaymentEvent.created_at >= start,
            PaymentEvent.created_at < end_excl,
        )
        .distinct()
        .scalar_subquery()
    )
    rev_stmt = select(
        func.coalesce(func.sum(Payment.amount_krw), 0).label("gross"),
        func.coalesce(
            func.sum(
                case((Payment.status == "refunded", Payment.amount_krw), else_=0)
            ),
            0,
        ).label("refund"),
    ).where(Payment.id.in_(charge_success_payment_ids))
    cost_stmt = (
        select(func.coalesce(func.sum(QALog.cost_usd), Decimal("0")))
        .outerjoin(User, User.id == QALog.user_id)
        .where(
            QALog.created_at >= start,
            QALog.created_at < end_excl,
            or_(QALog.user_id.is_(None), User.role != "admin"),
        )
    )
    err_stmt = select(func.count(PaymentEvent.id)).where(
        PaymentEvent.event_type == "charge_failed",
        PaymentEvent.created_at >= start,
        PaymentEvent.created_at < end_excl,
    )
    anomaly_stmt = (
        select(func.count(AnomalyEvent.id))
        .outerjoin(User, AnomalyEvent.target_user_id == User.id)
        .where(
            AnomalyEvent.created_at >= start,
            AnomalyEvent.created_at < end_excl,
            or_(AnomalyEvent.target_user_id.is_(None), User.role != "admin"),
        )
    )

    rev_row = (await session.execute(rev_stmt)).one()
    gross_revenue_krw = int(rev_row.gross or 0)
    refund_krw = int(rev_row.refund or 0)
    net_revenue_krw = gross_revenue_krw - refund_krw
    token_cost_usd_raw = (await session.execute(cost_stmt)).scalar_one()
    token_cost_usd: Decimal = (
        token_cost_usd_raw if isinstance(token_cost_usd_raw, Decimal) else Decimal(token_cost_usd_raw or 0)
    )
    error_count = int((await session.execute(err_stmt)).scalar_one() or 0)
    anomaly_count = int((await session.execute(anomaly_stmt)).scalar_one() or 0)

    usd_to_krw = await runtime_config_service.get_usd_to_krw(redis_runtime)
    token_cost_krw = int(
        (token_cost_usd * Decimal(usd_to_krw)).quantize(Decimal("1"))
    )
    variance_krw = net_revenue_krw - token_cost_krw

    return {
        "year_month": year_month,
        "revenue_krw": gross_revenue_krw,
        "gross_revenue_krw": gross_revenue_krw,
        "refund_krw": refund_krw,
        "net_revenue_krw": net_revenue_krw,
        "token_cost_usd": str(token_cost_usd.quantize(Decimal("0.000001"))),
        "token_cost_krw": token_cost_krw,
        "usd_to_krw": usd_to_krw,
        "variance_krw": variance_krw,
        "error_count": error_count,
        "anomaly_count": anomaly_count,
        "applied_filters": {
            "year_month": year_month,
            "kst_start": start.isoformat(),
            "kst_end_exclusive": end_excl.isoformat(),
        },
    }


def _shift_month(start: datetime, delta_months: int) -> datetime:
    """KST aware 월 1일 datetime을 delta_months 만큼 이동."""
    total = (start.year * 12 + (start.month - 1)) + delta_months
    new_year, new_month0 = divmod(total, 12)
    return datetime(new_year, new_month0 + 1, 1, tzinfo=KST)


async def get_revenue_variance_series(
    session: AsyncSession,
    *,
    redis_runtime: AsyncRedis,
    months: int,
    to_year_month: str,
) -> dict[str, Any]:
    """월별 매출·토큰비용·차액 시계열 (오름차순). 단일 SQL 2 쿼리 + 빈 월 0 채움."""
    to_start, _to_end_excl = _kst_month_bounds_from_str(to_year_month)
    from_start = _shift_month(to_start, -(months - 1))
    to_end_excl = _shift_month(to_start, 1)

    # payment_id별 첫 charge_success 이벤트만 집계해 중복 합산을 방지하고,
    # 환불되어 status='refunded' 가 된 결제도 그 달 매출에 포함되도록 한다.
    first_charge_success = (
        select(
            PaymentEvent.payment_id.label("pid"),
            func.min(PaymentEvent.created_at).label("first_at"),
        )
        .where(
            PaymentEvent.event_type == "charge_success",
            PaymentEvent.created_at >= from_start,
            PaymentEvent.created_at < to_end_excl,
        )
        .group_by(PaymentEvent.payment_id)
        .subquery()
    )
    rev_stmt = (
        select(
            func.date_trunc(
                "month", func.timezone("Asia/Seoul", first_charge_success.c.first_at)
            ).label("bucket"),
            func.coalesce(func.sum(Payment.amount_krw), 0).label("rev"),
            func.coalesce(
                func.sum(
                    case((Payment.status == "refunded", Payment.amount_krw), else_=0)
                ),
                0,
            ).label("refund"),
        )
        .join(Payment, Payment.id == first_charge_success.c.pid)
        .group_by("bucket")
    )
    cost_stmt = (
        select(
            func.date_trunc(
                "month", func.timezone("Asia/Seoul", QALog.created_at)
            ).label("bucket"),
            func.coalesce(func.sum(QALog.cost_usd), Decimal("0")).label("cost"),
        )
        .outerjoin(User, User.id == QALog.user_id)
        .where(
            QALog.created_at >= from_start,
            QALog.created_at < to_end_excl,
            or_(QALog.user_id.is_(None), User.role != "admin"),
        )
        .group_by("bucket")
    )

    rev_rows = (await session.execute(rev_stmt)).all()
    cost_rows = (await session.execute(cost_stmt)).all()

    usd_to_krw = await runtime_config_service.get_usd_to_krw(redis_runtime)

    def _to_ym(dt: Any) -> str:
        if dt is None:
            return ""
        return dt.strftime("%Y-%m")

    rev_map: dict[str, int] = {_to_ym(r.bucket): int(r.rev or 0) for r in rev_rows}
    refund_map: dict[str, int] = {_to_ym(r.bucket): int(r.refund or 0) for r in rev_rows}
    cost_map: dict[str, Decimal] = {
        _to_ym(r.bucket): (r.cost if isinstance(r.cost, Decimal) else Decimal(r.cost or 0))
        for r in cost_rows
    }

    items: list[dict[str, Any]] = []
    cur = from_start
    for _ in range(months):
        ym = cur.strftime("%Y-%m")
        gross_v = rev_map.get(ym, 0)
        refund_v = refund_map.get(ym, 0)
        net_v = gross_v - refund_v
        cost_v = cost_map.get(ym, Decimal("0"))
        cost_krw = int((cost_v * Decimal(usd_to_krw)).quantize(Decimal("1")))
        items.append(
            {
                "year_month": ym,
                "revenue_krw": gross_v,
                "gross_revenue_krw": gross_v,
                "refund_krw": refund_v,
                "net_revenue_krw": net_v,
                "token_cost_krw": cost_krw,
                "variance_krw": net_v - cost_krw,
            }
        )
        cur = _shift_month(cur, 1)

    return {
        "months": months,
        "to": to_year_month,
        "from": items[0]["year_month"] if items else to_year_month,
        "usd_to_krw": usd_to_krw,
        "items": items,
    }


async def get_revenue_variance_export_rows(
    session: AsyncSession,
    *,
    year_month: str,
    limit: int,
) -> tuple[list[dict[str, Any]], bool]:
    """Detail 시트용 결제 성공 row + truncated 플래그. 9.1 limit+1 fetch 패턴.

    summary 함수와 동일하게 payment_events.charge_success 발생 시점을 기준으로 매출에 포함된
    결제 row(환불되어 status='refunded' 인 row 포함)를 모두 내려준다. payment_id 단위 dedupe.
    """
    start, end_excl = _kst_month_bounds_from_str(year_month)

    first_charge_success = (
        select(
            PaymentEvent.payment_id.label("pid"),
            func.min(PaymentEvent.created_at).label("first_at"),
        )
        .where(
            PaymentEvent.event_type == "charge_success",
            PaymentEvent.created_at >= start,
            PaymentEvent.created_at < end_excl,
        )
        .group_by(PaymentEvent.payment_id)
        .subquery()
    )

    stmt = (
        select(
            Payment.id.label("payment_id"),
            Payment.charged_at,
            Payment.amount_krw,
            Payment.user_id,
            Payment.provider_order_id,
            Payment.subscription_id,
            Payment.status,
            User.email,
        )
        .join(User, User.id == Payment.user_id)
        .join(first_charge_success, first_charge_success.c.pid == Payment.id)
        .order_by(Payment.charged_at.desc(), Payment.id.desc())
        .limit(limit + 1)
    )
    raw = (await session.execute(stmt)).all()
    truncated = len(raw) > limit
    if truncated:
        raw = raw[:limit]

    rows: list[dict[str, Any]] = []
    for r in raw:
        if r.charged_at is not None:
            charged_kst = r.charged_at.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S")
        else:
            charged_kst = ""
        rows.append(
            {
                "payment_id": r.payment_id,
                "charged_at_kst": charged_kst,
                "amount_krw": r.amount_krw,
                "user_id": r.user_id,
                "email_masked": _mask_email(r.email),
                "provider_order_id": r.provider_order_id,
                "subscription_id": r.subscription_id if r.subscription_id is not None else "",
                "status": r.status,
                "is_refunded": "예" if r.status == "refunded" else "아니오",
            }
        )
    return rows, truncated
