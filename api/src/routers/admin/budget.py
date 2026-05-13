"""Story 5.2 — 예산 실시간 데이터 API."""

from decimal import Decimal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_serializer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.deps.auth import require_admin
from api.src.middleware.audit_actions import (
    AUDIT_BUDGET_LIMIT_UPDATE,
    audit_action,
)
from api.src.models.base import get_session
from api.src.models.budget_threshold import BudgetThreshold
from api.src.models.killswitch_state import MODE_MANUAL_TOTAL
from api.src.models.user import User
from api.src.services.budget_service import (
    get_current_month_snapshot,
    kst_month_bounds,
)
from api.src.services.killswitch_service import get_active_modes

router = APIRouter(prefix="/admin/budget", tags=["admin-budget"])


class BudgetCurrentMonthResponse(BaseModel):
    year_month: str
    monthly_limit_usd: Decimal
    spent_usd: Decimal
    percent: float
    status: str
    killswitch_active: bool
    killswitch_mode: str | None

    model_config = ConfigDict()

    @field_serializer("monthly_limit_usd", "spent_usd")
    def _ser_decimal(self, v: Decimal) -> str:
        return f"{v:.6f}" if v.as_tuple().exponent < -2 else f"{v:.2f}"


class UpdateMonthlyLimitRequest(BaseModel):
    monthly_limit_usd: Decimal = Field(
        gt=Decimal("0"),
        le=Decimal("999999.99"),
        description="당월 KST 토큰 예산 한도(USD). 0 초과 999,999.99 이하.",
    )


async def _build_response(
    response: Response, db: AsyncSession
) -> BudgetCurrentMonthResponse:
    snap = await get_current_month_snapshot(db)
    await db.commit()
    modes = await get_active_modes(db)
    response.headers["Cache-Control"] = "no-store"
    return BudgetCurrentMonthResponse(
        year_month=snap.year_month,
        monthly_limit_usd=snap.monthly_limit_usd,
        spent_usd=snap.spent_usd,
        percent=snap.percent,
        status=snap.status,
        killswitch_active=bool(modes),
        killswitch_mode=(
            MODE_MANUAL_TOTAL
            if MODE_MANUAL_TOTAL in modes
            else (next(iter(modes)) if modes else None)
        ),
    )


@router.get("/current-month", response_model=BudgetCurrentMonthResponse)
async def current_month(
    response: Response,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> BudgetCurrentMonthResponse:
    return await _build_response(response, db)


@router.patch("/monthly-limit", response_model=BudgetCurrentMonthResponse)
@audit_action(AUDIT_BUDGET_LIMIT_UPDATE)
async def update_monthly_limit(
    payload: UpdateMonthlyLimitRequest,
    request: Request,
    response: Response,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> BudgetCurrentMonthResponse:
    """당월(KST) 예산 한도(monthly_limit_usd) 조정.

    audit_logs INSERT 는 PATCH 미들웨어가 응답 직후 자동 수행.
    임계(80/95/100%) 재판정·알림은 다음 budget-task tick 에서 갱신된 한도 기준으로 처리.
    """
    _, _, ym = kst_month_bounds()
    threshold = (
        await db.execute(
            select(BudgetThreshold).where(BudgetThreshold.year_month == ym)
        )
    ).scalar_one_or_none()
    before_limit: Decimal | None = (
        threshold.monthly_limit_usd if threshold is not None else None
    )
    if threshold is None:
        threshold = BudgetThreshold(
            year_month=ym,
            monthly_limit_usd=payload.monthly_limit_usd,
        )
        db.add(threshold)
    else:
        threshold.monthly_limit_usd = payload.monthly_limit_usd
    await db.flush()

    request.state.audit_target_type = "budget_threshold"
    request.state.audit_target_id = str(threshold.id)
    request.state.audit_diff = {
        "year_month": ym,
        "monthly_limit_usd": {
            "before": f"{before_limit:.2f}" if before_limit is not None else None,
            "after": f"{payload.monthly_limit_usd:.2f}",
        },
    }
    return await _build_response(response, db)
