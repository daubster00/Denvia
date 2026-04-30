"""Story 5.2 — 예산 실시간 데이터 API."""

from decimal import Decimal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, field_serializer
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.deps.auth import require_admin
from api.src.models.base import get_session
from api.src.models.killswitch_state import MODE_MANUAL_TOTAL
from api.src.models.user import User
from api.src.services.budget_service import get_current_month_snapshot
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


@router.get("/current-month", response_model=BudgetCurrentMonthResponse)
async def current_month(
    response: Response,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
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
