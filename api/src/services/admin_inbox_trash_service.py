"""CS · 휴지통(쪽지) 관리 서비스.

사용자가 본인 쪽지함에서 삭제(soft delete)한 inbox_messages 행을 관리자가
조회·복구·영구삭제한다.

함수 목록:
- list_trash(): deleted_at IS NOT NULL 페이지네이션 + 사용자 정보 join
- get_trash_detail(): 단건 상세 + body_html sanitize
- restore_message(): deleted_at = NULL (원래 사용자 쪽지함으로 복귀)
- hard_delete_message(): DB row DELETE (30일 대기 없이 즉시 영구 삭제)

retention 규약: ``permanent_purge_at = deleted_at + 30 days``. 동일한 컷오프를
배치 ``retention_tasks.purge_old_inbox_messages`` 가 사용한다.

권한 경계: 모든 함수가 admin User를 요구한다(라우터 ``require_admin`` 가드 + 본
모듈은 단순 데이터 접근). 자동 발송된 ``type='system'`` 등도 동일 정책으로 다룬다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import structlog
from fastapi import HTTPException, Request
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.inbox_message import InboxMessage
from api.src.models.user import User
from api.src.schemas.admin.inbox_trash import (
    TrashDetailResponse,
    TrashListItem,
    TrashListResponse,
)
from api.src.services.budget_service import KST
from api.src.utils.html_sanitize import sanitize_body_html

logger = structlog.get_logger()

# retention_tasks.purge_old_inbox_messages 의 컷오프와 동일해야 함.
RETENTION_DAYS = 30


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


async def list_trash(
    page: int,
    per_page: int,
    admin: User,
    db: AsyncSession,
    *,
    email: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> TrashListResponse:
    """휴지통 목록 — 사용자별 삭제일 desc.

    필터:
    - ``email``: User.email 부분 일치 (대소문자 무시). 빈 문자열은 무시.
    - ``date_from``/``date_to``: deleted_at 을 KST 자정~다음날 자정 윈도우로
      걸러낸다. 한쪽만 들어오면 해당 경계만 적용.
    """
    base_filter: list = [InboxMessage.deleted_at.is_not(None)]

    if email:
        needle = email.strip()
        if needle:
            base_filter.append(User.email.ilike(f"%{needle}%"))

    start, end_excl = _kst_window(date_from, date_to)
    if start is not None:
        base_filter.append(InboxMessage.deleted_at >= start)
    if end_excl is not None:
        base_filter.append(InboxMessage.deleted_at < end_excl)

    total = int(
        (
            await db.execute(
                select(func.count(InboxMessage.id))
                .join(User, User.id == InboxMessage.user_id)
                .where(*base_filter)
            )
        ).scalar_one()
    )

    rows = (
        await db.execute(
            select(
                InboxMessage.id,
                InboxMessage.type,
                InboxMessage.title,
                InboxMessage.user_id,
                InboxMessage.created_at,
                InboxMessage.deleted_at,
                User.email.label("user_email"),
                User.name.label("user_name"),
            )
            .join(User, User.id == InboxMessage.user_id)
            .where(*base_filter)
            .order_by(InboxMessage.deleted_at.desc(), InboxMessage.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
    ).all()

    items = [
        TrashListItem(
            message_id=r.id,
            type=r.type,
            title=r.title,
            user_id=r.user_id,
            user_email=r.user_email,
            user_name=r.user_name,
            created_at=r.created_at,
            deleted_at=r.deleted_at,
            permanent_purge_at=r.deleted_at + timedelta(days=RETENTION_DAYS),
        )
        for r in rows
    ]

    logger.info(
        "admin.inbox_trash.listed",
        actor_user_id=admin.id,
        page=page,
        per_page=per_page,
        total=total,
        filter_email=bool(email),
        filter_date_from=date_from.isoformat() if date_from else None,
        filter_date_to=date_to.isoformat() if date_to else None,
    )

    return TrashListResponse(
        items=items, page=page, per_page=per_page, total=total
    )


async def _get_trashed_row(
    db: AsyncSession, message_id: int
) -> tuple[InboxMessage, User]:
    """휴지통 단건 + 사용자 fetch. 미존재/미삭제이면 404."""
    row = (
        await db.execute(
            select(InboxMessage, User)
            .join(User, User.id == InboxMessage.user_id)
            .where(
                InboxMessage.id == message_id,
                InboxMessage.deleted_at.is_not(None),
            )
        )
    ).first()
    if row is None:
        raise HTTPException(
            404,
            detail={
                "code": "TRASH_NOT_FOUND",
                "message": "해당 쪽지를 휴지통에서 찾을 수 없습니다.",
            },
        )
    return row[0], row[1]


async def get_trash_detail(
    message_id: int, admin: User, db: AsyncSession
) -> TrashDetailResponse:
    msg, user = await _get_trashed_row(db, message_id)

    logger.info(
        "admin.inbox_trash.viewed",
        actor_user_id=admin.id,
        message_id=msg.id,
        owner_user_id=msg.user_id,
    )

    # deleted_at 은 _get_trashed_row 필터로 NULL 아님이 보장된다.
    assert msg.deleted_at is not None
    return TrashDetailResponse(
        message_id=msg.id,
        type=msg.type,
        title=msg.title,
        body_html_safe=sanitize_body_html(msg.body_html),
        user_id=msg.user_id,
        user_email=user.email,
        user_name=user.name,
        is_read=msg.is_read,
        created_at=msg.created_at,
        deleted_at=msg.deleted_at,
        permanent_purge_at=msg.deleted_at + timedelta(days=RETENTION_DAYS),
        created_by_admin_id=msg.created_by_admin_id,
    )


async def restore_message(
    request: Request, message_id: int, admin: User, db: AsyncSession
) -> TrashDetailResponse:
    """휴지통 → 원래 사용자의 쪽지함으로 복구 (deleted_at = NULL)."""
    msg, user = await _get_trashed_row(db, message_id)
    before_deleted_at = msg.deleted_at

    msg.deleted_at = None
    await db.commit()
    await db.refresh(msg)

    request.state.audit_target_type = "inbox_message"
    request.state.audit_target_id = msg.id
    request.state.audit_diff = {
        "before": {
            "deleted_at": before_deleted_at.isoformat()
            if before_deleted_at
            else None
        },
        "after": {"deleted_at": None},
        "owner_user_id": msg.user_id,
        "title": msg.title,
    }

    logger.info(
        "admin.inbox_trash.restored",
        actor_user_id=admin.id,
        message_id=msg.id,
        owner_user_id=msg.user_id,
    )

    return TrashDetailResponse(
        message_id=msg.id,
        type=msg.type,
        title=msg.title,
        body_html_safe=sanitize_body_html(msg.body_html),
        user_id=msg.user_id,
        user_email=user.email,
        user_name=user.name,
        is_read=msg.is_read,
        created_at=msg.created_at,
        # 복구 직후라 deleted_at 은 NULL — 응답에서는 직전 시각을 그대로 노출해
        # 클라이언트 라우팅 직전 토스트 표기 등에 활용한다.
        deleted_at=before_deleted_at,  # type: ignore[arg-type]
        permanent_purge_at=before_deleted_at + timedelta(days=RETENTION_DAYS),  # type: ignore[operator]
        created_by_admin_id=msg.created_by_admin_id,
    )


async def hard_delete_message(
    request: Request, message_id: int, admin: User, db: AsyncSession
) -> None:
    """휴지통 row 즉시 DELETE — 30일 대기 없이 영구 삭제."""
    msg, _ = await _get_trashed_row(db, message_id)

    request.state.audit_target_type = "inbox_message"
    request.state.audit_target_id = msg.id
    request.state.audit_diff = {
        "before": {
            "title": msg.title,
            "type": msg.type,
            "owner_user_id": msg.user_id,
            "deleted_at": msg.deleted_at.isoformat() if msg.deleted_at else None,
        },
        "after": {"purged": True},
    }

    await db.execute(delete(InboxMessage).where(InboxMessage.id == msg.id))
    await db.commit()

    logger.info(
        "admin.inbox_trash.hard_deleted",
        actor_user_id=admin.id,
        message_id=message_id,
        owner_user_id=msg.user_id,
    )


__all__ = [
    "RETENTION_DAYS",
    "list_trash",
    "get_trash_detail",
    "restore_message",
    "hard_delete_message",
]
