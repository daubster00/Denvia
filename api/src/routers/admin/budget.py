"""Story 5.2 — 예산 실시간 데이터 API."""

from decimal import Decimal

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_serializer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.deps.auth import require_admin, require_admin_page
from api.src.deps.redis import get_redis_runtime
from api.src.middleware.audit_actions import (
    AUDIT_BUDGET_LIMIT_UPDATE,
    audit_action,
)
from api.src.models.base import get_session
from api.src.models.budget_threshold import BudgetThreshold
from api.src.models.killswitch_state import MODE_MANUAL_TOTAL
from api.src.models.user import User
from api.src.services import runtime_config_service
from api.src.services.budget_service import (
    get_current_month_snapshot,
    kst_month_bounds,
)
from api.src.services.killswitch_service import get_active_modes

router = APIRouter(
    prefix="/admin/budget",
    tags=["admin-budget"],
    dependencies=[Depends(require_admin_page("/admin"))],
)


class BudgetCurrentMonthResponse(BaseModel):
    year_month: str
    monthly_limit_usd: Decimal
    spent_usd: Decimal
    # Story: 전체 시스템 KRW 통일 — UI 표시용 환산 보조 필드.
    # DB 원본은 USD 유지(OpenAI 청구가 USD), API 응답 시점에만 환율로 환산해 부착.
    monthly_limit_krw: int
    spent_krw: int
    usd_to_krw: int
    percent: float
    status: str
    killswitch_active: bool
    killswitch_mode: str | None
    # 과거 월(이미 지나간 달) 조회면 true. UI에서 게이지·kill-switch 라벨을
    # "현재 상태"가 아닌 "그 달의 결과"로 보여주기 위한 힌트.
    is_past_month: bool

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
    response: Response,
    db: AsyncSession,
    redis_runtime: aioredis.Redis,
    ym: str | None = None,
) -> BudgetCurrentMonthResponse:
    snap = await get_current_month_snapshot(db, ym=ym)
    await db.commit()
    _, _, current_ym = kst_month_bounds()
    is_past = snap.year_month != current_ym
    # killswitch는 "현재" 상태 — 과거 월 조회 시에는 게이지를 빨간 상태로
    # 만들지 않도록 false로 마스킹한다.
    if is_past:
        modes: set[str] = set()
    else:
        modes = await get_active_modes(db)
    usd_to_krw = await runtime_config_service.get_usd_to_krw(redis_runtime)
    monthly_limit_krw = int(
        (snap.monthly_limit_usd * Decimal(usd_to_krw)).quantize(Decimal("1"))
    )
    spent_krw = int(
        (snap.spent_usd * Decimal(usd_to_krw)).quantize(Decimal("1"))
    )
    response.headers["Cache-Control"] = "no-store"
    return BudgetCurrentMonthResponse(
        year_month=snap.year_month,
        monthly_limit_usd=snap.monthly_limit_usd,
        spent_usd=snap.spent_usd,
        monthly_limit_krw=monthly_limit_krw,
        spent_krw=spent_krw,
        usd_to_krw=usd_to_krw,
        percent=snap.percent,
        status=snap.status,
        killswitch_active=bool(modes),
        killswitch_mode=(
            MODE_MANUAL_TOTAL
            if MODE_MANUAL_TOTAL in modes
            else (next(iter(modes)) if modes else None)
        ),
        is_past_month=is_past,
    )


@router.get("/current-month", response_model=BudgetCurrentMonthResponse)
async def current_month(
    response: Response,
    ym: str | None = Query(
        default=None,
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
        description="조회할 KST 월 (YYYY-MM). 생략 시 현재 월. 미래 월은 422.",
    ),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
    redis_runtime: aioredis.Redis = Depends(get_redis_runtime),
) -> BudgetCurrentMonthResponse:
    if ym is not None:
        _, _, current_ym = kst_month_bounds()
        if ym > current_ym:
            raise HTTPException(
                status_code=422,
                detail="future month not allowed",
            )
    return await _build_response(response, db, redis_runtime, ym=ym)


@router.patch("/monthly-limit", response_model=BudgetCurrentMonthResponse)
@audit_action(AUDIT_BUDGET_LIMIT_UPDATE)
async def update_monthly_limit(
    payload: UpdateMonthlyLimitRequest,
    request: Request,
    response: Response,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
    redis_runtime: aioredis.Redis = Depends(get_redis_runtime),
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
    return await _build_response(response, db, redis_runtime)
