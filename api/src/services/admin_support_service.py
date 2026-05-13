"""Admin 고객문의 서비스 — Story 4.5 + Story 9.3 확장.

GET   list_inquiries      status_in / q / from / to 필터 + status CASE 정렬 (Story 9.3)
GET   get_inquiry         user 메타 + recent_qa 3건 + replies 이력 (Story 9.3)
PATCH update_inquiry      reply_message(plain text 4.5 호환) / status (force 분기 Story 9.3)
POST  create_reply        Tiptap reply_html 답변 (Story 9.3 신규) — inquiry_replies INSERT
GET   count_open          탭 카운트용 (Story 9.3 신규)
"""

from __future__ import annotations

import html as _html
import json
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import structlog
from fastapi import HTTPException, Request
from sqlalchemy import case, delete as sa_delete, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.middleware.audit_actions import (
    AUDIT_SUPPORT_REPLY,
    AUDIT_SUPPORT_REPLY_DELETE,
    AUDIT_SUPPORT_REPLY_EDIT,
)
from api.src.models.customer_inquiry import CustomerInquiry
from api.src.models.inbox_message import InboxMessage
from api.src.models.inquiry_attachment import InquiryAttachment
from api.src.models.inquiry_reply import InquiryReply
from api.src.models.qa_log import QALog
from api.src.models.user import User
from api.src.schemas.admin.support import (
    InquiryAttachmentItem,
    InquiryDetailResponse,
    InquiryListItem,
    InquiryListResponse,
    InquiryReplyEditRequest,
    InquiryReplyItem,
    InquiryReplyRequest,
    InquiryStatus,
    InquiryUpdateRequest,
    RecentQAExcerpt,
)
from api.src.services.analytics_service import _mask_email
from api.src.utils.html_sanitize import sanitize_body_html

logger = structlog.get_logger(__name__)

INQUIRY_REPLY_INBOX_TITLE = "고객문의 답변이 도착했습니다"
_RECENT_QA_LIMIT = 3  # Story 6.1은 10건. 본 스토리(9.3)는 직전 3건.
_KST = ZoneInfo("Asia/Seoul")

# AC-6: 정상 정방향 전이 (force=False 기본 허용)
_FORWARD_TRANSITIONS: dict[str, set[str]] = {
    "open": {"in_progress", "resolved"},
    "in_progress": {"resolved", "open"},  # in_progress → open은 재오픈 → 직접 의도이므로 허용
    "resolved": set(),  # resolved에서 다른 상태는 force 필요
}

_VALID_STATUSES: set[str] = {"open", "in_progress", "resolved"}


def _kst_date_range(f: date | None, t: date | None) -> tuple[datetime | None, datetime | None]:
    """from/to 날짜를 KST 기준 [시작, 끝+1일) UTC datetime 범위로 변환."""
    start_dt: datetime | None = None
    end_dt: datetime | None = None
    if f is not None:
        start_dt = datetime.combine(f, time.min).replace(tzinfo=_KST)
    if t is not None:
        end_dt = datetime.combine(t + timedelta(days=1), time.min).replace(tzinfo=_KST)
    return start_dt, end_dt


def _escape_ilike(q: str) -> str:
    """ILIKE 메타문자 escape — `_` / `%` / `\\`."""
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def list_inquiries(
    db: AsyncSession,
    *,
    status: InquiryStatus | None = None,
    status_in: set[str] | None = None,
    q: str | None = None,
    f: date | None = None,
    t: date | None = None,
    page: int = 1,
    per_page: int = 50,
) -> InquiryListResponse:
    """고객문의 목록 — Story 9.3: status_in 다중 필터 + q ILIKE 검색 + from/to 범위.

    하위 호환: status (4.5 단건) 단독 제공 시 status_in=[status]로 normalize.
    """
    if status is not None and status_in is None:
        status_in = {status}

    base = select(
        CustomerInquiry.id,
        CustomerInquiry.user_id,
        User.email,
        User.segment,
        CustomerInquiry.subject,
        CustomerInquiry.body,
        CustomerInquiry.inquiry_type,
        CustomerInquiry.status,
        CustomerInquiry.created_at,
        CustomerInquiry.resolved_at,
    ).join(User, User.id == CustomerInquiry.user_id)
    count_q = select(func.count()).select_from(CustomerInquiry).join(
        User, User.id == CustomerInquiry.user_id
    )

    filters = []
    if status_in:
        valid = status_in & _VALID_STATUSES
        if valid:
            filters.append(CustomerInquiry.status.in_(valid))

    start_dt, end_dt = _kst_date_range(f, t)
    if start_dt is not None:
        filters.append(CustomerInquiry.created_at >= start_dt)
    if end_dt is not None:
        filters.append(CustomerInquiry.created_at < end_dt)

    if q:
        pattern = f"%{_escape_ilike(q)}%"
        filters.append(
            or_(
                CustomerInquiry.subject.ilike(pattern, escape="\\"),
                CustomerInquiry.body.ilike(pattern, escape="\\"),
                User.email.ilike(pattern, escape="\\"),
            )
        )

    if filters:
        for ftr in filters:
            base = base.where(ftr)
            count_q = count_q.where(ftr)

    total_result = await db.execute(count_q)
    total = total_result.scalar_one()

    # AC-2: status='open' → 0, in_progress → 1, resolved → 2 + created_at DESC
    status_order = case(
        (CustomerInquiry.status == "open", 0),
        (CustomerInquiry.status == "in_progress", 1),
        (CustomerInquiry.status == "resolved", 2),
        else_=3,
    )
    rows_result = await db.execute(
        base.order_by(
            status_order,
            desc(CustomerInquiry.created_at),
            desc(CustomerInquiry.id),
        )
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
            body_preview=(row.body or "")[:80],
            inquiry_type=row.inquiry_type,
            segment=row.segment if row.segment in ("doctor", "hygienist", "student_other") else None,
            status=row.status,
            created_at=row.created_at,
            resolved_at=row.resolved_at,
        )
        for row in rows
    ]

    return InquiryListResponse(items=items, page=page, per_page=per_page, total=total)


async def _fetch_recent_qa(db: AsyncSession, user_id: int) -> list[RecentQAExcerpt]:
    """사용자 직전 질의 3건 발췌 (Story 6.1 패턴 답습, limit만 10→3)."""
    rows = (
        await db.execute(
            select(QALog.id, QALog.question_text, QALog.created_at)
            .where(QALog.user_id == user_id)
            .order_by(QALog.created_at.desc(), QALog.id.desc())
            .limit(_RECENT_QA_LIMIT)
        )
    ).all()
    return [
        RecentQAExcerpt(
            qa_log_id=r.id,
            question_excerpt=(r.question_text or "")[:60],
            created_at=r.created_at,
        )
        for r in rows
    ]


async def _fetch_replies(db: AsyncSession, inquiry_id: int) -> list[InquiryReplyItem]:
    """inquiry_replies + admin email join, 시간 ASC."""
    rows = (
        await db.execute(
            select(
                InquiryReply.id,
                InquiryReply.admin_id,
                User.email,
                InquiryReply.reply_html,
                InquiryReply.created_at,
            )
            .join(User, User.id == InquiryReply.admin_id)
            .where(InquiryReply.inquiry_id == inquiry_id)
            .order_by(InquiryReply.created_at.asc(), InquiryReply.id.asc())
        )
    ).all()
    return [
        InquiryReplyItem(
            reply_id=r.id,
            admin_id=r.admin_id,
            admin_email_masked=_mask_email(r.email),
            reply_html_safe=sanitize_body_html(r.reply_html),  # 응답 직전 이중 sanitize
            created_at=r.created_at,
        )
        for r in rows
    ]


async def _fetch_attachments(
    db: AsyncSession, inquiry_id: int
) -> list[InquiryAttachmentItem]:
    """문의 첨부 이미지 — id ASC."""
    rows = (
        await db.execute(
            select(InquiryAttachment)
            .where(InquiryAttachment.inquiry_id == inquiry_id)
            .order_by(InquiryAttachment.id.asc())
        )
    ).scalars().all()
    return [
        InquiryAttachmentItem(
            id=r.id,
            file_url=r.file_url,
            file_name=r.file_name,
            mime_type=r.mime_type,
            size_bytes=r.size_bytes,
        )
        for r in rows
    ]


async def get_inquiry(db: AsyncSession, inquiry_id: int) -> InquiryDetailResponse | None:
    """단건 상세 — 사용자 메타 + recent_qa(3건) + replies 이력 함께 조회."""
    result = await db.execute(
        select(
            CustomerInquiry.id,
            CustomerInquiry.user_id,
            User.email,
            User.phone,
            User.segment,
            User.subscription_status,
            User.created_at.label("user_created_at"),
            CustomerInquiry.subject,
            CustomerInquiry.body,
            CustomerInquiry.inquiry_type,
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

    recent_qa = await _fetch_recent_qa(db, row.user_id)
    replies = await _fetch_replies(db, inquiry_id)
    attachments = await _fetch_attachments(db, inquiry_id)

    sub_status = row.subscription_status if row.subscription_status in ("free", "pro", "blocked") else "free"
    seg = row.segment if row.segment in ("doctor", "hygienist", "student_other") else None

    return InquiryDetailResponse(
        id=row.id,
        user_id=row.user_id,
        user_email=row.email,
        user_phone=row.phone,
        subject=row.subject,
        body=row.body,
        inquiry_type=row.inquiry_type,
        status=row.status,
        created_at=row.created_at,
        resolved_at=row.resolved_at,
        user_segment=seg,
        user_subscription_status=sub_status,
        user_created_at=row.user_created_at,
        recent_qa=recent_qa,
        replies=replies,
        attachments=attachments,
    )


async def count_open_inquiries(db: AsyncSession) -> int:
    """탭 카운트용 — status='open' 만 집계 (in_progress 미포함)."""
    return (
        await db.execute(
            select(func.count())
            .select_from(CustomerInquiry)
            .where(CustomerInquiry.status == "open")
        )
    ).scalar_one()


async def update_inquiry(
    request: Request,
    db: AsyncSession,
    inquiry_id: int,
    payload: InquiryUpdateRequest,
    *,
    admin_id: int,
) -> InquiryDetailResponse | None:
    """4.5 호환 PATCH — reply_message(plain text) / status 변경.

    Story 9.3 확장:
    - 역행 전이 (resolved → open 등) force=False 시 409.
    - plain text 답변도 inquiry_replies row를 함께 INSERT하여 추후 편집/삭제 시
      쪽지함과 1:1 매칭(reply_id)이 가능하도록 한다.
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
        reply = InquiryReply(
            inquiry_id=inquiry.id,
            admin_id=admin_id,
            reply_html=safe_body,
        )
        db.add(reply)
        await db.flush()
        db.add(
            InboxMessage(
                user_id=inquiry.user_id,
                notice_id=None,
                popup_id=None,
                inquiry_id=inquiry.id,
                reply_id=reply.id,
                type="system",
                title=INQUIRY_REPLY_INBOX_TITLE,
                body_html=safe_body,
            )
        )
        inquiry.status = "resolved"
        inquiry.resolved_at = func.now()
        reply_sent = True
    elif payload.status is not None:
        # AC-6 force 분기 — 역행 차단
        if payload.status != inquiry.status:
            allowed = _FORWARD_TRANSITIONS.get(inquiry.status, set())
            if payload.status not in allowed and not payload.force:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "INQUIRY_STATUS_REVERT_REQUIRES_CONFIRMATION",
                        "message": "완료된 문의를 재개하려면 확인이 필요합니다.",
                        "current_status": inquiry.status,
                        "requested_status": payload.status,
                    },
                )
        inquiry.status = payload.status
        if payload.status == "resolved" and inquiry.resolved_at is None:
            inquiry.resolved_at = func.now()
        elif payload.status != "resolved":
            # 역행 전이 시 resolved_at 보존(기록 유지) — 명시적 정책
            pass

    await db.flush()
    await db.refresh(inquiry)

    after = {"status": inquiry.status, "resolved_at": _iso(inquiry.resolved_at)}

    request.state.audit_action = AUDIT_SUPPORT_REPLY
    request.state.audit_target_type = "customer_inquiry"
    request.state.audit_target_id = inquiry.id
    request.state.audit_diff = json.dumps(
        {"before": before, "after": after, "reply_sent": reply_sent, "force": payload.force},
        ensure_ascii=False,
    )

    await db.commit()

    return await get_inquiry(db, inquiry_id)


async def create_reply(
    request: Request,
    db: AsyncSession,
    inquiry_id: int,
    payload: InquiryReplyRequest,
    *,
    admin_id: int,
) -> InquiryDetailResponse | None:
    """Story 9.3 신규 — Tiptap reply_html 답변.

    1. inquiry_replies row INSERT (sanitize된 HTML).
    2. customer_inquiries.status 갱신 (default 'resolved').
    3. inbox_messages type='system' INSERT (sanitize된 본문).
    4. audit_logs 트리거(미들웨어).
    5. 알림톡 fire-and-forget은 라우터에서 처리 (response 직후).
    """
    inquiry_row = await db.execute(
        select(CustomerInquiry).where(CustomerInquiry.id == inquiry_id)
    )
    inquiry = inquiry_row.scalar_one_or_none()
    if inquiry is None:
        return None

    safe_html = sanitize_body_html(payload.reply_html)
    if not safe_html.strip():
        # sanitize 결과가 빈 본문이면 422
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_PARAM",
                "message": "본문이 비어 있습니다.",
                "field": "reply_html",
            },
        )

    reply = InquiryReply(
        inquiry_id=inquiry_id,
        admin_id=admin_id,
        reply_html=safe_html,
    )
    db.add(reply)
    await db.flush()

    new_status = payload.new_status or "resolved"
    before_status = inquiry.status
    inquiry.status = new_status
    if new_status == "resolved" and inquiry.resolved_at is None:
        inquiry.resolved_at = func.now()

    db.add(
        InboxMessage(
            user_id=inquiry.user_id,
            notice_id=None,
            popup_id=None,
            inquiry_id=inquiry_id,
            reply_id=reply.id,
            type="system",
            title=INQUIRY_REPLY_INBOX_TITLE,
            body_html=safe_html,
        )
    )

    await db.flush()

    request.state.audit_action = AUDIT_SUPPORT_REPLY
    request.state.audit_target_type = "customer_inquiry"
    request.state.audit_target_id = inquiry_id
    request.state.audit_diff = json.dumps(
        {
            "status_change": {"before": before_status, "after": new_status},
            "reply_id": reply.id,
            "reply_html_length": len(safe_html),
        },
        ensure_ascii=False,
    )

    # 라우터에서 알림톡을 fire-and-forget 발송하기 위해 reply.id, user_id, subject를 state에 저장
    request.state.support_reply_user_id = inquiry.user_id
    request.state.support_reply_id = reply.id
    request.state.support_reply_inquiry_subject = inquiry.subject[:30]

    await db.commit()

    return await get_inquiry(db, inquiry_id)


async def update_reply(
    request: Request,
    db: AsyncSession,
    inquiry_id: int,
    reply_id: int,
    payload: InquiryReplyEditRequest,
    *,
    admin_id: int,
) -> InquiryDetailResponse | None:
    """관리자 답변 수정 — inquiry_replies.reply_html 갱신 + 매칭 inbox 본문 동기.

    1. inquiry_replies row 검증 (inquiry_id 일치).
    2. reply_html sanitize → 비어있으면 422.
    3. inquiry_replies.reply_html 갱신.
    4. inbox_messages 중 reply_id 일치 row의 body_html 동기 갱신.
       (구버전 데이터로 reply_id가 NULL이면 동기 대상 없음 — inquiry만 갱신.)
    5. audit_logs는 미들웨어가 응답 직후 자동 INSERT.
    """
    reply_row = await db.execute(
        select(InquiryReply).where(
            InquiryReply.id == reply_id,
            InquiryReply.inquiry_id == inquiry_id,
        )
    )
    reply = reply_row.scalar_one_or_none()
    if reply is None:
        return None

    safe_html = sanitize_body_html(payload.reply_html)
    if not safe_html.strip():
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_PARAM",
                "message": "본문이 비어 있습니다.",
                "field": "reply_html",
            },
        )

    before_len = len(reply.reply_html)
    reply.reply_html = safe_html

    # 사용자 쪽지함 동기 — reply_id로 매칭되는 row 모두 갱신(보통 1건).
    inbox_rows = (
        await db.execute(
            select(InboxMessage).where(InboxMessage.reply_id == reply_id)
        )
    ).scalars().all()
    inbox_updated = 0
    for inbox in inbox_rows:
        inbox.body_html = safe_html
        inbox_updated += 1

    await db.flush()

    request.state.audit_action = AUDIT_SUPPORT_REPLY_EDIT
    request.state.audit_target_type = "inquiry_reply"
    request.state.audit_target_id = reply_id
    request.state.audit_diff = json.dumps(
        {
            "inquiry_id": inquiry_id,
            "reply_id": reply_id,
            "before_length": before_len,
            "after_length": len(safe_html),
            "inbox_synced": inbox_updated,
        },
        ensure_ascii=False,
    )

    await db.commit()

    return await get_inquiry(db, inquiry_id)


async def delete_reply(
    request: Request,
    db: AsyncSession,
    inquiry_id: int,
    reply_id: int,
    *,
    admin_id: int,
) -> InquiryDetailResponse | None:
    """관리자 답변 삭제 — inquiry_replies row 삭제 + 매칭 inbox row 동기 삭제.

    1. inquiry_replies row 검증.
    2. inbox_messages 중 reply_id 일치 row 먼저 삭제(사용자 쪽지에서 회수).
    3. inquiry_replies row 삭제.
    4. 남은 답변이 0건이고 현재 status='resolved'이면 status='open'으로 되돌리고
       resolved_at을 NULL로 비운다 — 답변이 없는데 "답변완료"로 남는 표시 모순을 차단.
    5. audit_logs는 미들웨어가 응답 직후 자동 INSERT.
    """
    reply_row = await db.execute(
        select(InquiryReply).where(
            InquiryReply.id == reply_id,
            InquiryReply.inquiry_id == inquiry_id,
        )
    )
    reply = reply_row.scalar_one_or_none()
    if reply is None:
        return None

    inquiry = (
        await db.execute(
            select(CustomerInquiry).where(CustomerInquiry.id == inquiry_id)
        )
    ).scalar_one()

    inbox_result = await db.execute(
        sa_delete(InboxMessage).where(InboxMessage.reply_id == reply_id)
    )
    inbox_deleted = inbox_result.rowcount or 0

    await db.delete(reply)
    await db.flush()

    remaining = (
        await db.execute(
            select(func.count())
            .select_from(InquiryReply)
            .where(InquiryReply.inquiry_id == inquiry_id)
        )
    ).scalar_one()

    status_reverted = False
    before_status = inquiry.status
    if remaining == 0 and inquiry.status == "resolved":
        inquiry.status = "open"
        inquiry.resolved_at = None
        status_reverted = True
        await db.flush()

    request.state.audit_action = AUDIT_SUPPORT_REPLY_DELETE
    request.state.audit_target_type = "inquiry_reply"
    request.state.audit_target_id = reply_id
    request.state.audit_diff = json.dumps(
        {
            "inquiry_id": inquiry_id,
            "reply_id": reply_id,
            "inbox_deleted": inbox_deleted,
            "remaining_replies": remaining,
            "status_reverted": status_reverted,
            "status_before": before_status,
            "status_after": inquiry.status,
        },
        ensure_ascii=False,
    )

    await db.commit()

    return await get_inquiry(db, inquiry_id)


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


__all__ = [
    "list_inquiries",
    "get_inquiry",
    "update_inquiry",
    "create_reply",
    "update_reply",
    "delete_reply",
    "count_open_inquiries",
    "INQUIRY_REPLY_INBOX_TITLE",
]
