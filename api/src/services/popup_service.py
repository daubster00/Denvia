"""팝업 관리 서비스 — Story 7.2 v2 재설계.

CRUD 6 함수 + 이미지 업로드 + 타입별 페이로드 검증 + sanitize + audit_diff + soft delete.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import structlog
from fastapi import HTTPException, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.popup import Popup
from api.src.models.user import User
from api.src.schemas.admin.popup import (
    PopupCreateRequest,
    PopupDetailResponse,
    PopupImageUploadResponse,
    PopupListItem,
    PopupListResponse,
    PopupToggleResponse,
    PopupUpdateRequest,
)
from api.src.utils.html_sanitize import safe_external_url, sanitize_body_html

logger = structlog.get_logger()


# 이미지 업로드 저장 경로 — RAG 패턴 답습.
# api/src/services/ → api/data/uploads/popup_images/
POPUP_IMAGE_DIR = (
    Path(__file__).parent.parent.parent / "data" / "uploads" / "popup_images"
)
POPUP_IMAGE_URL_PREFIX = "/static/popup-images"
_ALLOWED_IMAGE_MIMES = {"image/png", "image/jpeg", "image/webp"}
_ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
_MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


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


def _validate_image_url(image_url: str | None) -> None:
    """업로드된 image_url만 허용 — 외부 URL/path traversal 차단."""
    if image_url is None:
        return
    if not image_url.startswith(POPUP_IMAGE_URL_PREFIX + "/"):
        raise HTTPException(
            422,
            detail={
                "code": "POPUP_IMAGE_URL_INVALID",
                "message": "이미지는 업로드된 파일만 사용할 수 있습니다.",
            },
        )
    # 경로 조작 차단 — 슬래시 다음에 ".." 등이 오는 것을 막는다.
    rel = image_url[len(POPUP_IMAGE_URL_PREFIX) + 1 :]
    if "/" in rel or ".." in rel:
        raise HTTPException(
            422,
            detail={
                "code": "POPUP_IMAGE_URL_INVALID",
                "message": "잘못된 이미지 경로입니다.",
            },
        )


def _normalize_position_payload(req) -> None:
    """display_position == 'custom' 일 때만 px 값을 유지하고, 그 외에는 None 으로 정규화.

    'custom' 인데 px 값이 누락되면 422 로 거절한다(부분 입력 방지).
    in-place 로 req.display_position_top_px / display_position_left_px 를 정리한다.
    """
    if req.display_position == "custom":
        if req.display_position_top_px is None or req.display_position_left_px is None:
            raise HTTPException(
                422,
                detail={
                    "code": "POPUP_POSITION_PX_REQUIRED",
                    "message": "직접 입력 위치는 위/왼쪽 px 값을 모두 입력해주세요.",
                },
            )
    else:
        req.display_position_top_px = None
        req.display_position_left_px = None


def _validate_type_payload(
    popup_type: str, image_url: str | None, body_html: str | None
) -> None:
    if popup_type == "image":
        if not image_url:
            raise HTTPException(
                422,
                detail={
                    "code": "POPUP_IMAGE_REQUIRED",
                    "message": "이미지 타입은 이미지 파일이 필요합니다.",
                },
            )
    elif popup_type == "editor":
        if not body_html or not body_html.strip():
            raise HTTPException(
                422,
                detail={
                    "code": "POPUP_BODY_REQUIRED",
                    "message": "에디터 타입은 본문 내용이 필요합니다.",
                },
            )


async def _fetch_alive_popup(
    popup_id: int, db: AsyncSession, *, lock: bool = False
) -> Popup:
    stmt = select(Popup).where(Popup.id == popup_id, Popup.deleted_at.is_(None))
    if lock:
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
            .order_by(
                Popup.sort_order.asc(),
                Popup.display_start.desc(),
                Popup.id.desc(),
            )
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
    _validate_image_url(req.image_url)
    _validate_type_payload(req.popup_type, req.image_url, req.body_html)
    _normalize_position_payload(req)
    sanitized = sanitize_body_html(req.body_html) if req.body_html else None

    popup = Popup(
        title=req.title,
        body_html=sanitized,
        image_url=req.image_url,
        link_url=req.link_url,
        display_start=req.display_start,
        display_end=req.display_end,
        target_segment=req.target_segment,
        target_device=req.target_device,
        popup_type=req.popup_type,
        display_position=req.display_position,
        display_position_top_px=req.display_position_top_px,
        display_position_left_px=req.display_position_left_px,
        sort_order=req.sort_order,
        is_active=req.is_active,
        created_by_admin_id=admin.id,
    )
    db.add(popup)
    await db.flush()
    request.state.audit_target_type = "popup"
    request.state.audit_target_id = popup.id
    request.state.audit_diff = {
        "after": {
            "title": popup.title,
            "target_segment": popup.target_segment,
            "target_device": popup.target_device,
            "popup_type": popup.popup_type,
            "display_position": popup.display_position,
            "display_position_top_px": popup.display_position_top_px,
            "display_position_left_px": popup.display_position_left_px,
            "sort_order": popup.sort_order,
            "display_start": popup.display_start.isoformat(),
            "display_end": popup.display_end.isoformat(),
            "is_active": popup.is_active,
            "link_url": popup.link_url,
            "image_url": popup.image_url,
            "body_length": len(sanitized) if sanitized else 0,
        }
    }
    await db.commit()
    await db.refresh(popup)
    logger.info(
        "admin.popup.created",
        actor_user_id=admin.id,
        popup_id=popup.id,
        popup_type=popup.popup_type,
        target_device=popup.target_device,
        display_position=popup.display_position,
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
    _validate_image_url(req.image_url)
    _validate_type_payload(req.popup_type, req.image_url, req.body_html)
    _normalize_position_payload(req)

    before = {
        "title": popup.title,
        "target_segment": popup.target_segment,
        "target_device": popup.target_device,
        "popup_type": popup.popup_type,
        "display_position": popup.display_position,
        "display_position_top_px": popup.display_position_top_px,
        "display_position_left_px": popup.display_position_left_px,
        "sort_order": popup.sort_order,
        "display_start": popup.display_start.isoformat(),
        "display_end": popup.display_end.isoformat(),
        "is_active": popup.is_active,
        "link_url": popup.link_url,
        "image_url": popup.image_url,
        "body_length": len(popup.body_html or ""),
    }
    sanitized = sanitize_body_html(req.body_html) if req.body_html else None
    popup.title = req.title
    popup.body_html = sanitized
    popup.image_url = req.image_url
    popup.link_url = req.link_url
    popup.display_start = req.display_start
    popup.display_end = req.display_end
    popup.target_segment = req.target_segment
    popup.target_device = req.target_device
    popup.popup_type = req.popup_type
    popup.display_position = req.display_position
    popup.display_position_top_px = req.display_position_top_px
    popup.display_position_left_px = req.display_position_left_px
    popup.sort_order = req.sort_order
    popup.is_active = req.is_active
    request.state.audit_target_type = "popup"
    request.state.audit_target_id = popup.id
    request.state.audit_diff = {
        "before": before,
        "after": {
            "title": req.title,
            "target_segment": req.target_segment,
            "target_device": req.target_device,
            "popup_type": req.popup_type,
            "display_position": req.display_position,
            "display_position_top_px": req.display_position_top_px,
            "display_position_left_px": req.display_position_left_px,
            "sort_order": req.sort_order,
            "display_start": req.display_start.isoformat(),
            "display_end": req.display_end.isoformat(),
            "is_active": req.is_active,
            "link_url": req.link_url,
            "image_url": req.image_url,
            "body_length": len(sanitized) if sanitized else 0,
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
    popup.is_active = False
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


async def upload_popup_image(
    request: Request,
    file: UploadFile,
    admin: User,
) -> PopupImageUploadResponse:
    """팝업 이미지 multipart 업로드.

    - MIME / 확장자 / 크기 검증
    - uuid4 prefix로 충돌 방지
    - 응답: /static/popup-images/{filename} URL
    """
    # 1) MIME 검증
    if file.content_type not in _ALLOWED_IMAGE_MIMES:
        raise HTTPException(
            422,
            detail={
                "code": "POPUP_IMAGE_MIME_INVALID",
                "message": "PNG·JPG·WEBP 이미지만 업로드할 수 있습니다.",
            },
        )

    # 2) 확장자 검증
    raw_name = file.filename or ""
    ext = Path(raw_name).suffix.lower()
    if ext not in _ALLOWED_IMAGE_EXTS:
        raise HTTPException(
            422,
            detail={
                "code": "POPUP_IMAGE_EXT_INVALID",
                "message": "PNG·JPG·WEBP 확장자만 허용됩니다.",
            },
        )

    # 3) 크기 검증 (스트림 read는 한 번만 — 이후 disk write에 재사용)
    contents = await file.read()
    size = len(contents)
    if size > _MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(
            422,
            detail={
                "code": "POPUP_IMAGE_TOO_LARGE",
                "message": "이미지 크기는 5MB 이하여야 합니다.",
            },
        )

    # 4) 디스크 저장 — uuid prefix로 충돌·열거 차단
    POPUP_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    safe_filename = f"{uuid.uuid4().hex}{ext}"
    dest = POPUP_IMAGE_DIR / safe_filename
    dest.write_bytes(contents)

    image_url = f"{POPUP_IMAGE_URL_PREFIX}/{safe_filename}"

    # 5) audit context — target_id는 아직 없으므로 0(대체용) 또는 None.
    # AuditMiddleware는 target_id 없이도 INSERT한다 (audit_target_type만 있으면 됨).
    request.state.audit_target_type = "popup_image"
    request.state.audit_diff = {
        "after": {
            "filename": safe_filename,
            "original_name": raw_name,
            "size_bytes": size,
            "mime_type": file.content_type,
        }
    }

    logger.info(
        "admin.popup.image_uploaded",
        actor_user_id=admin.id,
        filename=safe_filename,
        size_bytes=size,
        mime_type=file.content_type,
    )

    return PopupImageUploadResponse(
        image_url=image_url,
        size_bytes=size,
        mime_type=file.content_type,
    )


__all__ = [
    "list_popups",
    "get_popup_detail",
    "create_popup",
    "update_popup",
    "toggle_active",
    "delete_popup",
    "upload_popup_image",
    "POPUP_IMAGE_DIR",
    "POPUP_IMAGE_URL_PREFIX",
]
