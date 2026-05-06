"""팝업 관리 서비스 — Story 7.2.

CRUD 6 함수 + sanitize 적용 + audit_diff 채움 + soft delete.
사용자 측 노출 경로(`inbox_service.get_active_popup`)에서 deleted_at IS NULL
필터를 추가했지만, 본 서비스도 모든 SELECT/UPDATE/DELETE에서 deleted_at NULL
조건을 강제해 admin 화면에서 잘못된 행 노출을 막는다.
"""

from __future__ import annotations

from datetime import datetime, timezone

import structlog
from fastapi import HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.popup import Popup
from api.src.models.user import User
from api.src.schemas.admin.popup import (
    PopupCreateRequest,
    PopupDetailResponse,
    PopupListItem,
    PopupListResponse,
    PopupToggleResponse,
    PopupUpdateRequest,
)
from api.src.utils.html_sanitize import safe_external_url, sanitize_body_html

logger = structlog.get_logger()


def _validate_link_url(link_url: str | None) -> None:
    if link_url and safe_external_url(link_url) is None:
        raise HTTPException(
            422,
            detail={
                "code": "POPUP_LINK_URL_INVALID",
                "message": "http:// 또는 https://로 시작하는 URL을 입력해주세요.",
            },
        )


def _normalize_aware(dt: datetime) -> datetime:
    """naive datetime은 UTC로 가정해 aware로 보정. mixed naive/aware 비교 TypeError 차단."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _validate_display_range(start: datetime, end: datetime) -> None:
    if _normalize_aware(end) <= _normalize_aware(start):
        raise HTTPException(
            422,
            detail={
                "code": "POPUP_DISPLAY_RANGE_INVALID",
                "message": "종료일은 시작일보다 늦어야 합니다.",
            },
        )


async def _fetch_alive_popup(
    popup_id: int, db: AsyncSession, *, lock: bool = False
) -> Popup:
    stmt = select(Popup).where(Popup.id == popup_id, Popup.deleted_at.is_(None))
    if lock:
        # AC-6: 동시 토글/편집/삭제 race 차단을 위한 row-level lock.
        stmt = stmt.with_for_update()
    popup = (await db.execute(stmt)).scalar_one_or_none()
    if popup is None:
        raise HTTPException(
            404,
            detail={
                "code": "POPUP_NOT_FOUND",
                "message": "해당 팝업을 찾을 수 없습니다.",
            },
        )
    return popup


async def list_popups(
    page: int, per_page: int, admin: User, db: AsyncSession
) -> PopupListResponse:
    base_filter = [Popup.deleted_at.is_(None)]
    total = (
        await db.execute(select(func.count(Popup.id)).where(*base_filter))
    ).scalar_one()
    rows = (
        await db.execute(
            select(Popup)
            .where(*base_filter)
            .order_by(Popup.display_start.desc(), Popup.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
    ).scalars().all()
    logger.info(
        "admin.popups.listed",
        actor_user_id=admin.id,
        page=page,
        per_page=per_page,
        total=int(total),
    )
    return PopupListResponse(
        items=[PopupListItem.model_validate(r) for r in rows],
        page=page,
        per_page=per_page,
        total=int(total),
    )


async def get_popup_detail(
    popup_id: int, admin: User, db: AsyncSession
) -> PopupDetailResponse:
    popup = await _fetch_alive_popup(popup_id, db)
    logger.info(
        "admin.popup.viewed",
        actor_user_id=admin.id,
        popup_id=popup.id,
    )
    return PopupDetailResponse.model_validate(popup)


async def create_popup(
    request: Request,
    req: PopupCreateRequest,
    admin: User,
    db: AsyncSession,
) -> PopupDetailResponse:
    _validate_display_range(req.display_start, req.display_end)
    _validate_link_url(req.link_url)
    sanitized = sanitize_body_html(req.body_html)

    popup = Popup(
        title=req.title,
        body_html=sanitized,
        link_url=req.link_url,
        display_start=req.display_start,
        display_end=req.display_end,
        target_segment=req.target_segment,
        is_active=req.is_active,
        created_by_admin_id=admin.id,
    )
    db.add(popup)
    await db.flush()  # popup.id 확보
    # audit context는 commit 이전에 세팅 — logger 예외로 인한 audit 누락 차단.
    request.state.audit_target_type = "popup"
    request.state.audit_target_id = popup.id
    request.state.audit_diff = {
        "after": {
            "title": popup.title,
            "target_segment": popup.target_segment,
            "display_start": popup.display_start.isoformat(),
            "display_end": popup.display_end.isoformat(),
            "is_active": popup.is_active,
            "link_url": popup.link_url,
            "body_length": len(sanitized),
        }
    }
    await db.commit()
    await db.refresh(popup)
    logger.info(
        "admin.popup.created",
        actor_user_id=admin.id,
        popup_id=popup.id,
        title=popup.title,
    )
    return PopupDetailResponse.model_validate(popup)


async def update_popup(
    request: Request,
    popup_id: int,
    req: PopupUpdateRequest,
    admin: User,
    db: AsyncSession,
) -> PopupDetailResponse:
    popup = await _fetch_alive_popup(popup_id, db, lock=True)
    _validate_display_range(req.display_start, req.display_end)
    _validate_link_url(req.link_url)

    before = {
        "title": popup.title,
        "target_segment": popup.target_segment,
        "display_start": popup.display_start.isoformat(),
        "display_end": popup.display_end.isoformat(),
        "is_active": popup.is_active,
        "link_url": popup.link_url,
        "body_length": len(popup.body_html or ""),
    }
    sanitized = sanitize_body_html(req.body_html)
    popup.title = req.title
    popup.body_html = sanitized
    popup.link_url = req.link_url
    popup.display_start = req.display_start
    popup.display_end = req.display_end
    popup.target_segment = req.target_segment
    popup.is_active = req.is_active
    # updated_at은 ORM onupdate=func.now()로 자동 갱신됨.
    # audit context는 commit 이전에 세팅.
    request.state.audit_target_type = "popup"
    request.state.audit_target_id = popup.id
    request.state.audit_diff = {
        "before": before,
        "after": {
            "title": req.title,
            "target_segment": req.target_segment,
            "display_start": req.display_start.isoformat(),
            "display_end": req.display_end.isoformat(),
            "is_active": req.is_active,
            "link_url": req.link_url,
            "body_length": len(sanitized),
        },
    }
    await db.commit()
    await db.refresh(popup)
    logger.info(
        "admin.popup.updated",
        actor_user_id=admin.id,
        popup_id=popup.id,
    )
    return PopupDetailResponse.model_validate(popup)


async def toggle_active(
    request: Request,
    popup_id: int,
    is_active: bool,
    admin: User,
    db: AsyncSession,
) -> PopupToggleResponse:
    popup = await _fetch_alive_popup(popup_id, db, lock=True)
    before = popup.is_active
    popup.is_active = is_active
    # updated_at은 ORM onupdate=func.now()로 자동 갱신됨.
    # audit context는 commit 이전에 세팅.
    request.state.audit_target_type = "popup"
    request.state.audit_target_id = popup.id
    request.state.audit_diff = {
        "before": {"is_active": before},
        "after": {"is_active": is_active},
    }
    await db.commit()
    await db.refresh(popup)
    logger.info(
        "admin.popup.toggled",
        actor_user_id=admin.id,
        popup_id=popup.id,
        before=before,
        after=is_active,
    )
    return PopupToggleResponse(
        id=popup.id, is_active=is_active, updated_at=popup.updated_at
    )


async def delete_popup(
    request: Request, popup_id: int, admin: User, db: AsyncSession
) -> None:
    popup = await _fetch_alive_popup(popup_id, db, lock=True)
    before = {"title": popup.title, "is_active": popup.is_active}
    popup.deleted_at = func.now()
    # updated_at은 ORM onupdate=func.now()로 자동 갱신됨.
    popup.is_active = False
    # audit context는 commit 이전에 세팅 — popup.id로 일관성 유지.
    request.state.audit_target_type = "popup"
    request.state.audit_target_id = popup.id
    request.state.audit_diff = {
        "before": before,
        "after": {"deleted_at": "now"},
    }
    await db.commit()
    logger.info(
        "admin.popup.deleted",
        actor_user_id=admin.id,
        popup_id=popup.id,
    )


__all__ = [
    "list_popups",
    "get_popup_detail",
    "create_popup",
    "update_popup",
    "toggle_active",
    "delete_popup",
]
