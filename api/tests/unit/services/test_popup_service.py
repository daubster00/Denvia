"""api/src/services/popup_service 단위 테스트 — Story 7.2."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, UploadFile

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
    admin.current_session_id = None
    admin.admin_grade = "master"
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
    display_position: str = "center",
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
    popup.display_position = display_position
    popup.display_position_top_px = None
    popup.display_position_left_px = None
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
    display_position: str = "center",
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
        display_position=display_position,
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
            obj.created_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
            obj.updated_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
            return None

        async def _flush():
            # 실제 SQLAlchemy처럼 flush 시점에 자동증분 id 부여 시뮬레이션.
            if captured:
                captured[0].id = 555
            return None

        db = MagicMock()
        db.add = MagicMock(side_effect=lambda obj: captured.append(obj))
        db.flush = AsyncMock(side_effect=_flush)
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
            obj.created_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
            obj.updated_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
            return None

        async def _flush():
            if captured:
                captured[0].id = 7
            return None

        db = MagicMock()
        db.add = MagicMock(side_effect=lambda obj: captured.append(obj))
        db.flush = AsyncMock(side_effect=_flush)
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


# ──────────────────────────────────────────────────────────────────────────────
# 타입 페이로드 / 이미지 URL 검증 — Story 7.2 v2 (AC-4)
# ──────────────────────────────────────────────────────────────────────────────


class TestTypePayloadValidation:
    """popup_type vs payload 일관성 검증 (POPUP_IMAGE_REQUIRED / POPUP_BODY_REQUIRED)."""

    async def test_image_type_without_image_url_raises_422(self):
        admin = _admin_mock()
        request = _request_mock()
        # popup_type=image 인데 image_url 누락
        req = _make_create_request(
            popup_type="image",
            image_url=None,
            body_html="<p>본문 있어도 무시</p>",
        )

        db = MagicMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        with pytest.raises(HTTPException) as exc:
            await popup_service.create_popup(request, req, admin, db)
        assert exc.value.status_code == 422
        assert exc.value.detail["code"] == "POPUP_IMAGE_REQUIRED"

    async def test_editor_type_with_blank_body_raises_422(self):
        admin = _admin_mock()
        request = _request_mock()
        # popup_type=editor + body_html None → blank
        req = _make_create_request(popup_type="editor", body_html=None)

        db = MagicMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        with pytest.raises(HTTPException) as exc:
            await popup_service.create_popup(request, req, admin, db)
        assert exc.value.status_code == 422
        assert exc.value.detail["code"] == "POPUP_BODY_REQUIRED"

    async def test_external_image_url_blocked(self):
        """업로드 prefix가 아닌 URL은 422 (외부 URL 차단)."""
        admin = _admin_mock()
        request = _request_mock()
        req = _make_create_request(
            popup_type="image",
            image_url="https://evil.example/x.png",
            body_html=None,
        )

        db = MagicMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        with pytest.raises(HTTPException) as exc:
            await popup_service.create_popup(request, req, admin, db)
        assert exc.value.status_code == 422
        assert exc.value.detail["code"] == "POPUP_IMAGE_URL_INVALID"

    async def test_image_url_path_traversal_blocked(self):
        """업로드 prefix 뒤 path traversal 시도는 422."""
        admin = _admin_mock()
        request = _request_mock()
        req = _make_create_request(
            popup_type="image",
            image_url="/static/popup-images/../etc/passwd",
            body_html=None,
        )

        db = MagicMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        with pytest.raises(HTTPException) as exc:
            await popup_service.create_popup(request, req, admin, db)
        assert exc.value.status_code == 422
        assert exc.value.detail["code"] == "POPUP_IMAGE_URL_INVALID"


# ──────────────────────────────────────────────────────────────────────────────
# upload_popup_image — Story 7.2 v2 (AC-3)
# ──────────────────────────────────────────────────────────────────────────────


def _upload_file(*, name: str, content_type: str, payload: bytes) -> UploadFile:
    return UploadFile(
        filename=name,
        file=BytesIO(payload),
        headers={"content-type": content_type},  # type: ignore[arg-type]
    )


class TestUploadPopupImage:
    async def test_rejects_invalid_mime(self):
        admin = _admin_mock()
        request = _request_mock()
        upload = _upload_file(name="x.gif", content_type="image/gif", payload=b"GIF")

        with pytest.raises(HTTPException) as exc:
            await popup_service.upload_popup_image(request, upload, admin)
        assert exc.value.status_code == 422
        assert exc.value.detail["code"] == "POPUP_IMAGE_MIME_INVALID"

    async def test_rejects_invalid_extension(self):
        admin = _admin_mock()
        request = _request_mock()
        # MIME는 OK지만 확장자가 .gif (방어 이중층)
        upload = _upload_file(
            name="x.gif", content_type="image/png", payload=b"\x89PNG"
        )

        with pytest.raises(HTTPException) as exc:
            await popup_service.upload_popup_image(request, upload, admin)
        assert exc.value.status_code == 422
        assert exc.value.detail["code"] == "POPUP_IMAGE_EXT_INVALID"

    async def test_rejects_oversized_file(self):
        admin = _admin_mock()
        request = _request_mock()
        big = b"\x89PNG" + b"\x00" * (5 * 1024 * 1024 + 1)  # 5MB + 1 byte
        upload = _upload_file(
            name="x.png", content_type="image/png", payload=big
        )

        with pytest.raises(HTTPException) as exc:
            await popup_service.upload_popup_image(request, upload, admin)
        assert exc.value.status_code == 422
        assert exc.value.detail["code"] == "POPUP_IMAGE_TOO_LARGE"

    async def test_accepts_valid_png_returns_safe_url(self, tmp_path, monkeypatch):
        admin = _admin_mock(user_id=42)
        request = _request_mock()
        upload = _upload_file(
            name="hello.png", content_type="image/png", payload=b"\x89PNGfake"
        )

        # 디스크 쓰기를 임시 디렉터리로 격리.
        monkeypatch.setattr(popup_service, "POPUP_IMAGE_DIR", tmp_path)

        out = await popup_service.upload_popup_image(request, upload, admin)

        # 응답 검증: prefix + safe filename(uuid hex + .png)
        assert out.image_url.startswith("/static/popup-images/")
        assert out.image_url.endswith(".png")
        assert out.size_bytes == len(b"\x89PNGfake")
        assert out.mime_type == "image/png"

        # 실제 파일이 디스크에 기록되었는지 확인.
        written = list(tmp_path.iterdir())
        assert len(written) == 1
        assert written[0].read_bytes() == b"\x89PNGfake"

        # audit context 설정 검증.
        assert request.state.audit_target_type == "popup_image"
        assert "filename" in request.state.audit_diff["after"]
        assert (
            request.state.audit_diff["after"]["original_name"] == "hello.png"
        )
        assert request.state.audit_diff["after"]["mime_type"] == "image/png"
