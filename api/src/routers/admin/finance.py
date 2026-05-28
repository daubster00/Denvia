"""Story 9.1 — 관리자 결제 기록 타임라인 (A-501) 라우터.

3개의 GET 전용 endpoint:
- GET /admin/payments/events           : 일자별 타임라인 + 페이지네이션 + KPI 합계
- GET /admin/payments/events/{event_id}: 단건 + raw_response_json 원본
- GET /admin/payments/events/export    : Detail/Summary 2-시트 xlsx

5.4(analytics) 패턴을 따라 Cache-Control: no-store + X-Truncated 헤더를 사용한다.
admin write 0건 — audit_logs INSERT 0건(AuditMiddleware GET 자동 제외).
"""

import io
from datetime import date, datetime, timedelta

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.deps.auth import require_admin, require_admin_page
from api.src.models.base import get_session
from api.src.models.user import User
from api.src.schemas.admin.finance import (
    PaymentEventDetailResponse,
    PaymentEventListResponse,
)
from api.src.services import finance_service
from api.src.services.budget_service import KST

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/admin/payments",
    tags=["admin-finance"],
    dependencies=[Depends(require_admin_page("/admin/finance"))],
)

_ALLOWED_PER_PAGE = (50, 100, 200)
_VALID_STATUS = {"pending", "success", "failed", "refunded", "refund_pending"}


def _parse_status_in(value: str | None) -> set[str] | None:
    if not value:
        return None
    parts = {p.strip() for p in value.split(",") if p.strip()}
    if not parts:
        return None
    invalid = parts - _VALID_STATUS
    if invalid:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_PARAM",
                "message": f"status_in 허용 값 외: {sorted(invalid)}",
            },
        )
    return parts


async def _resolve_user_filter(
    db: AsyncSession, value: str | None
) -> tuple[int | None, bool]:
    """필터 입력값을 (user_id, found) 튜플로 해석한다.

    - None/공백 → (None, True): 필터 미적용.
    - 전부 숫자 → 그대로 int 캐스팅. 존재 여부는 별도 확인하지 않는다(기존 동작 호환).
    - 그 외 → user role 계정의 email 정확 일치로 user_id 조회. 없으면 (None, False).

    found=False가 반환되면 호출자는 빈 결과를 돌려주어야 한다.
    """
    if value is None:
        return None, True
    v = value.strip()
    if not v:
        return None, True
    if v.isdigit():
        try:
            uid = int(v)
        except ValueError:
            return None, False
        if uid < 1:
            return None, False
        return uid, True
    if len(v) > 255:
        return None, False
    row = await db.execute(
        select(User.id).where(User.email == v, User.role == "user").limit(1)
    )
    uid = row.scalar_one_or_none()
    if uid is None:
        return None, False
    return int(uid), True


def _resolve_window(from_: date | None, to: date | None) -> tuple[date, date]:
    today = datetime.now(KST).date()
    t = to or today
    f = from_ or (t - timedelta(days=30))
    if f > t:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_PARAM", "message": "from은 to보다 이전이어야 합니다."},
        )
    return f, t


@router.get("/events", response_model=PaymentEventListResponse)
async def list_payment_events(
    response: Response,
    from_: date | None = Query(None, alias="from"),
    to: date | None = Query(None),
    status_in: str | None = Query(None),
    user_id: str | None = Query(None, max_length=255),
    provider_error_code: str | None = Query(None, min_length=1, max_length=50),
    page: int = Query(1, ge=1),
    per_page: int = Query(50),
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> PaymentEventListResponse:
    if per_page not in _ALLOWED_PER_PAGE:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_PARAM",
                "message": "per_page는 50/100/200 중 하나여야 합니다.",
            },
        )
    f, t = _resolve_window(from_, to)
    status_set = _parse_status_in(status_in)
    resolved_user_id, user_found = await _resolve_user_filter(db, user_id)

    if not user_found:
        response.headers["Cache-Control"] = "no-store"
        logger.info(
            "admin.finance.payments.viewed",
            actor_user_id=actor.id,
            from_=f.isoformat(),
            to=t.isoformat(),
            status_in=sorted(status_set) if status_set else None,
            user_id=user_id,
            user_id_resolved=None,
            provider_error_code=provider_error_code,
            page=page,
            per_page=per_page,
            total=0,
            user_lookup_miss=True,
        )
        return PaymentEventListResponse(
            items=[],
            page=page,
            per_page=per_page,
            total=0,
            error_code_summary=None,
        )

    items, total, error_summary = await finance_service.list_payment_events(
        db,
        f=f,
        t=t,
        status_in=status_set,
        user_id=resolved_user_id,
        error_code=provider_error_code,
        page=page,
        per_page=per_page,
    )

    response.headers["Cache-Control"] = "no-store"
    logger.info(
        "admin.finance.payments.viewed",
        actor_user_id=actor.id,
        from_=f.isoformat(),
        to=t.isoformat(),
        status_in=sorted(status_set) if status_set else None,
        user_id=user_id,
        user_id_resolved=resolved_user_id,
        provider_error_code=provider_error_code,
        page=page,
        per_page=per_page,
        total=total,
    )
    return PaymentEventListResponse(
        items=items,
        page=page,
        per_page=per_page,
        total=total,
        error_code_summary=error_summary,
    )


@router.get("/events/export")
async def export_payment_events(
    from_: date | None = Query(None, alias="from"),
    to: date | None = Query(None),
    status_in: str | None = Query(None),
    user_id: str | None = Query(None, max_length=255),
    provider_error_code: str | None = Query(None, min_length=1, max_length=50),
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    import openpyxl

    f, t = _resolve_window(from_, to)
    status_set = _parse_status_in(status_in)
    resolved_user_id, user_found = await _resolve_user_filter(db, user_id)

    if not user_found:
        rows: list[list] = []
        truncated = False
        summary: dict = {
            "from": f.isoformat(),
            "to": t.isoformat(),
            "user_id": user_id,
            "row_count": 0,
            "note": "해당 사용자 ID/이메일을 찾을 수 없습니다.",
        }
    else:
        rows, truncated, summary = await finance_service.export_payment_events(
            db,
            f=f,
            t=t,
            status_in=status_set,
            user_id=resolved_user_id,
            error_code=provider_error_code,
        )

    wb = openpyxl.Workbook()
    ws_sum = wb.active
    ws_sum.title = "Summary"
    ws_sum.append(["항목", "값"])
    for k, v in summary.items():
        ws_sum.append([finance_service._excel_safe_cell(k), finance_service._excel_safe_cell(v)])

    ws = wb.create_sheet("Detail")
    ws.append(list(finance_service._EXPORT_COLUMNS))
    for r in rows:
        ws.append(r)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"payment_events_{f.isoformat()}_{t.isoformat()}.xlsx"
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-store",
    }
    if truncated:
        headers["X-Truncated"] = "true"

    logger.info(
        "admin.finance.payments.exported",
        actor_user_id=actor.id,
        row_count=len(rows),
        truncated=truncated,
    )
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


@router.get("/events/{event_id}", response_model=PaymentEventDetailResponse)
async def get_payment_event(
    event_id: int,
    response: Response,
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> PaymentEventDetailResponse:
    detail = await finance_service.get_payment_event(db, event_id=event_id)
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "EVENT_NOT_FOUND",
                "message": "결제 이벤트를 찾을 수 없습니다.",
            },
        )
    response.headers["Cache-Control"] = "no-store"
    logger.info(
        "admin.finance.payment_event.viewed",
        actor_user_id=actor.id,
        event_id=event_id,
        payment_id=detail.payment_id,
    )
    return detail
