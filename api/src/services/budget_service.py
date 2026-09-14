"""BudgetService — 당월 KST 합계, 임계 분류, 자동 해제 판정."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

_YM_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")

from api.src.models.qa_log import QALog
from api.src.models.budget_threshold import BudgetThreshold
from api.src.models.rebuild_job import RebuildJob
from api.src.settings import settings

KST = timezone(timedelta(hours=9))


@dataclass(frozen=True)
class CurrentMonthSnapshot:
    year_month: str
    monthly_limit_usd: Decimal
    spent_usd: Decimal      # qa_spent_usd + rebuild_spent_usd — 예산 판정의 기준값
    percent: float          # 소수 둘째 자리 반올림
    status: str             # "normal" | "warning" | "critical"
    # ── 지출 내역 분해 (수정요청 게시판 #145) ──────────────────
    # qa_spent_usd     : 챗봇 대화(질의응답) 비용 — qa_logs.cost_usd 합계
    # rebuild_spent_usd: 지식 재구축(임베딩) 비용 — rebuild_jobs.embedding_cost_usd 합계
    # 기본값을 둔 것은 기존 호출부(위치 인자 5개) 호환을 위함.
    qa_spent_usd: Decimal = Decimal("0")
    rebuild_spent_usd: Decimal = Decimal("0")


def kst_month_bounds(now: datetime | None = None) -> tuple[datetime, datetime, str]:
    now = (now or datetime.now(KST)).astimezone(KST)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        next_start = start.replace(year=start.year + 1, month=1)
    else:
        next_start = start.replace(month=start.month + 1)
    return start, next_start, start.strftime("%Y-%m")


def kst_month_bounds_for_ym(ym: str) -> tuple[datetime, datetime, str]:
    """'YYYY-MM' 문자열(두자리 월 강제)을 받아 그 달의 KST [시작, 다음달 시작) 경계를 반환.

    형식이 잘못되면 ValueError. 라우터에서 422로 변환.
    """
    if not isinstance(ym, str):
        raise ValueError(f"invalid year-month: {ym!r}")
    m = _YM_RE.match(ym)
    if not m:
        raise ValueError(f"invalid year-month: {ym!r}")
    year, month = int(m.group(1)), int(m.group(2))
    start = datetime(year, month, 1, tzinfo=KST)
    if month == 12:
        next_start = datetime(year + 1, 1, 1, tzinfo=KST)
    else:
        next_start = datetime(year, month + 1, 1, tzinfo=KST)
    return start, next_start, start.strftime("%Y-%m")


def _as_decimal(value: object) -> Decimal:
    """SUM 결과를 Decimal 로 통일. 드라이버·백엔드에 따라 int/float 로 올 수 있다."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value or 0))


def classify(percent: float) -> str:
    if percent >= 95:
        return "critical"
    if percent >= 80:
        return "warning"
    return "normal"


async def get_current_month_snapshot(
    session: AsyncSession,
    ym: str | None = None,
) -> CurrentMonthSnapshot:
    """KST 한 달치 사용 스냅샷.

    - ym 미지정: 현재 KST 월. 한도 행이 없으면 기본 한도로 자동 생성(기존 동작 유지).
    - ym 지정: 그 달의 사용액·한도 조회. 한도 행이 없어도 생성하지 않고
      `settings.denvia_initial_monthly_budget_usd`를 폴백 한도로 사용
      (과거 달은 이미 끝났으므로 행을 새로 만들 이유가 없음).
    """
    if ym is None:
        start_kst, end_kst, ym_resolved = kst_month_bounds()
        create_if_missing = True
    else:
        start_kst, end_kst, ym_resolved = kst_month_bounds_for_ym(ym)
        create_if_missing = False

    sum_stmt = select(
        func.coalesce(func.sum(QALog.cost_usd), Decimal("0"))
    ).where(QALog.created_at >= start_kst, QALog.created_at < end_kst)
    qa_spent = _as_decimal((await session.execute(sum_stmt)).scalar_one())

    # #145 — 지식 재구축(임베딩) 비용도 한 달 지출에 포함한다.
    # 재구축은 특정 회원의 질문이 아니라 관리자 작업이라 user 필터가 없다.
    # 2026-09-14 이전 재구축은 embedding_cost_usd 가 NULL 이라 SUM 에서 자동 제외된다.
    rebuild_stmt = select(
        func.coalesce(func.sum(RebuildJob.embedding_cost_usd), Decimal("0"))
    ).where(RebuildJob.created_at >= start_kst, RebuildJob.created_at < end_kst)
    rebuild_spent = _as_decimal((await session.execute(rebuild_stmt)).scalar_one())

    spent: Decimal = qa_spent + rebuild_spent

    threshold = (await session.execute(
        select(BudgetThreshold).where(BudgetThreshold.year_month == ym_resolved)
    )).scalar_one_or_none()

    if threshold is None:
        if create_if_missing:
            threshold = BudgetThreshold(
                year_month=ym_resolved,
                monthly_limit_usd=settings.denvia_initial_monthly_budget_usd,
            )
            session.add(threshold)
            await session.flush()
            limit = threshold.monthly_limit_usd
        else:
            limit = settings.denvia_initial_monthly_budget_usd
    else:
        limit = threshold.monthly_limit_usd

    percent = float(round((spent / limit) * 100, 2)) if limit > 0 else 0.0
    return CurrentMonthSnapshot(
        year_month=ym_resolved,
        monthly_limit_usd=limit,
        spent_usd=spent,
        percent=percent,
        status=classify(percent),
        qa_spent_usd=qa_spent,
        rebuild_spent_usd=rebuild_spent,
    )
