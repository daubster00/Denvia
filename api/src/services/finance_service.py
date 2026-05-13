"""Story 9.1 — payment_events admin 조회·집계·export 서비스 (A-501).

핵심 책임:
- list_payment_events: payment_events LEFT JOIN payments/users/billing_keys + JSONB code 추출
- get_payment_event: 단건 + raw_response_json 원본 dict 노출
- export_payment_events: Detail/Summary 2-시트 xlsx (limit+1 fetch로 truncated 판단)
- _excel_safe_cell: CSV-injection 방어 (=, +, -, @ prefix 처리)

5.4(analytics) / 4.4(me/payments) 패턴을 그대로 재사용한다.
"""

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.billing_key import BillingKey
from api.src.models.payment import Payment
from api.src.models.payment_event import PaymentEvent
from api.src.models.user import User
from api.src.schemas.admin.finance import (
    ErrorCodeSummary,
    PaymentEventDetailResponse,
    PaymentEventItem,
)
from api.src.services.analytics_service import _mask_email
from api.src.services.budget_service import KST

EXPORT_DETAIL_LIMIT = 10_000  # Story 9.1 AC-6 — 5.4의 5_000보다 큼(결제 데이터 누적 대비)


def _excel_safe_cell(value: Any) -> Any:
    """CSV-injection 방어 — `=`/`+`/`-`/`@`로 시작하면 prefix `'`을 붙인다.

    엑셀이 셀 값을 수식으로 해석하면 외부 URL fetch나 명령 실행 위험이 있다.
    str이 아닌 값은 변환 없이 그대로 반환한다(int, datetime 등).
    """
    if isinstance(value, str) and value and value[0] in ("=", "+", "-", "@"):
        return f"'{value}"
    return value


def _kst_window(f: date, t: date) -> tuple[datetime, datetime]:
    """[from 00:00 KST, (to+1) 00:00 KST) 범위로 변환."""
    start = datetime(f.year, f.month, f.day, tzinfo=KST)
    end_excl = datetime(t.year, t.month, t.day, tzinfo=KST) + timedelta(days=1)
    return start, end_excl


def _bk_subquery():
    """billing_keys 결제 시점 매칭용 서브쿼리 (Story 4.4 패턴 그대로)."""
    return (
        select(
            BillingKey.user_id.label("bk_user_id"),
            BillingKey.created_at.label("bk_created_at"),
            BillingKey.revoked_at.label("bk_revoked_at"),
            BillingKey.card_last4.label("bk_card_last4"),
            BillingKey.card_company.label("bk_card_company"),
        )
        .subquery()
    )


def _row_to_item(r: Any) -> PaymentEventItem:
    raw = r.raw_response_json or {}
    return PaymentEventItem(
        event_id=r.event_id,
        payment_id=r.payment_id,
        event_type=r.event_type,
        charged_at=r.created_at.isoformat() if r.created_at else None,
        amount_krw=r.amount_krw,
        user_id=r.p_user_id,
        user_email_masked=_mask_email(r.email),
        card_last4=r.bk_card_last4,
        card_company=r.bk_card_company,
        provider_order_id=r.provider_order_id,
        provider_error_code=raw.get("code"),
        provider_error_message=raw.get("message"),
        status=r.payment_status,
    )


def _build_base_select():
    bk = _bk_subquery()
    stmt = (
        select(
            PaymentEvent.id.label("event_id"),
            PaymentEvent.payment_id,
            PaymentEvent.event_type,
            PaymentEvent.created_at,
            PaymentEvent.raw_response_json,
            Payment.amount_krw,
            Payment.provider_order_id,
            Payment.status.label("payment_status"),
            Payment.user_id.label("p_user_id"),
            Payment.charged_at.label("p_charged_at"),
            User.email,
            bk.c.bk_card_last4,
            bk.c.bk_card_company,
        )
        .join(Payment, Payment.id == PaymentEvent.payment_id)
        .join(User, User.id == Payment.user_id)
        .join(
            bk,
            (bk.c.bk_user_id == Payment.user_id)
            & (Payment.charged_at.isnot(None))
            & (Payment.charged_at >= bk.c.bk_created_at)
            & (
                (bk.c.bk_revoked_at.is_(None))
                | (Payment.charged_at < bk.c.bk_revoked_at)
            ),
            isouter=True,
        )
    )
    return stmt


def _apply_filters(
    stmt,
    *,
    start: datetime,
    end_excl: datetime,
    status_in: set[str] | None,
    user_id: int | None,
    error_code: str | None,
):
    stmt = stmt.where(PaymentEvent.created_at >= start)
    stmt = stmt.where(PaymentEvent.created_at < end_excl)
    if status_in:
        stmt = stmt.where(Payment.status.in_(status_in))
    if user_id is not None:
        stmt = stmt.where(Payment.user_id == user_id)
    if error_code:
        stmt = stmt.where(PaymentEvent.raw_response_json["code"].astext == error_code)
    return stmt


async def list_payment_events(
    session: AsyncSession,
    *,
    f: date,
    t: date,
    status_in: set[str] | None,
    user_id: int | None,
    error_code: str | None,
    page: int,
    per_page: int,
) -> tuple[list[PaymentEventItem], int, ErrorCodeSummary | None]:
    start, end_excl = _kst_window(f, t)

    base = _apply_filters(
        _build_base_select(),
        start=start,
        end_excl=end_excl,
        status_in=status_in,
        user_id=user_id,
        error_code=error_code,
    )

    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await session.execute(count_stmt)).scalar_one()

    rows_stmt = (
        base.order_by(desc(PaymentEvent.created_at), desc(PaymentEvent.id))
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    rows = (await session.execute(rows_stmt)).all()
    items = [_row_to_item(r) for r in rows]

    error_summary: ErrorCodeSummary | None = None
    if error_code:
        # 동일 WHERE 조건의 charge_failed 이벤트만 따로 합계 (페이지네이션과 별개)
        err_stmt = (
            select(
                func.count(PaymentEvent.id).label("event_cnt"),
                func.count(func.distinct(Payment.user_id)).label("user_cnt"),
            )
            .join(Payment, Payment.id == PaymentEvent.payment_id)
            .where(PaymentEvent.created_at >= start)
            .where(PaymentEvent.created_at < end_excl)
            .where(PaymentEvent.event_type == "charge_failed")
            .where(PaymentEvent.raw_response_json["code"].astext == error_code)
        )
        if status_in:
            err_stmt = err_stmt.where(Payment.status.in_(status_in))
        if user_id is not None:
            err_stmt = err_stmt.where(Payment.user_id == user_id)
        err_row = (await session.execute(err_stmt)).one()
        error_summary = ErrorCodeSummary(
            event_count=int(err_row.event_cnt or 0),
            affected_user_count=int(err_row.user_cnt or 0),
        )

    return items, int(total), error_summary


def _extract_refund_reason_from_event(raw: Any) -> str | None:
    """payment_events.raw_response_json에서 사용자 입력 환불 사유 추출.

    두 경로를 모두 본다:
    1) 수동 큐 진입 시 _enqueue_manual_review가 박는 명시적 `reason` (refund_requested 이벤트)
    2) 토스 자동 환불 응답의 `cancels[*].cancelReason` (refund_success 이벤트, 가장 최근 취소 우선)
    """
    if not isinstance(raw, dict):
        return None
    reason = raw.get("reason")
    if isinstance(reason, str) and reason.strip():
        return reason
    cancels = raw.get("cancels")
    if isinstance(cancels, list):
        sorted_cancels = sorted(
            (c for c in cancels if isinstance(c, dict)),
            key=lambda c: c.get("canceledAt") or "",
            reverse=True,
        )
        for c in sorted_cancels:
            cr = c.get("cancelReason")
            if isinstance(cr, str) and cr.strip():
                return cr
    return None


async def get_payment_event(
    session: AsyncSession, *, event_id: int
) -> PaymentEventDetailResponse | None:
    """단건 조회 — list와 동일 JOIN + raw_response_json + 환불 사유 폴백."""
    stmt = _build_base_select().where(PaymentEvent.id == event_id).limit(1)
    row = (await session.execute(stmt)).first()
    if row is None:
        return None
    item = _row_to_item(row)

    # 환불 사유: 현재 이벤트의 raw_response_json에서 추출 → 같은 결제의 다른 환불 이벤트로 폴백.
    refund_reason = _extract_refund_reason_from_event(row.raw_response_json)
    if not refund_reason:
        reason_stmt = (
            select(PaymentEvent.raw_response_json)
            .where(
                PaymentEvent.payment_id == row.payment_id,
                PaymentEvent.event_type.in_(
                    ("refund_requested", "refund_success", "refund_denied")
                ),
                PaymentEvent.id != event_id,
            )
            .order_by(desc(PaymentEvent.created_at), desc(PaymentEvent.id))
        )
        for r in (await session.execute(reason_stmt)).all():
            candidate = _extract_refund_reason_from_event(r[0])
            if candidate:
                refund_reason = candidate
                break

    return PaymentEventDetailResponse(
        **item.model_dump(),
        raw_response_json=row.raw_response_json,
        refund_reason=refund_reason,
    )


_EXPORT_COLUMNS = (
    "event_id",
    "payment_id",
    "event_type",
    "created_at_kst",
    "amount_krw",
    "user_id",
    "email_masked",
    "card_last4",
    "card_company",
    "provider_order_id",
    "provider_error_code",
    "provider_error_message",
    "status",
)


async def export_payment_events(
    session: AsyncSession,
    *,
    f: date,
    t: date,
    status_in: set[str] | None,
    user_id: int | None,
    error_code: str | None,
) -> tuple[list[list[Any]], bool, dict[str, Any]]:
    """Detail rows + truncated 플래그 + Summary dict.

    EXPORT_DETAIL_LIMIT+1 fetch로 truncated 판단.
    """
    start, end_excl = _kst_window(f, t)
    base = _apply_filters(
        _build_base_select(),
        start=start,
        end_excl=end_excl,
        status_in=status_in,
        user_id=user_id,
        error_code=error_code,
    )
    rows_stmt = base.order_by(
        desc(PaymentEvent.created_at), desc(PaymentEvent.id)
    ).limit(EXPORT_DETAIL_LIMIT + 1)
    raw_rows = (await session.execute(rows_stmt)).all()

    truncated = len(raw_rows) > EXPORT_DETAIL_LIMIT
    if truncated:
        raw_rows = raw_rows[:EXPORT_DETAIL_LIMIT]

    detail_rows: list[list[Any]] = []
    for r in raw_rows:
        item = _row_to_item(r)
        created_kst = r.created_at.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S") if r.created_at else ""
        detail_rows.append(
            [
                _excel_safe_cell(item.event_id),
                _excel_safe_cell(item.payment_id),
                _excel_safe_cell(item.event_type),
                _excel_safe_cell(created_kst),
                _excel_safe_cell(item.amount_krw),
                _excel_safe_cell(item.user_id),
                _excel_safe_cell(item.user_email_masked),
                _excel_safe_cell(item.card_last4 or ""),
                _excel_safe_cell(item.card_company or ""),
                _excel_safe_cell(item.provider_order_id),
                _excel_safe_cell(item.provider_error_code or ""),
                _excel_safe_cell(item.provider_error_message or ""),
                _excel_safe_cell(item.status),
            ]
        )

    # Summary 집계 — 동일 필터 적용
    def _count_when(value: str):
        return func.coalesce(
            func.sum(case((PaymentEvent.event_type == value, 1), else_=0)),
            0,
        )

    summary_stmt = (
        select(
            func.count(PaymentEvent.id).label("total"),
            _count_when("charge_success").label("success_n"),
            _count_when("charge_failed").label("failed_n"),
            _count_when("refund_success").label("refund_success_n"),
            _count_when("refund_requested").label("refund_req_n"),
        )
        .select_from(PaymentEvent)
        .join(Payment, Payment.id == PaymentEvent.payment_id)
        .where(PaymentEvent.created_at >= start)
        .where(PaymentEvent.created_at < end_excl)
    )
    if status_in:
        summary_stmt = summary_stmt.where(Payment.status.in_(status_in))
    if user_id is not None:
        summary_stmt = summary_stmt.where(Payment.user_id == user_id)
    if error_code:
        summary_stmt = summary_stmt.where(
            PaymentEvent.raw_response_json["code"].astext == error_code
        )
    s_row = (await session.execute(summary_stmt)).one()

    # 에러 코드별 분포 상위 10개 + "기타"
    # 주: PaymentEvent.raw_response_json["code"].astext를 SELECT/GROUP BY에 동시
    # 사용하면 SQLAlchemy가 별도 bindparam을 생성해 PostgreSQL grouping 검증이
    # 실패한다. func.jsonb_extract_path_text로 명시적 함수 호출하면 동일 표현식이
    # 재사용되어 문제가 해소된다.
    err_col = func.jsonb_extract_path_text(PaymentEvent.raw_response_json, "code")
    err_stmt = (
        select(
            err_col.label("err"),
            func.count(PaymentEvent.id).label("cnt"),
        )
        .join(Payment, Payment.id == PaymentEvent.payment_id)
        .where(PaymentEvent.created_at >= start)
        .where(PaymentEvent.created_at < end_excl)
        .where(PaymentEvent.event_type == "charge_failed")
        .where(err_col.is_not(None))
        .group_by(err_col)
        .order_by(desc(func.count(PaymentEvent.id)))
        .limit(11)
    )
    if status_in:
        err_stmt = err_stmt.where(Payment.status.in_(status_in))
    if user_id is not None:
        err_stmt = err_stmt.where(Payment.user_id == user_id)
    if error_code:
        err_stmt = err_stmt.where(err_col == error_code)
    err_dist = (await session.execute(err_stmt)).all()

    summary: dict[str, Any] = {
        "기간": f"{f.isoformat()} ~ {t.isoformat()}",
        "총 이벤트 수": int(s_row.total or 0),
        "결제 완료": int(s_row.success_n or 0),
        "결제 실패": int(s_row.failed_n or 0),
        "환불 완료": int(s_row.refund_success_n or 0),
        "환불 요청": int(s_row.refund_req_n or 0),
        "행 제한": EXPORT_DETAIL_LIMIT,
        "잘림 여부": "예" if truncated else "아니오",
    }
    top_10 = err_dist[:10]
    rest = err_dist[10:]
    for i, e in enumerate(top_10, start=1):
        summary[f"에러코드 #{i} ({e.err})"] = int(e.cnt)
    if rest:
        summary["에러코드 기타"] = int(sum(e.cnt for e in rest))

    return detail_rows, truncated, summary


__all__ = [
    "EXPORT_DETAIL_LIMIT",
    "_excel_safe_cell",
    "_EXPORT_COLUMNS",
    "list_payment_events",
    "get_payment_event",
    "export_payment_events",
]
