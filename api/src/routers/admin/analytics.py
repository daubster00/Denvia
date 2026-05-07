"""Story 5.2 / 5.3 / 5.4 — 사용자별 토큰·비용 분석 + 가입자/구독 분포 + 피드백 분석 API."""

import io
from datetime import datetime, timedelta, date
from decimal import Decimal
from typing import Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from redis.asyncio import Redis as AsyncRedis

from api.src.deps.auth import require_admin
from api.src.deps.redis import get_redis_runtime
from api.src.models.base import get_session
from api.src.models.qa_log import QALog
from api.src.models.user import User
from api.src.services.analytics_service import (
    ALLOWED_SERIES_MONTHS,
    EXPORT_DETAIL_LIMIT,
    EXPORT_DETAIL_LIMIT_REVENUE,
    SEGMENT_LABELS_KR,
    Unit,
    YEAR_MONTH_RE,
    _feedback_default_window,
    _kst_datetime,
    get_feedback_export_rows,
    get_feedback_items,
    get_feedback_items_total,
    get_feedback_series,
    get_feedback_summary,
    get_revenue_variance_export_rows,
    get_revenue_variance_month,
    get_revenue_variance_series,
    get_segment_export_rows,
    get_segment_stats,
    get_signups_buckets,
    get_subscriber_counts,
)
from api.src.services.budget_service import KST, kst_month_bounds
from api.src.services.finance_service import _excel_safe_cell

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin/analytics", tags=["admin-analytics"])


class UserTokensRow(BaseModel):
    user_id: int
    email: str
    segment: str | None
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: Decimal
    question_count: int
    avg_cost_per_question: Decimal


class UserTokensListResponse(BaseModel):
    items: list[UserTokensRow]
    page: int
    per_page: int
    total: int
    range: str
    year_month: str | None


@router.get("/user-tokens", response_model=UserTokensListResponse)
async def user_tokens(
    range: Literal["day", "month", "year"] = Query("month"),
    year_month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    from_: date | None = Query(None, alias="from"),
    to: date | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> UserTokensListResponse:
    start, end, ym = _resolve_window(range, year_month, from_, to)

    base = (
        select(
            QALog.user_id,
            func.coalesce(func.sum(QALog.input_tokens), 0).label("in_t"),
            func.coalesce(func.sum(QALog.output_tokens), 0).label("out_t"),
            func.coalesce(func.sum(QALog.cost_usd), Decimal("0")).label("cost"),
            func.count(QALog.id).label("q_cnt"),
        )
        .where(
            QALog.created_at >= start,
            QALog.created_at < end,
            QALog.user_id.is_not(None),
        )
        .group_by(QALog.user_id)
    )

    total = (await db.execute(
        select(func.count()).select_from(base.subquery())
    )).scalar_one()

    rows = (await db.execute(
        base.order_by(func.coalesce(func.sum(QALog.cost_usd), 0).desc())
        .offset((page - 1) * per_page).limit(per_page)
    )).all()

    user_ids = [r.user_id for r in rows]
    users_by_id: dict[int, User] = {}
    if user_ids:
        users = (await db.execute(
            select(User).where(User.id.in_(user_ids))
        )).scalars().all()
        users_by_id = {u.id: u for u in users}

    items: list[UserTokensRow] = []
    for r in rows:
        u = users_by_id.get(r.user_id)
        email = u.email if u else f"user#{r.user_id}"
        if u and getattr(u, "withdrawn_at", None) is not None:
            email = f"{email} (탈퇴)"
        avg = (Decimal(str(r.cost)) / r.q_cnt) if r.q_cnt > 0 else Decimal("0")
        items.append(UserTokensRow(
            user_id=r.user_id,
            email=email,
            segment=(u.segment if u else None),
            total_input_tokens=int(r.in_t),
            total_output_tokens=int(r.out_t),
            total_cost_usd=Decimal(str(r.cost)),
            question_count=int(r.q_cnt),
            avg_cost_per_question=avg,
        ))

    logger.info(
        "admin.dashboard.token_breakdown.viewed",
        actor_user_id=actor.id,
        range=range,
        year_month=ym,
        page=page,
    )

    return UserTokensListResponse(
        items=items,
        page=page,
        per_page=per_page,
        total=total,
        range=range,
        year_month=(ym if range == "month" else None),
    )


# ---------------------------------------------------------------------------
# Story 5.3: 가입자 추세 / 구독 분포
# ---------------------------------------------------------------------------


class SignupsBucketResponse(BaseModel):
    bucket_start: str  # YYYY-MM-DD (KST)
    cumulative: int
    active: int
    withdrawn: int


class SignupsResponse(BaseModel):
    unit: Unit
    from_: str = Field(alias="from")
    to: str
    buckets: list[SignupsBucketResponse]

    model_config = {"populate_by_name": True}


class UpcomingRenewal(BaseModel):
    """HOLD-PG 자리 — 본 스토리에서는 응답에 등장하지 않음."""

    user_id: int
    email_masked: str
    next_charge_at: datetime
    amount_krw: int


class SubscribersResponse(BaseModel):
    as_of: str  # ISO-8601 KST
    free_count: int
    pro_count: int
    blocked_count: int
    withdrawn_count: int
    pending_cancellation_count: int | None  # HOLD-PG: 항상 None
    upcoming_renewals: list[UpcomingRenewal]  # HOLD-PG: 항상 []


@router.get("/signups", response_model=SignupsResponse, response_model_by_alias=True)
async def signups(
    response: Response,
    unit: Unit = Query("month"),
    from_: date | None = Query(None, alias="from"),
    to: date | None = Query(None),
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> SignupsResponse:
    buckets, resolved_from, resolved_to = await get_signups_buckets(db, unit, from_, to)
    response.headers["Cache-Control"] = "no-store"
    logger.info(
        "admin.analytics.signups.viewed",
        actor_user_id=actor.id,
        unit=unit,
        from_=resolved_from.isoformat(),
        to=resolved_to.isoformat(),
        bucket_count=len(buckets),
    )
    return SignupsResponse(
        unit=unit,
        from_=resolved_from.isoformat(),
        to=resolved_to.isoformat(),
        buckets=[
            SignupsBucketResponse(
                bucket_start=b.bucket_start.isoformat(),
                cumulative=b.cumulative,
                active=b.active,
                withdrawn=b.withdrawn,
            )
            for b in buckets
        ],
    )


@router.get("/subscribers", response_model=SubscribersResponse)
async def subscribers(
    response: Response,
    as_of: Literal["now"] = Query("now"),  # 미래 확장 자리
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> SubscribersResponse:
    counts = await get_subscriber_counts(db)
    now_kst = datetime.now(KST).isoformat()
    response.headers["Cache-Control"] = "no-store"
    logger.info(
        "admin.analytics.subscribers.viewed",
        actor_user_id=actor.id,
        free=counts["free_count"],
        pro=counts["pro_count"],
        blocked=counts["blocked_count"],
        withdrawn=counts["withdrawn_count"],
    )
    return SubscribersResponse(as_of=now_kst, **counts)


# =============================================================================
# Story 5.4 — 피드백 분석
# =============================================================================

RatingFilterParam = Literal["good", "bad", "all"]


class FeedbackSummary(BaseModel):
    good_count: int
    bad_count: int
    good_ratio: float | None


class FeedbackSeriesItem(BaseModel):
    bucket_start: str
    good: int
    bad: int


class FeedbackItem(BaseModel):
    qa_log_id: int
    question_text: str
    answer_text: str | None
    rating: str
    segment: str | None
    created_at: str


class FeedbackResponse(BaseModel):
    unit: str
    from_: str = Field(alias="from")
    to: str
    rating_filter: str
    summary: FeedbackSummary
    series: list[FeedbackSeriesItem]
    items: list[FeedbackItem]
    page: int
    per_page: int
    total: int

    model_config = {"populate_by_name": True}


def _resolve_feedback_window(
    unit: Literal["day", "week", "month"],
    from_: date | None,
    to: date | None,
) -> tuple[datetime, datetime, date, date]:
    """KST half-open interval 반환: [start_kst, end_exclusive_kst), 사용자 from/to date."""
    if from_ is None and to is None:
        f, t = _feedback_default_window(unit)
    elif from_ is None:
        f, _ = _feedback_default_window(unit)
        t = to  # type: ignore[assignment]
    elif to is None:
        f = from_
        _, t = _feedback_default_window(unit)
    else:
        f, t = from_, to
    start_kst = _kst_datetime(f)
    end_exclusive_kst = _kst_datetime(t) + timedelta(days=1)
    return start_kst, end_exclusive_kst, f, t


@router.get("/feedback", response_model=FeedbackResponse, response_model_by_alias=True)
async def feedback(
    response: Response,
    unit: Literal["day", "week", "month"] = Query("month"),
    from_: date | None = Query(None, alias="from"),
    to: date | None = Query(None),
    rating_filter: RatingFilterParam = Query("all"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    q: str | None = Query(None),
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> FeedbackResponse:
    q_like = f"%{q}%" if q else None
    start_kst, end_exclusive_kst, from_date, to_date = _resolve_feedback_window(
        unit, from_, to
    )

    summary_data, series_data, total = await _gather_feedback(
        db, unit, start_kst, end_exclusive_kst, rating_filter, page, per_page, q_like
    )
    items_data = await get_feedback_items(
        db, start_kst, end_exclusive_kst, rating_filter, page, per_page, q_like
    )

    response.headers["Cache-Control"] = "no-store"
    logger.info(
        "admin.analytics.feedback.viewed",
        actor_user_id=actor.id,
        unit=unit,
        rating_filter=rating_filter,
        page=page,
        total=total,
    )

    return FeedbackResponse(
        unit=unit,
        from_=from_date.isoformat(),
        to=to_date.isoformat(),
        rating_filter=rating_filter,
        summary=FeedbackSummary(**summary_data),
        series=[FeedbackSeriesItem(**s) for s in series_data],
        items=[FeedbackItem(**item) for item in items_data],
        page=page,
        per_page=per_page,
        total=total,
    )


async def _gather_feedback(
    db: AsyncSession,
    unit: Literal["day", "week", "month"],
    start_kst: datetime,
    end_exclusive_kst: datetime,
    rating_filter: RatingFilterParam,
    page: int,
    per_page: int,
    q_like: str | None,
) -> tuple[dict, list, int]:
    summary_data = await get_feedback_summary(db, start_kst, end_exclusive_kst, q_like)
    series_data = await get_feedback_series(db, unit, start_kst, end_exclusive_kst, q_like)
    total = await get_feedback_items_total(
        db, start_kst, end_exclusive_kst, rating_filter, q_like
    )
    return summary_data, series_data, total


@router.get("/feedback/export")
async def feedback_export(
    unit: Literal["day", "week", "month"] = Query("month"),
    from_: date | None = Query(None, alias="from"),
    to: date | None = Query(None),
    rating_filter: RatingFilterParam = Query("all"),
    q: str | None = Query(None),
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    import openpyxl

    q_like = f"%{q}%" if q else None
    start_kst, end_exclusive_kst, from_date, to_date = _resolve_feedback_window(
        unit, from_, to
    )
    rows, truncated = await get_feedback_export_rows(
        db, start_kst, end_exclusive_kst, rating_filter, q_like
    )

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "피드백"
    ws.append(["qa_log_id", "질문", "답변", "피드백", "가입유형", "제출일시(KST)"])
    for row in rows:
        ws.append([
            row["qa_log_id"],
            row["question_text"],
            row["answer_text"] or "",
            row["rating"],
            row["segment"] or "",
            row["created_at_kst"],
        ])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"feedback_{from_date.isoformat()}_{to_date.isoformat()}.xlsx"
    content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    logger.info(
        "admin.analytics.feedback.exported",
        actor_user_id=actor.id,
        row_count=len(rows),
    )

    headers: dict[str, str] = {
        "Content-Disposition": f'attachment; filename="{filename}"',
    }
    if truncated:
        headers["X-Truncated"] = "true"

    return StreamingResponse(buf, media_type=content_type, headers=headers)


def _resolve_window(
    range_: str,
    year_month: str | None,
    from_: date | None,
    to: date | None,
) -> tuple[datetime, datetime, str | None]:
    if range_ == "month":
        if year_month is None:
            return kst_month_bounds()
        y, m = (int(p) for p in year_month.split("-"))
        start = datetime(y, m, 1, tzinfo=KST)
        end = (
            datetime(y + 1, 1, 1, tzinfo=KST)
            if m == 12
            else datetime(y, m + 1, 1, tzinfo=KST)
        )
        return start, end, year_month
    if range_ == "day":
        end_d = to or datetime.now(KST).date()
        start_d = from_ or (end_d - timedelta(days=30))
        return (
            datetime(start_d.year, start_d.month, start_d.day, tzinfo=KST),
            datetime(end_d.year, end_d.month, end_d.day, tzinfo=KST)
            + timedelta(days=1),
            None,
        )
    # year
    now = datetime.now(KST)
    return (
        datetime(now.year, 1, 1, tzinfo=KST),
        datetime(now.year + 1, 1, 1, tzinfo=KST),
        None,
    )


# =============================================================================
# Story 6.4 — 가입유형 통계 + 연차 히스토그램 + 엑셀 export
# =============================================================================


class SegmentRowResponse(BaseModel):
    segment: Literal["doctor", "hygienist", "student_other"]
    count: int
    active_count: int
    pro_count: int


class ExperienceRowResponse(BaseModel):
    segment: Literal["doctor", "hygienist"]
    years_bucket: Literal["0-2", "3-5", "6-10", "11-20", "20+"]
    count: int


class SegmentsAppliedFilters(BaseModel):
    include_withdrawn: bool
    include_blocked: bool


class SegmentsResponse(BaseModel):
    as_of: str
    applied_filters: SegmentsAppliedFilters
    total: int
    by_segment: list[SegmentRowResponse]
    by_experience: list[ExperienceRowResponse]


@router.get("/segments", response_model=SegmentsResponse)
async def segments(
    response: Response,
    as_of: Literal["now"] = Query("now"),
    include_withdrawn: bool = Query(False),
    include_blocked: bool = Query(False),
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> SegmentsResponse:
    stats = await get_segment_stats(
        db,
        include_withdrawn=include_withdrawn,
        include_blocked=include_blocked,
    )
    response.headers["Cache-Control"] = "no-store"
    logger.info(
        "admin.analytics.segments.viewed",
        actor_user_id=actor.id,
        total=stats["total"],
        include_withdrawn=include_withdrawn,
        include_blocked=include_blocked,
    )
    return SegmentsResponse(
        as_of=datetime.now(KST).isoformat(),
        applied_filters=SegmentsAppliedFilters(**stats["applied_filters"]),
        total=stats["total"],
        by_segment=[SegmentRowResponse(**r.__dict__) for r in stats["by_segment"]],
        by_experience=[
            ExperienceRowResponse(**r.__dict__) for r in stats["by_experience"]
        ],
    )


@router.get("/segments/export")
async def segments_export(
    include_withdrawn: bool = Query(False),
    include_blocked: bool = Query(False),
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    import openpyxl

    stats = await get_segment_stats(
        db,
        include_withdrawn=include_withdrawn,
        include_blocked=include_blocked,
    )
    rows, truncated = await get_segment_export_rows(
        db,
        include_withdrawn=include_withdrawn,
        include_blocked=include_blocked,
    )

    wb = openpyxl.Workbook()
    ws_sum = wb.active
    ws_sum.title = "Summary"
    ws_sum.append(["가입유형 통계 — 기준", datetime.now(KST).isoformat()])
    ws_sum.append([])
    ws_sum.append(["segment", "segment_label", "count", "active_count", "pro_count"])
    for r in stats["by_segment"]:
        ws_sum.append(
            [
                r.segment,
                SEGMENT_LABELS_KR.get(r.segment, ""),
                r.count,
                r.active_count,
                r.pro_count,
            ]
        )
    ws_sum.append([])
    ws_sum.append(["segment", "segment_label", "years_bucket", "count"])
    for r in stats["by_experience"]:
        ws_sum.append(
            [
                r.segment,
                SEGMENT_LABELS_KR.get(r.segment, ""),
                r.years_bucket,
                r.count,
            ]
        )

    ws_det = wb.create_sheet("Detail")
    if truncated:
        ws_det.append([f"※ {EXPORT_DETAIL_LIMIT}행으로 제한됨"])
    ws_det.append(
        [
            "user_id",
            "email_masked",
            "segment",
            "segment_label",
            "years_of_experience",
            "subscription_status",
            "created_at_kst",
        ]
    )
    for row in rows:
        ws_det.append(
            [
                row["user_id"],
                row["email_masked"],
                row["segment"],
                row["segment_label"],
                row["years_of_experience"],
                row["subscription_status"],
                row["created_at_kst"],
            ]
        )

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    today = datetime.now(KST).date().isoformat()
    filename = f"segments_{today}.xlsx"
    content_type = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    logger.info(
        "admin.analytics.segments.exported",
        actor_user_id=actor.id,
        row_count=len(rows),
        truncated=truncated,
    )

    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    if truncated:
        headers["X-Truncated"] = "true"
    return StreamingResponse(buf, media_type=content_type, headers=headers)


# =============================================================================
# Story 5.5 — 매출 + 토큰비용 차액 (A-106) + xlsx export (A-107)
# =============================================================================


def _validate_year_month(year_month: str | None) -> str:
    """year_month 검증 + None이면 현재 KST 월로 fallback."""
    if year_month is None:
        _start, _next, ym = kst_month_bounds()
        return ym
    if not YEAR_MONTH_RE.match(year_month):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_PARAM",
                "message": "year_month는 YYYY-MM 형식이어야 합니다.",
            },
        )
    return year_month


class RevenueVarianceFilters(BaseModel):
    year_month: str
    kst_start: str
    kst_end_exclusive: str


class RevenueVarianceResponse(BaseModel):
    year_month: str
    revenue_krw: int
    token_cost_usd: str
    token_cost_krw: int
    usd_to_krw: int
    variance_krw: int
    error_count: int
    anomaly_count: int
    applied_filters: RevenueVarianceFilters


class RevenueSeriesItem(BaseModel):
    year_month: str
    revenue_krw: int
    token_cost_krw: int
    variance_krw: int


class RevenueSeriesResponse(BaseModel):
    months: int
    to: str
    from_: str = Field(alias="from")
    usd_to_krw: int
    items: list[RevenueSeriesItem]

    model_config = {"populate_by_name": True}


@router.get(
    "/revenue-variance",
    response_model=RevenueVarianceResponse,
)
async def revenue_variance(
    response: Response,
    year_month: str | None = Query(None),
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
    redis_runtime: AsyncRedis = Depends(get_redis_runtime),
) -> RevenueVarianceResponse:
    ym = _validate_year_month(year_month)
    data = await get_revenue_variance_month(
        db, redis_runtime=redis_runtime, year_month=ym
    )
    response.headers["Cache-Control"] = "no-store"
    logger.info(
        "admin.finance.revenue_variance.viewed",
        actor_user_id=actor.id,
        year_month=ym,
        revenue_krw=data["revenue_krw"],
        variance_krw=data["variance_krw"],
    )
    return RevenueVarianceResponse(**data)


@router.get(
    "/revenue-variance/series",
    response_model=RevenueSeriesResponse,
    response_model_by_alias=True,
)
async def revenue_variance_series(
    response: Response,
    months: int = Query(12),
    to: str | None = Query(None),
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
    redis_runtime: AsyncRedis = Depends(get_redis_runtime),
) -> RevenueSeriesResponse:
    if months not in ALLOWED_SERIES_MONTHS:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_PARAM",
                "message": "months는 3/6/12/24 중 하나여야 합니다.",
            },
        )
    to_ym = _validate_year_month(to)
    data = await get_revenue_variance_series(
        db, redis_runtime=redis_runtime, months=months, to_year_month=to_ym
    )
    response.headers["Cache-Control"] = "no-store"
    logger.info(
        "admin.finance.revenue_variance.series.viewed",
        actor_user_id=actor.id,
        months=months,
        to=to_ym,
    )
    return RevenueSeriesResponse(
        months=data["months"],
        to=data["to"],
        usd_to_krw=data["usd_to_krw"],
        items=[RevenueSeriesItem(**i) for i in data["items"]],
        **{"from": data["from"]},
    )


@router.get("/revenue-variance/export")
async def revenue_variance_export(
    year_month: str = Query(...),
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
    redis_runtime: AsyncRedis = Depends(get_redis_runtime),
) -> StreamingResponse:
    import openpyxl

    ym = _validate_year_month(year_month)
    summary = await get_revenue_variance_month(
        db, redis_runtime=redis_runtime, year_month=ym
    )
    rows, truncated = await get_revenue_variance_export_rows(
        db, year_month=ym, limit=EXPORT_DETAIL_LIMIT_REVENUE
    )

    wb = openpyxl.Workbook()
    ws_sum = wb.active
    ws_sum.title = "Summary"
    ws_sum.append(["항목", "값"])
    ws_sum.append(["기간", f"{ym} (KST 1일 00:00 ~ 다음 달 1일 00:00)"])
    ws_sum.append(["당월 매출 (KRW)", summary["revenue_krw"]])
    ws_sum.append(["당월 토큰 비용 (USD)", summary["token_cost_usd"]])
    ws_sum.append(["적용 환율 (KRW/USD)", summary["usd_to_krw"]])
    ws_sum.append(["당월 토큰 비용 (KRW)", summary["token_cost_krw"]])
    ws_sum.append(["차액 (KRW)", summary["variance_krw"]])
    ws_sum.append(["결제 실패 건수", summary["error_count"]])
    ws_sum.append(["이상 이벤트 건수", summary["anomaly_count"]])
    ws_sum.append(["행 제한 (Detail)", EXPORT_DETAIL_LIMIT_REVENUE])
    ws_sum.append(["잘림 여부", "예" if truncated else "아니오"])

    ws_det = wb.create_sheet("Detail")
    if truncated:
        ws_det.append([f"※ {EXPORT_DETAIL_LIMIT_REVENUE}행으로 제한됨"])
    ws_det.append(
        [
            "payment_id",
            "charged_at_kst",
            "amount_krw",
            "user_id",
            "email_masked",
            "provider_order_id",
            "subscription_id",
        ]
    )
    for r in rows:
        ws_det.append(
            [
                _excel_safe_cell(r["payment_id"]),
                _excel_safe_cell(r["charged_at_kst"]),
                _excel_safe_cell(r["amount_krw"]),
                _excel_safe_cell(r["user_id"]),
                _excel_safe_cell(r["email_masked"]),
                _excel_safe_cell(r["provider_order_id"]),
                _excel_safe_cell(r["subscription_id"]),
            ]
        )

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"revenue_variance_{ym}.xlsx"
    headers_resp = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-store",
    }
    if truncated:
        headers_resp["X-Truncated"] = "true"

    logger.info(
        "admin.finance.revenue_variance.exported",
        actor_user_id=actor.id,
        year_month=ym,
        row_count=len(rows),
        truncated=truncated,
    )
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers_resp,
    )
