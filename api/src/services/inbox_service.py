"""쪽지함·팝업 서비스 — Story 4.5.

함수 목록:
- list_inbox(): 쪽지함 페이지네이션 조회 + sanitize
- mark_read(): 단일 쪽지 읽음 처리(멱등)
- get_unread_count(): TopNav 뱃지용 미읽음 개수
- get_active_popup(): 메인 진입 시 노출 후보 1건 조회
- mark_popup_seen(): 팝업 X/ESC 클릭 → inbox UPSERT (seen_popup_at = NOW())

권한 경계: 모든 함수가 user_id를 강제 매개변수로 받고 WHERE 절에 항상 포함한다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.inbox_message import InboxMessage
from api.src.models.popup import Popup
from api.src.models.user import User
from api.src.schemas.inbox import (
    ActivePopupResponse,
    InboxItem,
    InboxListResponse,
)
from api.src.utils.html_sanitize import safe_external_url, sanitize_body_html


async def list_inbox(
    db: AsyncSession,
    user_id: int,
    page: int,
    per_page: int,
    filter_unread: bool,
) -> InboxListResponse:
    """쪽지함 페이지네이션 조회 + body_html sanitize 적용."""
    base_filter = [InboxMessage.user_id == user_id]
    if filter_unread:
        base_filter.append(InboxMessage.is_read.is_(False))

    total = (
        await db.execute(
            select(func.count(InboxMessage.id)).where(*base_filter)
        )
    ).scalar_one()

    unread_count = (
        await db.execute(
            select(func.count(InboxMessage.id))
            .where(InboxMessage.user_id == user_id)
            .where(InboxMessage.is_read.is_(False))
        )
    ).scalar_one()

    rows = (
        await db.execute(
            select(InboxMessage)
            .where(*base_filter)
            .order_by(InboxMessage.created_at.desc(), InboxMessage.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
    ).scalars().all()

    items = [
        InboxItem(
            message_id=r.id,
            type=r.type,
            title=r.title,
            body_html_safe=sanitize_body_html(r.body_html),
            is_read=r.is_read,
            created_at=r.created_at.isoformat(),
            notice_id=r.notice_id,
            popup_id=r.popup_id,
        )
        for r in rows
    ]
    return InboxListResponse(
        items=items,
        page=page,
        per_page=per_page,
        total=int(total),
        unread_count=int(unread_count),
    )


async def mark_read(
    db: AsyncSession, user_id: int, message_id: int
) -> bool | None:
    """본인 쪽지를 읽음 처리한다.

    Returns:
        True  — 이미 읽음(멱등 케이스)
        False — 미읽음 → 읽음으로 전환
        None  — 본인 row 아님 또는 미존재(404 분기용)
    """
    row = (
        await db.execute(
            select(InboxMessage).where(
                InboxMessage.id == message_id,
                InboxMessage.user_id == user_id,
            )
        )
    ).scalar_one_or_none()

    if row is None:
        return None

    was_already_read = bool(row.is_read)
    if not was_already_read:
        row.is_read = True
        await db.commit()
    return was_already_read


async def get_unread_count(db: AsyncSession, user_id: int) -> int:
    """TopNav 뱃지용 미읽음 개수."""
    return int(
        (
            await db.execute(
                select(func.count(InboxMessage.id))
                .where(InboxMessage.user_id == user_id)
                .where(InboxMessage.is_read.is_(False))
            )
        ).scalar_one()
    )


async def get_active_popup(
    db: AsyncSession, user: User
) -> ActivePopupResponse | None:
    """메인 진입 시 자동 노출 후보 1건.

    조건: is_active=TRUE AND display_window 내 AND target_segment 매칭 AND
          (사용자가 아직 X 클릭 안 했음 = inbox_messages.seen_popup_at IS NULL)

    target_segment 매칭: 'all' 또는 사용자 segment.
    사용자 segment IS NULL이면 'all' 타깃만 매칭.
    """
    segment_match: list = [Popup.target_segment == "all"]
    if user.segment is not None:
        segment_match.append(Popup.target_segment == user.segment)

    seen_subq = (
        select(InboxMessage.popup_id)
        .where(
            InboxMessage.user_id == user.id,
            InboxMessage.popup_id.is_not(None),
            InboxMessage.seen_popup_at.is_not(None),
        )
        .scalar_subquery()
    )

    stmt = (
        select(Popup)
        .where(
            Popup.is_active.is_(True),
            Popup.display_start <= func.now(),
            Popup.display_end >= func.now(),
            or_(*segment_match),
            Popup.id.notin_(seen_subq),
        )
        .order_by(Popup.display_start.desc(), Popup.id.desc())
        .limit(1)
    )

    popup = (await db.execute(stmt)).scalar_one_or_none()
    if popup is None:
        return None

    return ActivePopupResponse(
        popup_id=popup.id,
        title=popup.title,
        body_html_safe=sanitize_body_html(popup.body_html),
        link_url=safe_external_url(popup.link_url),
        display_end=popup.display_end.isoformat(),
    )


async def mark_popup_seen(
    db: AsyncSession, user_id: int, popup_id: int
) -> Literal["inserted", "updated", "not_found"]:
    """팝업 X/ESC 클릭 시 inbox_messages UPSERT.

    partial UNIQUE(uniq_inbox_user_popup)에 의해 사용자×팝업 1행 보장.

    Returns:
        "inserted" — 신규 삽입(첫 노출)
        "updated"  — 기존 행 seen_popup_at 갱신(재노출)
        "not_found" — popup_id 미존재 또는 is_active=false
    """
    popup = (
        await db.execute(
            select(Popup).where(Popup.id == popup_id, Popup.is_active.is_(True))
        )
    ).scalar_one_or_none()
    if popup is None:
        return "not_found"

    stmt = (
        pg_insert(InboxMessage)
        .values(
            user_id=user_id,
            notice_id=None,
            popup_id=popup.id,
            type="notice",
            title=popup.title,
            body_html=popup.body_html,
            is_read=True,
            seen_popup_at=func.now(),
        )
        .on_conflict_do_update(
            index_elements=["user_id", "popup_id"],
            index_where=InboxMessage.popup_id.is_not(None),
            set_={"seen_popup_at": func.now()},
        )
        .returning(InboxMessage.id, InboxMessage.created_at)
    )
    # SQLAlchemy/psycopg returns (id, created_at). 신규 INSERT vs UPDATE 분기는
    # ON CONFLICT 시 created_at은 보존되므로 행 존재 여부를 사전 SELECT로 판정한다.
    pre_existing = (
        await db.execute(
            select(InboxMessage.id).where(
                InboxMessage.user_id == user_id,
                InboxMessage.popup_id == popup.id,
            )
        )
    ).scalar_one_or_none()

    await db.execute(stmt)
    await db.commit()

    return "updated" if pre_existing is not None else "inserted"


__all__ = [
    "list_inbox",
    "mark_read",
    "get_unread_count",
    "get_active_popup",
    "mark_popup_seen",
]
