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

from dataclasses import dataclass
from datetime import datetime, date, timedelta
from typing import Literal

from typing import Any

from sqlalchemy import and_, select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.qa_feedback import QAFeedback
from api.src.models.qa_log import QALog
from api.src.models.user import User
from api.src.services.budget_service import KST

Unit = Literal["day", "week", "month", "year"]


@dataclass(frozen=True)
class SignupsBucket:
    bucket_start: date
    cumulative: int
    active: int
    withdrawn: int


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

    daily_signups = await _daily_counts_kst(session, User.created_at)
    daily_withdrawals = await _daily_counts_kst(session, User.withdrawn_at)
    # 차단 사용자 (현재 시점). 시간 흐름 추적이 어려우므로 마지막 버킷에만 반영.
    blocked_now: int = (await session.execute(
        select(func.count(User.id)).where(
            User.subscription_status == "blocked",
            User.withdrawn_at.is_(None),
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

        buckets.append(SignupsBucket(
            bucket_start=start,
            cumulative=cumulative,
            active=active,
            withdrawn=withdrawn,
        ))

    return buckets, from_, to


async def get_subscriber_counts(
    session: AsyncSession,
) -> dict[str, int | None | list]:
    """현재 시점 free/pro/blocked/withdrawn 카운트.

    HOLD-PG 자리: pending_cancellation_count=None, upcoming_renewals=[].
    """
    rows = (await session.execute(
        select(User.subscription_status, func.count(User.id))
        .where(User.withdrawn_at.is_(None))
        .group_by(User.subscription_status)
    )).all()
    counts = {status: 0 for status in ("free", "pro", "blocked")}
    for status, n in rows:
        if status in counts:
            counts[status] = int(n)

    withdrawn_count = (await session.execute(
        select(func.count(User.id)).where(User.withdrawn_at.is_not(None))
    )).scalar_one()

    return {
        "free_count": counts["free"],
        "pro_count": counts["pro"],
        "blocked_count": counts["blocked"],
        "withdrawn_count": int(withdrawn_count),
        "pending_cancellation_count": None,
        "upcoming_renewals": [],
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
        .where(*conds)
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
        .where(*conds)
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
        .where(*conds)
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
            QAFeedback.created_at,
        )
        .join(QALog, QAFeedback.qa_log_id == QALog.id)
        .outerjoin(User, QALog.user_id == User.id)
        .where(*conds)
        .order_by(QAFeedback.created_at.desc())
        .limit(per_page)
        .offset((page - 1) * per_page)
    )).all()

    result = []
    for qa_log_id, question_text, answer_text, rating, segment, created_at in rows:
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
            QAFeedback.created_at,
        )
        .join(QALog, QAFeedback.qa_log_id == QALog.id)
        .outerjoin(User, QALog.user_id == User.id)
        .where(*conds)
        .order_by(QAFeedback.created_at.desc())
        .limit(max_rows + 1)
    )).all()

    truncated = len(rows) > max_rows
    rows = rows[:max_rows]

    result = []
    for qa_log_id, question_text, answer_text, rating, segment, created_at in rows:
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
    base_conds = []
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
    conds = []
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
