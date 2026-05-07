"""쪽지함·팝업 서비스 — Story 4.5 + 7.2 v2 재설계.

함수 목록:
- list_inbox(): 쪽지함 페이지네이션 조회 + sanitize
- mark_read(): 단일 쪽지 읽음 처리(멱등)
- get_unread_count(): TopNav 뱃지용 미읽음 개수
- get_active_popups(): 메인 진입 시 노출 후보 배열 조회 (디바이스 필터)
- (제거됨) mark_popup_seen — Story 7.2 v2에서 쪽지함 보관 중단. 노출 추적은 클라이언트 sessionStorage.

권한 경계: 모든 함수가 user_id를 강제 매개변수로 받고 WHERE 절에 항상 포함한다.
"""

from __future__ import annotations

from typing import Literal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.inbox_message import InboxMessage
from api.src.models.popup import Popup
from api.src.models.user import User
from api.src.schemas.inbox import (
    ActivePopupResponse,
    InboxItem,
    InboxListResponse,
    InboxPreviewItem,
    InboxPreviewResponse,
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


async def get_active_popups(
    db: AsyncSession,
    user: User,
    device: Literal["pc", "mobile"],
) -> list[ActivePopupResponse]:
    """메인 진입 시 노출 후보 배열 — Story 7.2 v2.

    조건:
    - is_active=TRUE
    - deleted_at IS NULL
    - display_start <= NOW() <= display_end
    - target_segment 'all' 또는 사용자 segment 일치 (사용자 segment NULL이면 'all'만)
    - target_device 'both' 또는 요청 디바이스 일치

    정렬: sort_order ASC (관리자가 캐러셀 순서 통제), display_start DESC, id DESC.

    노출 1회/세션 + '오늘 안보기' 필터는 클라이언트에서 처리한다 (sessionStorage / localStorage).
    """
    segment_match: list = [Popup.target_segment == "all"]
    if user.segment is not None:
        segment_match.append(Popup.target_segment == user.segment)

    device_match = or_(
        Popup.target_device == "both",
        Popup.target_device == device,
    )

    stmt = (
        select(Popup)
        .where(
            Popup.is_active.is_(True),
            Popup.deleted_at.is_(None),
            Popup.display_start <= func.now(),
            Popup.display_end >= func.now(),
            or_(*segment_match),
            device_match,
        )
        .order_by(
            Popup.sort_order.asc(),
            Popup.display_start.desc(),
            Popup.id.desc(),
        )
    )

    rows = (await db.execute(stmt)).scalars().all()
    return [
        ActivePopupResponse(
            popup_id=p.id,
            title=p.title,
            popup_type=p.popup_type,
            image_url=p.image_url,
            body_html_safe=(
                sanitize_body_html(p.body_html) if p.body_html else None
            ),
            link_url=safe_external_url(p.link_url),
            display_end=p.display_end.isoformat(),
        )
        for p in rows
    ]


async def get_preview_messages(
    db: AsyncSession, user_id: int, max_count: int
) -> InboxPreviewResponse:
    """쪽지함 미리보기 — 미읽음 우선·최신순 N건.

    드롭다운용 경량 페이로드 (body_html 제외). 미읽음이 부족하면 읽은 쪽지로 채운다
    (운영 초기에 보낸 쪽지가 있어도 신규 사용자가 빈 미리보기를 보지 않게).
    """
    rows = (
        await db.execute(
            select(InboxMessage)
            .where(InboxMessage.user_id == user_id)
            .order_by(
                InboxMessage.is_read.asc(),  # FALSE(0)가 먼저 → 미읽음 우선
                InboxMessage.created_at.desc(),
                InboxMessage.id.desc(),
            )
            .limit(max_count)
        )
    ).scalars().all()

    items = [
        InboxPreviewItem(
            message_id=r.id,
            type=r.type,
            title=r.title,
            is_read=r.is_read,
            created_at=r.created_at.isoformat(),
        )
        for r in rows
    ]
    return InboxPreviewResponse(items=items, max_count=max_count)


__all__ = [
    "list_inbox",
    "mark_read",
    "get_unread_count",
    "get_active_popups",
    "get_preview_messages",
]
