"""QAReviewService — #113 질의응답 검토 도메인 로직.

운영진이 사용자 질의응답(질문+답변)을 검토해 굿/베드 + 코멘트를 남기고,
최고관리자가 검토완료 처리한다. 기존 qa_feedback(고객 피드백)과 완전히 분리된 별도 개념.

집계 규칙(analytics_service.get_feedback_summary 복제):
- category = reviewed_at IS NOT NULL 이면 'reviewed', 그 외 rating.
- good_ratio = round(good / (good + bad), 3), 분모는 '미검토 GOOD/BAD' 한정. 없으면 None.

모든 시간 버킷은 KST(Asia/Seoul) 기준 자정.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import HTTPException
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.qa_log import QALog
from api.src.models.qa_review import QAReview
from api.src.models.qa_review_settings import QAReviewSettings
from api.src.models.user import User
from api.src.services.budget_service import KST

Period = Literal["today", "3d", "7d", "month", "custom"]
RatingFilter = Literal["all", "good", "bad", "unrated"]
ReviewFilter = Literal["all", "reviewed", "unreviewed"]
Bucket = Literal["day", "week", "month"]

ALLOWED_LOOKBACK_PRESETS = (1, 3, 7, 30)
EXPORT_LIMIT = 10_000


# =============================================================================
# 기간 계산 helpers
# =============================================================================


def _kst_dt(d: date) -> datetime:
    """date → KST 자정 datetime."""
    return datetime(d.year, d.month, d.day, tzinfo=KST)


def _resolve_period(
    period: Period,
    date_from: date | None,
    date_to: date | None,
) -> tuple[date, date]:
    """period → (from_date, to_date) KST 기준 날짜(포함 구간)."""
    today = datetime.now(KST).date()
    if period == "today":
        return today, today
    if period == "3d":
        return today - timedelta(days=3), today
    if period == "7d":
        return today - timedelta(days=7), today
    if period == "month":
        return today - timedelta(days=30), today
    # custom
    f = date_from or (today - timedelta(days=7))
    t = date_to or today
    if f > t:
        f = t
    return f, t


def _clamp_for_sub_operator(
    from_date: date,
    *,
    viewer_grade: str | None,
    max_lookback_days: int,
) -> tuple[date, bool]:
    """sub_operator 는 (오늘 - max_lookback_days) 이전을 조회할 수 없다. 클램프 여부 반환."""
    if viewer_grade != "sub_operator":
        return from_date, False
    today = datetime.now(KST).date()
    min_date = today - timedelta(days=max_lookback_days)
    if from_date < min_date:
        return min_date, True
    return from_date, False


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _to_kst_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(KST).isoformat()


def _category_expr():
    """qa_reviews row → 화면 카테고리 (reviewed 우선). LEFT JOIN NULL 은 'unrated'."""
    return case(
        (QAReview.reviewed_at.is_not(None), "reviewed"),
        (QAReview.rating == "good", "good"),
        (QAReview.rating == "bad", "bad"),
        else_="unrated",
    )


# =============================================================================
# 목록
# =============================================================================


async def list_reviews(
    session: AsyncSession,
    *,
    viewer_grade: str | None,
    period: Period,
    date_from: date | None,
    date_to: date | None,
    rating_filter: RatingFilter,
    review_filter: ReviewFilter,
    q: str | None,
    page: int,
    page_size: int,
    max_lookback_days: int,
) -> dict[str, Any]:
    """qa_logs LEFT JOIN qa_reviews(hidden_at IS NULL) 목록 + total + effective 기간."""
    from_date, to_date = _resolve_period(period, date_from, date_to)
    from_date, clamped = _clamp_for_sub_operator(
        from_date, viewer_grade=viewer_grade, max_lookback_days=max_lookback_days
    )
    start_kst = _kst_dt(from_date)
    end_exclusive_kst = _kst_dt(to_date) + timedelta(days=1)

    reviewer = aliased(User)  # reviewed_by 이름 조회용
    rater = aliased(User)  # 평가 메모 작성자(rated_by) 이름 조회용

    conds = [
        QALog.created_at >= start_kst,
        QALog.created_at < end_exclusive_kst,
        or_(QALog.user_id.is_(None), User.role != "admin"),
        # 숨김 처리된 review 는 목록에서 제외 (review 미존재 행은 포함)
        or_(QAReview.id.is_(None), QAReview.hidden_at.is_(None)),
    ]

    if rating_filter == "good":
        conds.append(QAReview.rating == "good")
    elif rating_filter == "bad":
        conds.append(QAReview.rating == "bad")
    elif rating_filter == "unrated":
        conds.append(QAReview.rating.is_(None))

    if review_filter == "reviewed":
        conds.append(QAReview.reviewed_at.is_not(None))
    elif review_filter == "unreviewed":
        conds.append(QAReview.reviewed_at.is_(None))

    if q:
        q_like = f"%{q}%"
        conds.append(
            or_(
                QALog.question_text.ilike(q_like),
                QALog.answer_text.ilike(q_like),
            )
        )

    base_join = (
        select(QALog.id)
        .select_from(QALog)
        .outerjoin(QAReview, QAReview.qa_log_id == QALog.id)
        .outerjoin(User, QALog.user_id == User.id)
        .where(*conds)
    )
    total = (
        await session.execute(select(func.count()).select_from(base_join.subquery()))
    ).scalar_one()

    rows = (
        await session.execute(
            select(
                QALog.id,
                QALog.question_text,
                QALog.answer_text,
                QALog.created_at,
                QALog.user_id,
                User.email,
                User.segment,
                QAReview.rating,
                QAReview.comment,
                QAReview.change_count,
                QAReview.reviewed_at,
                reviewer.email.label("reviewer_email"),
                rater.email.label("rater_email"),
            )
            .select_from(QALog)
            .outerjoin(QAReview, QAReview.qa_log_id == QALog.id)
            .outerjoin(User, QALog.user_id == User.id)
            .outerjoin(reviewer, QAReview.reviewed_by_user_id == reviewer.id)
            .outerjoin(rater, QAReview.rated_by_admin_id == rater.id)
            .where(*conds)
            .order_by(QALog.created_at.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
    ).all()

    items: list[dict[str, Any]] = []
    for r in rows:
        item: dict[str, Any] = {
            "qa_log_id": int(r.id),
            "question": r.question_text,
            "answer": r.answer_text,
            "created_at": _to_kst_iso(r.created_at),
            "review": {
                "rating": r.rating,
                "comment": r.comment,
                "change_count": int(r.change_count) if r.change_count is not None else 0,
                "reviewed_at": _to_kst_iso(r.reviewed_at),
                "reviewed_by_name": r.reviewer_email,
                "rated_by_name": r.rater_email,
            },
            "user": {
                "user_id": int(r.user_id) if r.user_id is not None else None,
                "email": r.email,
                "segment": r.segment,
            },
        }
        items.append(item)

    return {
        "items": items,
        "total": int(total),
        "effective_period": {
            "date_from": from_date.isoformat(),
            "date_to": to_date.isoformat(),
            "clamped": clamped,
            "max_lookback_days": max_lookback_days,
        },
    }


# =============================================================================
# 통계 (good_ratio + 시계열)
# =============================================================================


def _summary_conditions(start_kst: datetime, end_exclusive_kst: datetime) -> list:
    return [
        QALog.created_at >= start_kst,
        QALog.created_at < end_exclusive_kst,
        or_(QALog.user_id.is_(None), User.role != "admin"),
        # rating 이 있거나 검토완료된 행만 집계 대상(미평가·미검토는 제외)
        or_(QAReview.rating.is_not(None), QAReview.reviewed_at.is_not(None)),
        QAReview.hidden_at.is_(None),
    ]


async def get_review_summary(
    session: AsyncSession,
    *,
    period: Period,
    date_from: date | None,
    date_to: date | None,
    bucket: Bucket,
) -> dict[str, Any]:
    """good_ratio(analytics 복제) + day/week/month 버킷 시계열."""
    from_date, to_date = _resolve_period(period, date_from, date_to)
    start_kst = _kst_dt(from_date)
    end_exclusive_kst = _kst_dt(to_date) + timedelta(days=1)

    conds = _summary_conditions(start_kst, end_exclusive_kst)
    category = _category_expr()

    # ---- summary ----
    rows = (
        await session.execute(
            select(category.label("category"), func.count(QAReview.id))
            .select_from(QAReview)
            .join(QALog, QAReview.qa_log_id == QALog.id)
            .outerjoin(User, QALog.user_id == User.id)
            .where(*conds)
            .group_by(category)
        )
    ).all()
    counts = {"good": 0, "bad": 0, "reviewed": 0}
    for cat, n in rows:
        if cat in counts:
            counts[cat] = int(n)
    pending_total = counts["good"] + counts["bad"]
    summary = {
        "good_count": counts["good"],
        "bad_count": counts["bad"],
        "reviewed_count": counts["reviewed"],
        "good_ratio": round(counts["good"] / pending_total, 3) if pending_total else None,
    }

    # ---- series ----
    if bucket == "day":
        trunc_expr = func.date(func.timezone("Asia/Seoul", QALog.created_at))
        unit_step = "day"
    elif bucket == "week":
        trunc_expr = func.date(
            func.timezone("Asia/Seoul", func.date_trunc("week", QALog.created_at))
        )
        unit_step = "week"
    else:
        trunc_expr = func.date(
            func.timezone("Asia/Seoul", func.date_trunc("month", QALog.created_at))
        )
        unit_step = "month"

    series_rows = (
        await session.execute(
            select(
                trunc_expr.label("bucket"),
                category.label("category"),
                func.count(QAReview.id).label("cnt"),
            )
            .select_from(QAReview)
            .join(QALog, QAReview.qa_log_id == QALog.id)
            .outerjoin(User, QALog.user_id == User.id)
            .where(*conds)
            .group_by("bucket", "category")
            .order_by("bucket")
        )
    ).all()

    raw: dict[date, dict[str, int]] = {}
    for b, cat, cnt in series_rows:
        if isinstance(b, datetime):
            b = b.date()
        raw.setdefault(b, {"good": 0, "bad": 0, "reviewed": 0})
        if cat in ("good", "bad", "reviewed"):
            raw[b][cat] = int(cnt)

    series = []
    for bs in _bucket_starts(from_date, to_date, unit_step):
        c = raw.get(bs, {"good": 0, "bad": 0, "reviewed": 0})
        denom = c["good"] + c["bad"]
        series.append(
            {
                "bucket": bs.isoformat(),
                "good": c["good"],
                "bad": c["bad"],
                "good_ratio": round(c["good"] / denom, 3) if denom else None,
            }
        )

    return {"summary": summary, "series": series}


def _truncate_to_unit(d: date, unit: str) -> date:
    if unit == "day":
        return d
    if unit == "week":
        # 일요일 시작 (analytics 와 동일 규칙)
        return d - timedelta(days=d.isoweekday() % 7)
    return date(d.year, d.month, 1)


def _next_bucket(start: date, unit: str) -> date:
    if unit == "day":
        return start + timedelta(days=1)
    if unit == "week":
        return start + timedelta(weeks=1)
    if start.month == 12:
        return date(start.year + 1, 1, 1)
    return date(start.year, start.month + 1, 1)


def _bucket_starts(from_: date, to: date, unit: str) -> list[date]:
    cur = _truncate_to_unit(from_, unit)
    end_anchor = _truncate_to_unit(to, unit)
    out: list[date] = []
    while cur <= end_anchor:
        out.append(cur)
        cur = _next_bucket(cur, unit)
    return out


# =============================================================================
# 평가 / 코멘트 / 검토완료 / 다중삭제
# =============================================================================


def _serialize_review(review: QAReview | None) -> dict[str, Any]:
    if review is None:
        return {
            "rating": None,
            "comment": None,
            "change_count": 0,
            "reviewed_at": None,
        }
    return {
        "rating": review.rating,
        "comment": review.comment,
        "change_count": int(review.change_count),
        "reviewed_at": _to_kst_iso(review.reviewed_at),
    }


async def _get_review(session: AsyncSession, qa_log_id: int) -> QAReview | None:
    return (
        await session.execute(
            select(QAReview).where(QAReview.qa_log_id == qa_log_id)
        )
    ).scalar_one_or_none()


async def _ensure_qa_log(session: AsyncSession, qa_log_id: int) -> None:
    exists = (
        await session.execute(select(QALog.id).where(QALog.id == qa_log_id))
    ).scalar_one_or_none()
    if exists is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "QA_REVIEW_QA_LOG_NOT_FOUND",
                "message": "질의 기록을 찾을 수 없습니다.",
            },
        )


async def upsert_rating(
    session: AsyncSession,
    *,
    qa_log_id: int,
    rating: str | None,
    comment: str | None,
    admin_id: int,
) -> dict[str, Any]:
    """평가 설정 — SET 시맨틱(#113 모달 개편).

    모달에서 굿/배드 선택 + 평가 메모를 한 번에 저장한다. 과거의 '토글' 방식(같은
    값 재클릭 시 해제)은 폐기하고, 넘어온 값 그대로 덮어쓴다.

    - rating='good'|'bad' → 해당 값으로 설정. comment(평가 메모)를 그대로 저장(굿/베드 공통).
    - rating=None → 평가 해제(rating/comment 모두 NULL). 모달에서 선택을 해제한 경우.
    - 모든 변경에 change_count += 1.
    """
    await _ensure_qa_log(session, qa_log_id)
    now = _now_utc()
    review = await _get_review(session, qa_log_id)

    # 빈 문자열 메모는 '메모 없음'으로 정규화.
    normalized_comment = comment if (comment and comment.strip()) else None

    if review is None:
        review = QAReview(
            qa_log_id=qa_log_id,
            rating=rating,
            comment=normalized_comment if rating is not None else None,
            rated_by_admin_id=admin_id,
            change_count=1,
            created_at=now,
            updated_at=now,
        )
        session.add(review)
    else:
        if rating is None:
            review.rating = None
            review.comment = None
        else:
            review.rating = rating
            review.comment = normalized_comment
        review.change_count = int(review.change_count) + 1
        review.rated_by_admin_id = admin_id
        review.updated_at = now

    await session.flush()
    return _serialize_review(review)


async def update_comment(
    session: AsyncSession,
    *,
    qa_log_id: int,
    comment: str,
    admin_id: int,
) -> dict[str, Any]:
    """평가 메모 수정. 굿/베드 평가가 선택된 항목이면 허용. 미평가면 422.

    #113 모달 개편: 과거엔 '베드' 에만 허용했으나, 굿/베드 모두 메모를 남길 수 있게 완화.
    """
    review = await _get_review(session, qa_log_id)
    if review is None or review.rating is None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "QA_REVIEW_COMMENT_NOT_ALLOWED",
                "message": "먼저 굿 또는 베드로 평가한 뒤 메모를 남길 수 있습니다.",
            },
        )
    review.comment = comment
    review.rated_by_admin_id = admin_id
    review.updated_at = _now_utc()
    await session.flush()
    return _serialize_review(review)


async def set_reviewed(
    session: AsyncSession,
    *,
    qa_log_id: int,
    reviewed: bool,
    admin_id: int,
) -> dict[str, Any]:
    """검토완료/미검토 토글. 행이 없으면 생성 후 설정."""
    await _ensure_qa_log(session, qa_log_id)
    now = _now_utc()
    review = await _get_review(session, qa_log_id)
    if review is None:
        review = QAReview(
            qa_log_id=qa_log_id,
            reviewed_at=now if reviewed else None,
            reviewed_by_user_id=admin_id if reviewed else None,
            created_at=now,
            updated_at=now,
        )
        session.add(review)
    else:
        review.reviewed_at = now if reviewed else None
        review.reviewed_by_user_id = admin_id if reviewed else None
        review.updated_at = now
    await session.flush()
    result = _serialize_review(review)
    result["reviewed"] = reviewed
    return result


async def bulk_hide(
    session: AsyncSession,
    *,
    qa_log_ids: list[int],
    admin_id: int,
) -> int:
    """각 qa_log_id 를 목록에서 소프트 숨김(hidden_at=now). 처리한 행 수 반환."""
    if not qa_log_ids:
        return 0
    now = _now_utc()
    # 실제 존재하는 qa_log 만 대상으로.
    valid_ids = set(
        (
            await session.execute(
                select(QALog.id).where(QALog.id.in_(qa_log_ids))
            )
        ).scalars().all()
    )
    existing = {
        r.qa_log_id: r
        for r in (
            await session.execute(
                select(QAReview).where(QAReview.qa_log_id.in_(valid_ids))
            )
        ).scalars().all()
    }
    processed = 0
    for qid in valid_ids:
        review = existing.get(qid)
        if review is None:
            session.add(
                QAReview(
                    qa_log_id=qid,
                    hidden_at=now,
                    rated_by_admin_id=admin_id,
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            review.hidden_at = now
            review.updated_at = now
        processed += 1
    await session.flush()
    return processed


# =============================================================================
# Export
# =============================================================================


async def get_export_rows(
    session: AsyncSession,
    *,
    period: Period,
    date_from: date | None,
    date_to: date | None,
    max_rows: int = EXPORT_LIMIT,
) -> tuple[list[dict[str, Any]], bool]:
    """xlsx export용 행. (rows, truncated) 반환. hidden_at IS NULL 만."""
    from_date, to_date = _resolve_period(period, date_from, date_to)
    start_kst = _kst_dt(from_date)
    end_exclusive_kst = _kst_dt(to_date) + timedelta(days=1)

    rater = aliased(User)
    reviewer = aliased(User)

    rows = (
        await session.execute(
            select(
                QALog.created_at,
                QALog.question_text,
                QALog.answer_text,
                QAReview.rating,
                QAReview.comment,
                rater.email.label("rater_email"),
                QAReview.reviewed_at,
                reviewer.email.label("reviewer_email"),
            )
            .select_from(QALog)
            .outerjoin(QAReview, QAReview.qa_log_id == QALog.id)
            .outerjoin(User, QALog.user_id == User.id)
            .outerjoin(rater, QAReview.rated_by_admin_id == rater.id)
            .outerjoin(reviewer, QAReview.reviewed_by_user_id == reviewer.id)
            .where(
                QALog.created_at >= start_kst,
                QALog.created_at < end_exclusive_kst,
                or_(QALog.user_id.is_(None), User.role != "admin"),
                or_(QAReview.id.is_(None), QAReview.hidden_at.is_(None)),
            )
            .order_by(QALog.created_at.desc())
            .limit(max_rows + 1)
        )
    ).all()

    truncated = len(rows) > max_rows
    rows = rows[:max_rows]

    result: list[dict[str, Any]] = []
    for r in rows:
        created_kst = ""
        if r.created_at is not None:
            dt = r.created_at
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            created_kst = dt.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S")
        rating_label = {"good": "굿", "bad": "베드"}.get(r.rating or "", "")
        reviewed_label = "검토완료" if r.reviewed_at is not None else "미검토"
        result.append(
            {
                "created_at_kst": created_kst,
                "question": r.question_text or "",
                "answer": r.answer_text or "",
                "rating_label": rating_label,
                "comment": r.comment or "",
                "rater": r.rater_email or "",
                "reviewed_label": reviewed_label,
                "reviewer": r.reviewer_email or "",
            }
        )
    return result, truncated


# =============================================================================
# 설정 (단일행)
# =============================================================================


async def get_settings(session: AsyncSession) -> dict[str, int]:
    """단일행 설정 조회. 행이 없으면 생성(기본 7)."""
    row = (
        await session.execute(
            select(QAReviewSettings).where(QAReviewSettings.id == 1)
        )
    ).scalar_one_or_none()
    if row is None:
        row = QAReviewSettings(id=1, sub_operator_max_lookback_days=7)
        session.add(row)
        await session.flush()
    return {"sub_operator_max_lookback_days": int(row.sub_operator_max_lookback_days)}


async def update_settings(
    session: AsyncSession,
    *,
    days: int,
    admin_id: int,
) -> dict[str, int]:
    """부관리자 조회 최대 과거 일수 변경."""
    row = (
        await session.execute(
            select(QAReviewSettings).where(QAReviewSettings.id == 1)
        )
    ).scalar_one_or_none()
    if row is None:
        row = QAReviewSettings(id=1, sub_operator_max_lookback_days=days)
        session.add(row)
    else:
        row.sub_operator_max_lookback_days = days
    row.updated_by_admin_id = admin_id
    row.updated_at = _now_utc()
    await session.flush()
    return {"sub_operator_max_lookback_days": int(row.sub_operator_max_lookback_days)}
