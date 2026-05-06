"""Admin 고객문의 서비스 — Story 9.3 계열.

목록·상세·상태변경/답변 등록 비즈니스 로직.

답변 등록 흐름:
1. customer_inquiries.status='resolved' + resolved_at=now() 로 마감.
2. inbox_messages 에 type='system' 행 1건 INSERT (사용자 알림).
3. request.state.audit_* 를 채워 미들웨어가 audit_logs INSERT 하도록 트리거.
"""

from __future__ import annotations

import html as _html
import json

import structlog
from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.middleware.audit_actions import AUDIT_SUPPORT_REPLY
from api.src.models.customer_inquiry import CustomerInquiry
from api.src.models.inbox_message import InboxMessage
from api.src.models.user import User
from api.src.schemas.admin.support import (
    InquiryDetailResponse,
    InquiryListItem,
    InquiryListResponse,
    InquiryStatus,
    InquiryUpdateRequest,
)

logger = structlog.get_logger(__name__)

INQUIRY_REPLY_INBOX_TITLE = "고객문의 답변이 도착했습니다"


async def list_inquiries(
    db: AsyncSession,
    *,
    status: InquiryStatus | None = None,
    page: int = 1,
    per_page: int = 20,
) -> InquiryListResponse:
    """고객문의 목록 — status 필터 + 페이지네이션, 최신순 정렬."""
    base = (
        select(
            CustomerInquiry.id,
            CustomerInquiry.user_id,
            User.email,
            CustomerInquiry.subject,
            CustomerInquiry.status,
            CustomerInquiry.created_at,
            CustomerInquiry.resolved_at,
        )
        .join(User, User.id == CustomerInquiry.user_id)
    )
    count_q = select(func.count()).select_from(CustomerInquiry)

    if status is not None:
        base = base.where(CustomerInquiry.status == status)
        count_q = count_q.where(CustomerInquiry.status == status)

    total_result = await db.execute(count_q)
    total = total_result.scalar_one()

    rows_result = await db.execute(
        base.order_by(CustomerInquiry.created_at.desc(), CustomerInquiry.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    rows = rows_result.all()

    items = [
        InquiryListItem(
            id=row.id,
            user_id=row.user_id,
            user_email=row.email,
            subject=row.subject,
            status=row.status,
            created_at=row.created_at,
            resolved_at=row.resolved_at,
        )
        for row in rows
    ]

    return InquiryListResponse(items=items, page=page, per_page=per_page, total=total)


async def get_inquiry(db: AsyncSession, inquiry_id: int) -> InquiryDetailResponse | None:
    """단건 상세 — 사용자 이메일·휴대폰 함께 조회. 없으면 None."""
    result = await db.execute(
        select(
            CustomerInquiry.id,
            CustomerInquiry.user_id,
            User.email,
            User.phone,
            CustomerInquiry.subject,
            CustomerInquiry.body,
            CustomerInquiry.status,
            CustomerInquiry.created_at,
            CustomerInquiry.resolved_at,
        )
        .join(User, User.id == CustomerInquiry.user_id)
        .where(CustomerInquiry.id == inquiry_id)
    )
    row = result.first()
    if row is None:
        return None
    return InquiryDetailResponse(
        id=row.id,
        user_id=row.user_id,
        user_email=row.email,
        user_phone=row.phone,
        subject=row.subject,
        body=row.body,
        status=row.status,
        created_at=row.created_at,
        resolved_at=row.resolved_at,
    )


async def update_inquiry(
    request: Request,
    db: AsyncSession,
    inquiry_id: int,
    payload: InquiryUpdateRequest,
) -> InquiryDetailResponse | None:
    """상태 변경 / 답변 등록.

    - reply_message 가 있으면 status='resolved' 로 자동 마감되고, 사용자 inbox 에
      type='system' 메시지가 INSERT 된다 (이메일 0건 정책 준수).
    - audit_logs INSERT 는 미들웨어가 응답 직후 자동 처리한다.
    """
    inquiry_row = await db.execute(
        select(CustomerInquiry).where(CustomerInquiry.id == inquiry_id)
    )
    inquiry = inquiry_row.scalar_one_or_none()
    if inquiry is None:
        return None

    before = {"status": inquiry.status, "resolved_at": _iso(inquiry.resolved_at)}
    reply_sent = False

    if payload.reply_message is not None:
        safe_body = _html.escape(payload.reply_message)
        # 답변 알림 — inbox_messages.type='system' (notice/popup 미연동)
        inbox = InboxMessage(
            user_id=inquiry.user_id,
            notice_id=None,
            popup_id=None,
            type="system",
            title=INQUIRY_REPLY_INBOX_TITLE,
            body_html=safe_body,
        )
        db.add(inbox)
        inquiry.status = "resolved"
        inquiry.resolved_at = func.now()
        reply_sent = True
    elif payload.status is not None:
        inquiry.status = payload.status
        if payload.status == "resolved" and inquiry.resolved_at is None:
            inquiry.resolved_at = func.now()

    await db.flush()
    await db.refresh(inquiry)

    after = {"status": inquiry.status, "resolved_at": _iso(inquiry.resolved_at)}

    # audit middleware 가 읽을 상태 채우기
    request.state.audit_action = AUDIT_SUPPORT_REPLY
    request.state.audit_target_type = "customer_inquiry"
    request.state.audit_target_id = inquiry.id
    request.state.audit_diff = json.dumps(
        {"before": before, "after": after, "reply_sent": reply_sent},
        ensure_ascii=False,
    )

    await db.commit()

    return await get_inquiry(db, inquiry_id)


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


__all__ = ["list_inquiries", "get_inquiry", "update_inquiry"]
