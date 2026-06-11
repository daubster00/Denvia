"""Admin 사용자 활동 로그 도메인 로직 (Story 6.1 확장).

본 모듈은 단일 사용자에 대한 활동 로그 페이지네이션을 제공한다:
- list_user_qa_logs       : qa_logs 테이블 user_id 필터
- list_user_inquiries     : customer_inquiries 테이블 user_id 필터
- list_user_anomaly_events: anomaly_events 테이블 target_user_id 필터

설계 결정:
- 각 카테고리는 (count + select) 2쿼리. N+1 없음.
- 사용자 존재 확인은 호출 라우터가 admin_user_service.get_user_detail 으로 선행 검증.
- 정렬: created_at DESC (시간 역순).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.anomaly_event import AnomalyEvent
from api.src.models.customer_inquiry import CustomerInquiry
from api.src.models.qa_log import QALog
from api.src.schemas.admin.user_activity import (
    RetrievedDocItem,
    UserAnomalyEventItem,
    UserAnomalyEventListResponse,
    UserInquiryItem,
    UserInquiryListResponse,
    UserQALogDetail,
    UserQALogItem,
    UserQALogListResponse,
)
from api.src.services.budget_service import KST

logger = structlog.get_logger(__name__)

_INQUIRY_PREVIEW_LEN = 120


def _excerpt(text: str | None, length: int) -> str:
    if not text:
        return ""
    if len(text) <= length:
        return text
    return text[:length] + "…"


def _kst_window(
    f: date | None, t: date | None
) -> tuple[datetime | None, datetime | None]:
    """[from 00:00 KST, (to+1) 00:00 KST). 한쪽만 있으면 그쪽 경계만 반환."""
    start = (
        datetime(f.year, f.month, f.day, tzinfo=KST) if f is not None else None
    )
    end_excl = (
        datetime(t.year, t.month, t.day, tzinfo=KST) + timedelta(days=1)
        if t is not None
        else None
    )
    return start, end_excl


async def list_user_qa_logs(
    db: AsyncSession,
    *,
    user_id: int,
    page: int = 1,
    per_page: int = 20,
    date_from: date | None = None,
    date_to: date | None = None,
) -> UserQALogListResponse:
    """qa_logs 페이지네이션 (user_id 필터, created_at DESC).

    date_from/date_to 는 KST 기준 자정~다음날 자정 윈도우로 변환해
    qa_logs.created_at 에 적용한다.
    """
    conds = [QALog.user_id == user_id]
    start, end_excl = _kst_window(date_from, date_to)
    if start is not None:
        conds.append(QALog.created_at >= start)
    if end_excl is not None:
        conds.append(QALog.created_at < end_excl)
    where_clause = and_(*conds)

    total = (
        await db.execute(select(func.count()).select_from(QALog).where(where_clause))
    ).scalar_one()

    rows = (
        await db.execute(
            select(QALog)
            .where(where_clause)
            .order_by(QALog.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
    ).scalars().all()

    items = [
        UserQALogItem(
            qa_log_id=row.id,
            question_excerpt=row.question_text or "",
            answer_excerpt=row.answer_text or "",
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
            cost_usd=row.cost_usd,
            latency_ms=row.latency_ms,
            status=row.status,
            rule_matched=row.rule_matched,
            created_at=row.created_at,
        )
        for row in rows
    ]
    return UserQALogListResponse(
        items=items, page=page, per_page=per_page, total=int(total)
    )


async def get_user_qa_log_detail(
    db: AsyncSession,
    *,
    user_id: int,
    qa_log_id: int,
) -> UserQALogDetail | None:
    """qa_logs 단건 상세 — 관리자 '상세보기' 전용.

    user_id × qa_log_id 교차 검증으로 다른 사용자의 로그 노출을 차단한다.
    반환은 normalized_query, retrieved_docs 포함 (본 마이그레이션 이전 행은 None).
    """
    row = (
        await db.execute(
            select(QALog).where(QALog.id == qa_log_id, QALog.user_id == user_id)
        )
    ).scalar_one_or_none()
    if row is None:
        return None

    raw_docs = row.retrieved_docs or []
    docs: list[RetrievedDocItem] = []
    for entry in raw_docs:
        if not isinstance(entry, dict):
            continue
        docs.append(
            RetrievedDocItem(
                page_content=str(entry.get("page_content", "")),
                metadata=entry.get("metadata") or {},
            )
        )

    return UserQALogDetail(
        qa_log_id=row.id,
        question_text=row.question_text or "",
        normalized_query=row.normalized_query,
        retrieved_docs=docs,
        prompt_text=row.prompt_text,
        answer_text=row.answer_text,
        rule_matched=bool(row.rule_matched),
        status=row.status,
        input_tokens=row.input_tokens,
        output_tokens=row.output_tokens,
        cost_usd=row.cost_usd,
        latency_ms=row.latency_ms,
        created_at=row.created_at,
    )


async def list_user_inquiries(
    db: AsyncSession,
    *,
    user_id: int,
    page: int = 1,
    per_page: int = 20,
) -> UserInquiryListResponse:
    """customer_inquiries 페이지네이션 (user_id 필터, created_at DESC)."""
    where_clause = CustomerInquiry.user_id == user_id

    total = (
        await db.execute(
            select(func.count()).select_from(CustomerInquiry).where(where_clause)
        )
    ).scalar_one()

    rows = (
        await db.execute(
            select(CustomerInquiry)
            .where(where_clause)
            .order_by(CustomerInquiry.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
    ).scalars().all()

    items = [
        UserInquiryItem(
            id=row.id,
            subject=row.subject,
            body_preview=_excerpt(row.body, _INQUIRY_PREVIEW_LEN),
            status=row.status,
            created_at=row.created_at,
            resolved_at=row.resolved_at,
        )
        for row in rows
    ]
    return UserInquiryListResponse(
        items=items, page=page, per_page=per_page, total=int(total)
    )


async def list_user_anomaly_events(
    db: AsyncSession,
    *,
    user_id: int,
    page: int = 1,
    per_page: int = 20,
) -> UserAnomalyEventListResponse:
    """anomaly_events 페이지네이션 (target_user_id 필터, created_at DESC)."""
    where_clause = AnomalyEvent.target_user_id == user_id

    total = (
        await db.execute(
            select(func.count()).select_from(AnomalyEvent).where(where_clause)
        )
    ).scalar_one()

    rows = (
        await db.execute(
            select(AnomalyEvent)
            .where(where_clause)
            .order_by(AnomalyEvent.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
    ).scalars().all()

    items = [
        UserAnomalyEventItem(
            id=row.id,
            type=row.type,
            ip=row.ip,
            ua=row.ua,
            status=row.status,
            created_at=row.created_at,
        )
        for row in rows
    ]
    return UserAnomalyEventListResponse(
        items=items, page=page, per_page=per_page, total=int(total)
    )


__all__ = [
    "list_user_qa_logs",
    "get_user_qa_log_detail",
    "list_user_inquiries",
    "list_user_anomaly_events",
]
