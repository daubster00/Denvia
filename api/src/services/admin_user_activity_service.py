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

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.anomaly_event import AnomalyEvent
from api.src.models.customer_inquiry import CustomerInquiry
from api.src.models.qa_log import QALog
from api.src.schemas.admin.user_activity import (
    UserAnomalyEventItem,
    UserAnomalyEventListResponse,
    UserInquiryItem,
    UserInquiryListResponse,
    UserQALogItem,
    UserQALogListResponse,
)

logger = structlog.get_logger(__name__)

_QA_EXCERPT_LEN = 120
_INQUIRY_PREVIEW_LEN = 120


def _excerpt(text: str | None, length: int) -> str:
    if not text:
        return ""
    if len(text) <= length:
        return text
    return text[:length] + "…"


async def list_user_qa_logs(
    db: AsyncSession,
    *,
    user_id: int,
    page: int = 1,
    per_page: int = 20,
) -> UserQALogListResponse:
    """qa_logs 페이지네이션 (user_id 필터, created_at DESC)."""
    where_clause = QALog.user_id == user_id

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
            question_excerpt=_excerpt(row.question_text, _QA_EXCERPT_LEN),
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
    "list_user_inquiries",
    "list_user_anomaly_events",
]
