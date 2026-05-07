"""api/src/services/popup_service 단위 테스트 — Story 7.2."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from api.src.models.popup import Popup
from api.src.schemas.admin.popup import (
    PopupCreateRequest,
    PopupUpdateRequest,
)
from api.src.services import popup_service


# ──────────────────────────────────────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────────────────────────────────────


def _admin_mock(user_id: int = 99):
    admin = MagicMock()
    admin.id = user_id
    return admin


def _request_mock():
    req = MagicMock()
    req.state = MagicMock()
    return req


def _popup_row(
    *,
    popup_id: int = 1,
    title: str = "5월 프로모션",
    body_html: str | None = "<p>안녕</p>",
    image_url: str | None = None,
    link_url: str | None = "https://example.com",
    target_segment: str = "all",
    target_device: str = "both",
    popup_type: str = "editor",
    sort_order: int = 0,
    is_active: bool = True,
    deleted_at: datetime | None = None,
    created_by_admin_id: int = 1,
):
    now = datetime(2026, 5, 1, tzinfo=timezone.utc)
    popup = MagicMock(spec=Popup)
    popup.id = popup_id
    popup.title = title
    popup.body_html = body_html
    popup.image_url = image_url
    popup.link_url = link_url
    popup.display_start = now
    popup.display_end = now + timedelta(days=7)
    popup.target_segment = target_segment
    popup.target_device = target_device
    popup.popup_type = popup_type
    popup.sort_order = sort_order
    popup.is_active = is_active
    popup.deleted_at = deleted_at
    popup.created_at = now
    popup.updated_at = now
    popup.created_by_admin_id = created_by_admin_id
    return popup


def _make_create_request(
    *,
    title: str = "5월 프로모션",
    body_html: str | None = "<p>안녕</p>",
    image_url: str | None = None,
    link_url: str | None = "https://example.com/promo",
    is_active: bool = True,
    target_segment: str = "all",
    target_device: str = "both",
    popup_type: str = "editor",
    sort_order: int = 0,
    days_offset: int = 7,
) -> PopupCreateRequest:
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    return PopupCreateRequest(
        title=title,
        body_html=body_html,
        image_url=image_url,
        link_url=link_url,
        display_start=start,
        display_end=start + timedelta(days=days_offset),
        target_segment=target_segment,
        target_device=target_device,
        popup_type=popup_type,
        sort_order=sort_order,
        is_active=is_active,
    )


# ──────────────────────────────────────────────────────────────────────────────
# list_popups
# ──────────────────────────────────────────────────────────────────────────────


class TestListPopups:
    async def test_returns_flat_pagination(self):
        rows = [_popup_row(popup_id=i) for i in (10, 11)]

        count_result = MagicMock()
        count_result.scalar_one = MagicMock(return_value=2)
        rows_result = MagicMock()
        rows_result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=rows))
        )

        db = MagicMock()
        db.execute = AsyncMock(side_effect=[count_result, rows_result])

        admin = _admin_mock()
        out = await popup_service.list_popups(
            page=1, per_page=20, admin=admin, db=db
        )
        assert out.page == 1
        assert out.per_page == 20
        assert out.total == 2
        assert len(out.items) == 2


# ──────────────────────────────────────────────────────────────────────────────
# get_popup_detail
# ──────────────────────────────────────────────────────────────────────────────


class TestGetPopupDetail:
    async def test_returns_detail_for_alive_popup(self):
        popup = _popup_row()
        select_result = MagicMock()
        select_result.scalar_one_or_none = MagicMock(return_value=popup)
        db = MagicMock()
        db.execute = AsyncMock(return_value=select_result)

        admin = _admin_mock()
        out = await popup_service.get_popup_detail(popup.id, admin, db)
        assert out.id == popup.id
        assert out.body_html == popup.body_html

    async def test_404_when_missing(self):
        select_result = MagicMock()
        select_result.scalar_one_or_none = MagicMock(return_value=None)
        db = MagicMock()
        db.execute = AsyncMock(return_value=select_result)

        admin = _admin_mock()
        with pytest.raises(HTTPException) as exc:
            await popup_service.get_popup_detail(999, admin, db)
        assert exc.value.status_code == 404
        assert exc.value.detail["code"] == "POPUP_NOT_FOUND"


# ──────────────────────────────────────────────────────────────────────────────
# create_popup
# ──────────────────────────────────────────────────────────────────────────────


class TestCreatePopup:
    async def test_create_sanitizes_body_and_sets_audit_after(self):
        admin = _admin_mock(user_id=99)
        request = _request_mock()
        req = _make_create_request(
            body_html='<p>안녕</p><script>alert(1)</script>'
        )

        captured: list = []

        def _refresh(obj):
            obj.id = 555
            obj.created_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
            obj.updated_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
            return None

        db = MagicMock()
        db.add = MagicMock(side_effect=lambda obj: captured.append(obj))
        db.commit = AsyncMock()
        db.refresh = AsyncMock(side_effect=_refresh)

        out = await popup_service.create_popup(request, req, admin, db)

        assert out.id == 555
        # 서버 sanitize: <script>가 제거되어야 함
        assert "<script>" not in captured[0].body_html
        assert "<p>안녕</p>" in captured[0].body_html

        # audit state
        assert request.state.audit_target_type == "popup"
        assert request.state.audit_target_id == 555
        assert request.state.audit_diff["after"]["title"] == "5월 프로모션"

    async def test_create_invalid_link_url_raises_422(self):
        admin = _admin_mock()
        request = _request_mock()
        req = _make_create_request(link_url="javascript:alert(1)")

        db = MagicMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        with pytest.raises(HTTPException) as exc:
            await popup_service.create_popup(request, req, admin, db)
        assert exc.value.status_code == 422
        assert exc.value.detail["code"] == "POPUP_LINK_URL_INVALID"

    async def test_create_display_range_invalid_raises_422(self):
        admin = _admin_mock()
        request = _request_mock()
        # display_end <= display_start → days_offset 음수
        req = _make_create_request(days_offset=-1)

        db = MagicMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        with pytest.raises(HTTPException) as exc:
            await popup_service.create_popup(request, req, admin, db)
        assert exc.value.status_code == 422
        assert exc.value.detail["code"] == "POPUP_DISPLAY_RANGE_INVALID"

    async def test_create_link_url_none_allowed(self):
        admin = _admin_mock()
        request = _request_mock()
        req = _make_create_request(link_url=None)

        captured: list = []

        def _refresh(obj):
            obj.id = 7
            obj.created_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
            obj.updated_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
            return None

        db = MagicMock()
        db.add = MagicMock(side_effect=lambda obj: captured.append(obj))
        db.commit = AsyncMock()
        db.refresh = AsyncMock(side_effect=_refresh)

        out = await popup_service.create_popup(request, req, admin, db)
        assert out.link_url is None


# ──────────────────────────────────────────────────────────────────────────────
# update_popup
# ──────────────────────────────────────────────────────────────────────────────


class TestUpdatePopup:
    async def test_update_records_before_after_diff(self):
        admin = _admin_mock()
        request = _request_mock()
        existing = _popup_row(popup_id=42, title="이전 제목", is_active=True)

        select_result = MagicMock()
        select_result.scalar_one_or_none = MagicMock(return_value=existing)

        db = MagicMock()
        db.execute = AsyncMock(return_value=select_result)
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        new_req = PopupUpdateRequest(
            title="새 제목",
            body_html="<p>업데이트</p>",
            link_url="https://denvia.kr",
            display_start=existing.display_start,
            display_end=existing.display_end,
            target_segment="doctor",
            is_active=False,
        )
        out = await popup_service.update_popup(request, 42, new_req, admin, db)

        assert out.title == "새 제목"
        assert out.target_segment == "doctor"
        assert request.state.audit_diff["before"]["title"] == "이전 제목"
        assert request.state.audit_diff["after"]["title"] == "새 제목"
        assert request.state.audit_diff["before"]["is_active"] is True
        assert request.state.audit_diff["after"]["is_active"] is False

    async def test_update_404_when_soft_deleted(self):
        admin = _admin_mock()
        request = _request_mock()

        select_result = MagicMock()
        select_result.scalar_one_or_none = MagicMock(return_value=None)
        db = MagicMock()
        db.execute = AsyncMock(return_value=select_result)

        new_req = _make_create_request()
        with pytest.raises(HTTPException) as exc:
            await popup_service.update_popup(request, 999, new_req, admin, db)
        assert exc.value.status_code == 404


# ──────────────────────────────────────────────────────────────────────────────
# toggle_active
# ──────────────────────────────────────────────────────────────────────────────


class TestToggleActive:
    async def test_toggle_records_audit_diff(self):
        admin = _admin_mock()
        request = _request_mock()
        popup = _popup_row(popup_id=12, is_active=True)

        select_result = MagicMock()
        select_result.scalar_one_or_none = MagicMock(return_value=popup)

        db = MagicMock()
        db.execute = AsyncMock(return_value=select_result)
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        out = await popup_service.toggle_active(
            request, 12, is_active=False, admin=admin, db=db
        )
        assert out.id == 12
        assert out.is_active is False
        assert request.state.audit_diff == {
            "before": {"is_active": True},
            "after": {"is_active": False},
        }

    async def test_toggle_404_when_missing(self):
        admin = _admin_mock()
        request = _request_mock()

        select_result = MagicMock()
        select_result.scalar_one_or_none = MagicMock(return_value=None)
        db = MagicMock()
        db.execute = AsyncMock(return_value=select_result)

        with pytest.raises(HTTPException) as exc:
            await popup_service.toggle_active(
                request, 999, is_active=False, admin=admin, db=db
            )
        assert exc.value.status_code == 404


# ──────────────────────────────────────────────────────────────────────────────
# delete_popup
# ──────────────────────────────────────────────────────────────────────────────


class TestDeletePopup:
    async def test_delete_sets_deleted_at_and_is_active_false(self):
        admin = _admin_mock()
        request = _request_mock()
        popup = _popup_row(popup_id=7, is_active=True, title="삭제 대상")

        select_result = MagicMock()
        select_result.scalar_one_or_none = MagicMock(return_value=popup)

        db = MagicMock()
        db.execute = AsyncMock(return_value=select_result)
        db.commit = AsyncMock()

        await popup_service.delete_popup(request, 7, admin, db)
        assert popup.is_active is False
        assert popup.deleted_at is not None  # func.now() expression
        assert request.state.audit_diff["before"]["title"] == "삭제 대상"
        assert request.state.audit_diff["after"]["deleted_at"] == "now"
        assert request.state.audit_target_id == 7

    async def test_delete_404_when_already_soft_deleted(self):
        admin = _admin_mock()
        request = _request_mock()

        select_result = MagicMock()
        select_result.scalar_one_or_none = MagicMock(return_value=None)
        db = MagicMock()
        db.execute = AsyncMock(return_value=select_result)
        db.commit = AsyncMock()

        with pytest.raises(HTTPException) as exc:
            await popup_service.delete_popup(request, 999, admin, db)
        assert exc.value.status_code == 404
