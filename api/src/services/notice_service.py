"""공지(쪽지) 관리 서비스 — Story 7.1.

작성 시 즉시 발행: 매칭 segment의 모든 user에 inbox_messages 한 행씩 INSERT.
편집은 미지원(스냅샷 무결성 보호). 삭제는 hard delete + CASCADE로 사용자
inbox에서도 회수된다(잘못 발행한 쪽지의 즉시 철회 용도).

권한 경계: 모든 함수가 admin User를 요구한다. require_admin은 라우터 레벨에서 강제.
"""

from __future__ import annotations

from datetime import datetime, timezone

import structlog
from fastapi import HTTPException, Request
from sqlalchemy import case, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.inbox_message import InboxMessage
from api.src.models.notice import Notice
from api.src.models.user import User
from api.src.schemas.admin.notice import (
    NoticeCreateRequest,
    NoticeDetailResponse,
    NoticeListItem,
    NoticeListResponse,
    NoticeRecipientItem,
    NoticeRecipientsResponse,
)
from api.src.utils.html_sanitize import sanitize_body_html

logger = structlog.get_logger()


def _delivered_count_subq():
    """notice_id별 inbox_messages 행 수 — fan-out 결과 집계용."""
    return (
        select(InboxMessage.notice_id, func.count(InboxMessage.id).label("delivered"))
        .where(InboxMessage.notice_id.is_not(None))
        .group_by(InboxMessage.notice_id)
        .subquery()
    )


async def list_notices(
    page: int, per_page: int, admin: User, db: AsyncSession
) -> NoticeListResponse:
    total = (await db.execute(select(func.count(Notice.id)))).scalar_one()

    delivered_sq = _delivered_count_subq()
    rows = (
        await db.execute(
            select(
                Notice,
                func.coalesce(delivered_sq.c.delivered, 0).label("delivered"),
            )
            .outerjoin(delivered_sq, delivered_sq.c.notice_id == Notice.id)
            .order_by(Notice.created_at.desc(), Notice.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
    ).all()

    logger.info(
        "admin.notices.listed",
        actor_user_id=admin.id,
        page=page,
        per_page=per_page,
        total=int(total),
    )

    items = [
        NoticeListItem(
            id=n.id,
            title=n.title,
            target_segment=n.target_segment,
            published_at=n.published_at,
            created_by_admin_id=n.created_by_admin_id,
            created_at=n.created_at,
            delivered_user_count=int(delivered),
        )
        for n, delivered in rows
    ]
    return NoticeListResponse(
        items=items, page=page, per_page=per_page, total=int(total)
    )


async def get_notice_detail(
    notice_id: int, admin: User, db: AsyncSession
) -> NoticeDetailResponse:
    notice = (
        await db.execute(select(Notice).where(Notice.id == notice_id))
    ).scalar_one_or_none()
    if notice is None:
        raise HTTPException(
            404,
            detail={
                "code": "NOTICE_NOT_FOUND",
                "message": "해당 쪽지를 찾을 수 없습니다.",
            },
        )

    delivered = (
        await db.execute(
            select(func.count(InboxMessage.id)).where(
                InboxMessage.notice_id == notice_id
            )
        )
    ).scalar_one()

    logger.info(
        "admin.notice.viewed", actor_user_id=admin.id, notice_id=notice.id
    )
    return NoticeDetailResponse(
        id=notice.id,
        title=notice.title,
        body_html=notice.body_html,
        target_segment=notice.target_segment,
        published_at=notice.published_at,
        created_by_admin_id=notice.created_by_admin_id,
        created_at=notice.created_at,
        delivered_user_count=int(delivered),
    )


def _segment_user_filter(target_segment: str):
    """target_segment에 매칭되는 user들의 WHERE 조건 리스트.

    - 'all'   → 모든 활성 사용자(role='user' — admin은 본 알림 제외).
    - others  → User.segment 일치.
    탈퇴한 사용자(withdrawn_at IS NOT NULL)는 항상 제외.
    """
    base = [User.role == "user", User.withdrawn_at.is_(None)]
    if target_segment == "all":
        return base
    return base + [User.segment == target_segment]


async def create_notice(
    request: Request,
    body: NoticeCreateRequest,
    admin: User,
    db: AsyncSession,
) -> NoticeDetailResponse:
    """쪽지 작성 + 즉시 발행 + fan-out.

    1) notices 테이블에 1행 INSERT (published_at = NOW)
    2) target_segment 매칭 user들에 inbox_messages bulk INSERT
       (title/body_html 스냅샷 — 이후 notice 본문 편집과 무관)
    """
    sanitized = sanitize_body_html(body.body_html)
    now = datetime.now(timezone.utc)

    notice = Notice(
        title=body.title,
        body_html=sanitized,
        target_segment=body.target_segment,
        published_at=now,
        created_by_admin_id=admin.id,
    )
    db.add(notice)
    await db.flush()

    user_ids = (
        (
            await db.execute(
                select(User.id).where(*_segment_user_filter(body.target_segment))
            )
        )
        .scalars()
        .all()
    )

    inbox_rows = [
        {
            "user_id": uid,
            "notice_id": notice.id,
            "popup_id": None,
            "type": "notice",
            "title": notice.title,
            "body_html": sanitized,
            "is_read": False,
            "seen_popup_at": None,
        }
        for uid in user_ids
    ]
    if inbox_rows:
        await db.execute(InboxMessage.__table__.insert(), inbox_rows)

    request.state.audit_target_type = "notice"
    request.state.audit_target_id = notice.id
    request.state.audit_diff = {
        "after": {
            "title": notice.title,
            "target_segment": notice.target_segment,
            "published_at": notice.published_at.isoformat()
            if notice.published_at
            else None,
            "delivered_user_count": len(user_ids),
            "body_length": len(sanitized),
        }
    }
    await db.commit()
    await db.refresh(notice)

    logger.info(
        "admin.notice.created",
        actor_user_id=admin.id,
        notice_id=notice.id,
        target_segment=notice.target_segment,
        delivered_user_count=len(user_ids),
    )

    return NoticeDetailResponse(
        id=notice.id,
        title=notice.title,
        body_html=notice.body_html,
        target_segment=notice.target_segment,
        published_at=notice.published_at,
        created_by_admin_id=notice.created_by_admin_id,
        created_at=notice.created_at,
        delivered_user_count=len(user_ids),
    )


async def delete_notice(
    request: Request, notice_id: int, admin: User, db: AsyncSession
) -> None:
    """쪽지 hard delete — CASCADE로 사용자 inbox에서도 회수.

    잘못 발행한 쪽지를 즉시 철회하기 위한 경로. 정상 운영 흐름은 발행 후 보존.
    """
    notice = (
        await db.execute(select(Notice).where(Notice.id == notice_id))
    ).scalar_one_or_none()
    if notice is None:
        raise HTTPException(
            404,
            detail={
                "code": "NOTICE_NOT_FOUND",
                "message": "해당 쪽지를 찾을 수 없습니다.",
            },
        )

    delivered = (
        await db.execute(
            select(func.count(InboxMessage.id)).where(
                InboxMessage.notice_id == notice_id
            )
        )
    ).scalar_one()

    request.state.audit_target_type = "notice"
    request.state.audit_target_id = notice.id
    request.state.audit_diff = {
        "before": {
            "title": notice.title,
            "target_segment": notice.target_segment,
            "delivered_user_count": int(delivered),
        },
        "after": {"deleted": True},
    }

    await db.execute(delete(Notice).where(Notice.id == notice_id))
    await db.commit()

    logger.info(
        "admin.notice.deleted",
        actor_user_id=admin.id,
        notice_id=notice_id,
        recalled_inbox_count=int(delivered),
    )


async def list_notice_recipients(
    notice_id: int,
    status: str,
    page: int,
    per_page: int,
    admin: User,
    db: AsyncSession,
) -> NoticeRecipientsResponse:
    """쪽지 수신자 목록 — read/unread 분리 페이지네이션.

    counts(read_count, unread_count)는 항상 동봉하므로 UI에서 탭 라벨에 즉시 표기 가능.
    items는 status 파라미터에 해당하는 한쪽만 페이지네이션해서 돌려준다.
    """
    if status not in ("read", "unread"):
        raise HTTPException(
            422,
            detail={
                "code": "INVALID_STATUS",
                "message": "status는 'read' 또는 'unread'여야 합니다.",
            },
        )

    notice = (
        await db.execute(select(Notice).where(Notice.id == notice_id))
    ).scalar_one_or_none()
    if notice is None:
        raise HTTPException(
            404,
            detail={
                "code": "NOTICE_NOT_FOUND",
                "message": "해당 쪽지를 찾을 수 없습니다.",
            },
        )

    counts_row = (
        await db.execute(
            select(
                func.coalesce(
                    func.sum(
                        case((InboxMessage.is_read.is_(True), 1), else_=0)
                    ),
                    0,
                ).label("read_count"),
                func.coalesce(
                    func.sum(
                        case((InboxMessage.is_read.is_(False), 1), else_=0)
                    ),
                    0,
                ).label("unread_count"),
            ).where(InboxMessage.notice_id == notice_id)
        )
    ).one()
    read_count = int(counts_row.read_count)
    unread_count = int(counts_row.unread_count)
    total = read_count if status == "read" else unread_count

    is_read_value = status == "read"
    rows = (
        await db.execute(
            select(
                User.id,
                User.email,
                User.name,
                User.segment,
                InboxMessage.is_read,
                InboxMessage.created_at,
            )
            .join(User, User.id == InboxMessage.user_id)
            .where(
                InboxMessage.notice_id == notice_id,
                InboxMessage.is_read.is_(is_read_value),
            )
            .order_by(User.email.asc(), User.id.asc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
    ).all()

    logger.info(
        "admin.notice.recipients.listed",
        actor_user_id=admin.id,
        notice_id=notice_id,
        status=status,
        page=page,
        per_page=per_page,
        total=total,
    )

    items = [
        NoticeRecipientItem(
            user_id=r.id,
            email=r.email,
            name=r.name,
            segment=r.segment,
            is_read=r.is_read,
            delivered_at=r.created_at,
        )
        for r in rows
    ]
    return NoticeRecipientsResponse(
        items=items,
        page=page,
        per_page=per_page,
        total=total,
        read_count=read_count,
        unread_count=unread_count,
        status=status,  # type: ignore[arg-type]
    )


__all__ = [
    "list_notices",
    "get_notice_detail",
    "list_notice_recipients",
    "create_notice",
    "delete_notice",
]
