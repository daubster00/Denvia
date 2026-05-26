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
from sqlalchemy import String, case, cast, delete, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.inbox_message import InboxMessage
from api.src.models.notice import Notice
from api.src.models.user import User
from api.src.schemas.admin.notice import (
    AdminDMDetailResponse,
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
    page: int,
    per_page: int,
    admin: User,
    db: AsyncSession,
    target_filter: str = "all",
) -> NoticeListResponse:
    """전체/세그먼트 broadcast(notices) + 1:1 쪽지(admin_dm inbox_messages)를
    UNION ALL로 합쳐 created_at desc 순으로 페이지네이션한다.

    target_filter:
      - "all"       : 둘 다 (기본)
      - "broadcast" : 전체/세그먼트 공지만
      - "dm"        : 특정 사용자 쪽지만
    """
    include_broadcast = target_filter in ("all", "broadcast")
    include_dm = target_filter in ("all", "dm")

    broadcast_count = 0
    if include_broadcast:
        broadcast_count = int(
            (
                await db.execute(select(func.count(Notice.id)))
            ).scalar_one()
        )

    dm_count = 0
    if include_dm:
        dm_count = int(
            (
                await db.execute(
                    select(func.count(InboxMessage.id)).where(
                        InboxMessage.type == "admin_dm"
                    )
                )
            ).scalar_one()
        )

    total = broadcast_count + dm_count

    delivered_sq = _delivered_count_subq()

    notice_select = (
        select(
            literal("notice").label("item_type"),
            Notice.id.label("id"),
            Notice.title.label("title"),
            cast(Notice.target_segment, String).label("target_segment"),
            cast(literal(None), String).label("target_user_email"),
            cast(literal(None), Notice.id.type).label("target_user_id"),
            Notice.published_at.label("published_at"),
            Notice.created_by_admin_id.label("created_by_admin_id"),
            Notice.created_at.label("created_at"),
            func.coalesce(delivered_sq.c.delivered, 0).label("delivered"),
        )
        .outerjoin(delivered_sq, delivered_sq.c.notice_id == Notice.id)
    )

    dm_select = (
        select(
            literal("admin_dm").label("item_type"),
            InboxMessage.id.label("id"),
            InboxMessage.title.label("title"),
            cast(literal(None), String).label("target_segment"),
            User.email.label("target_user_email"),
            InboxMessage.user_id.label("target_user_id"),
            InboxMessage.created_at.label("published_at"),
            InboxMessage.created_by_admin_id.label("created_by_admin_id"),
            InboxMessage.created_at.label("created_at"),
            literal(1).label("delivered"),
        )
        .join(User, User.id == InboxMessage.user_id)
        .where(InboxMessage.type == "admin_dm")
    )

    if include_broadcast and include_dm:
        unified = notice_select.union_all(dm_select).subquery()
    elif include_broadcast:
        unified = notice_select.subquery()
    else:
        unified = dm_select.subquery()

    rows = (
        await db.execute(
            select(unified)
            .order_by(unified.c.created_at.desc(), unified.c.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
    ).all()

    logger.info(
        "admin.notices.listed",
        actor_user_id=admin.id,
        page=page,
        per_page=per_page,
        total=total,
        target_filter=target_filter,
    )

    items = [
        NoticeListItem(
            item_type=r.item_type,
            id=int(r.id),
            title=r.title,
            target_segment=r.target_segment,
            target_user_id=int(r.target_user_id) if r.target_user_id is not None else None,
            target_user_email=r.target_user_email,
            published_at=r.published_at,
            created_by_admin_id=r.created_by_admin_id,
            created_at=r.created_at,
            delivered_user_count=int(r.delivered),
        )
        for r in rows
    ]
    return NoticeListResponse(
        items=items, page=page, per_page=per_page, total=total
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


async def get_admin_dm_detail(
    message_id: int, admin: User, db: AsyncSession
) -> AdminDMDetailResponse:
    """관리자 1:1 쪽지 단건 — inbox_messages.id 기준. 받는 사용자 이메일 동봉.

    type='admin_dm' 가 아니면 404. 사용자 본인이 휴지통에 넣어도(deleted_at NOT NULL)
    관리자 상세는 계속 열람 가능(회수 이력 표시용).
    """
    row = (
        await db.execute(
            select(InboxMessage, User.email, User.name)
            .join(User, User.id == InboxMessage.user_id)
            .where(
                InboxMessage.id == message_id,
                InboxMessage.type == "admin_dm",
            )
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(
            404,
            detail={
                "code": "ADMIN_DM_NOT_FOUND",
                "message": "해당 쪽지를 찾을 수 없습니다.",
            },
        )
    msg, user_email, user_name = row

    logger.info(
        "admin.dm.viewed",
        actor_user_id=admin.id,
        message_id=msg.id,
        target_user_id=msg.user_id,
    )
    return AdminDMDetailResponse(
        id=msg.id,
        title=msg.title,
        body_html=msg.body_html,
        target_user_id=msg.user_id,
        target_user_email=user_email,
        target_user_name=user_name,
        is_read=msg.is_read,
        created_by_admin_id=msg.created_by_admin_id,
        created_at=msg.created_at,
        deleted_at=msg.deleted_at,
    )


async def delete_admin_dm(
    request: Request, message_id: int, admin: User, db: AsyncSession
) -> None:
    """관리자 1:1 쪽지 hard delete — 사용자 쪽지함에서도 즉시 회수.

    type='admin_dm' 행에만 동작. 공지 fan-out 행은 절대 건드리지 않는다.
    """
    msg = (
        await db.execute(
            select(InboxMessage).where(
                InboxMessage.id == message_id,
                InboxMessage.type == "admin_dm",
            )
        )
    ).scalar_one_or_none()
    if msg is None:
        raise HTTPException(
            404,
            detail={
                "code": "ADMIN_DM_NOT_FOUND",
                "message": "해당 쪽지를 찾을 수 없습니다.",
            },
        )

    request.state.audit_target_type = "inbox_message"
    request.state.audit_target_id = msg.id
    request.state.audit_diff = {
        "before": {
            "target_user_id": msg.user_id,
            "title": msg.title,
            "is_read": msg.is_read,
        },
        "after": {"deleted": True},
    }

    await db.execute(
        delete(InboxMessage).where(
            InboxMessage.id == message_id,
            InboxMessage.type == "admin_dm",
        )
    )
    await db.commit()

    logger.info(
        "admin.dm.deleted",
        actor_user_id=admin.id,
        message_id=message_id,
        target_user_id=msg.user_id,
    )


__all__ = [
    "list_notices",
    "get_notice_detail",
    "list_notice_recipients",
    "create_notice",
    "delete_notice",
    "get_admin_dm_detail",
    "delete_admin_dm",
]
