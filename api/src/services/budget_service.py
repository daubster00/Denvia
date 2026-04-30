"""BudgetService — 당월 KST 합계, 임계 분류, 자동 해제 판정."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.qa_log import QALog
from api.src.models.budget_threshold import BudgetThreshold
from api.src.settings import settings

KST = timezone(timedelta(hours=9))


@dataclass(frozen=True)
class CurrentMonthSnapshot:
    year_month: str
    monthly_limit_usd: Decimal
    spent_usd: Decimal
    percent: float          # 소수 둘째 자리 반올림
    status: str             # "normal" | "warning" | "critical"


def kst_month_bounds(now: datetime | None = None) -> tuple[datetime, datetime, str]:
    now = (now or datetime.now(KST)).astimezone(KST)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        next_start = start.replace(year=start.year + 1, month=1)
    else:
        next_start = start.replace(month=start.month + 1)
    return start, next_start, start.strftime("%Y-%m")


def classify(percent: float) -> str:
    if percent >= 95:
        return "critical"
    if percent >= 80:
        return "warning"
    return "normal"


async def get_current_month_snapshot(
    session: AsyncSession,
) -> CurrentMonthSnapshot:
    start_kst, end_kst, ym = kst_month_bounds()
    sum_stmt = select(
        func.coalesce(func.sum(QALog.cost_usd), Decimal("0"))
    ).where(QALog.created_at >= start_kst, QALog.created_at < end_kst)
    spent: Decimal = (await session.execute(sum_stmt)).scalar_one()

    threshold = (await session.execute(
        select(BudgetThreshold).where(BudgetThreshold.year_month == ym)
    )).scalar_one_or_none()
    if threshold is None:
        threshold = BudgetThreshold(
            year_month=ym,
            monthly_limit_usd=settings.denvia_initial_monthly_budget_usd,
        )
        session.add(threshold)
        await session.flush()

    limit = threshold.monthly_limit_usd
    percent = float(round((spent / limit) * 100, 2)) if limit > 0 else 0.0
    return CurrentMonthSnapshot(
        year_month=ym,
        monthly_limit_usd=limit,
        spent_usd=spent,
        percent=percent,
        status=classify(percent),
    )
