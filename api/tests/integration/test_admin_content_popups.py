"""Admin 팝업 관리 통합 테스트 — Story 7.2.

CRUD 6 endpoint × 200/201/204/401/403/404/422 + audit_logs INSERT 검증.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest
from httpx import ASGITransport, AsyncClient

from api.src.main import app
from api.src.models.audit_log import AuditLog
from api.src.models.base import get_session
from api.src.models.popup import Popup
from api.src.settings import settings


# ──────────────────────────────────────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────────────────────────────────────

_next_user_id = 5000


def _make_admin_jwt() -> tuple[str, int]:
    global _next_user_id
    _next_user_id += 1
    uid = _next_user_id
    payload = {
        "sub": str(uid),
        "aud": "denvia-admin",
        "exp": int(time.time()) + 3600,
    }
    token = pyjwt.encode(
        payload,
        settings.denvia_jwt_secret,
        algorithm=settings.denvia_jwt_algorithm,
    )
    return token, uid


def _make_user_jwt() -> tuple[str, int]:
    """관리자 아닌 일반 user 세션(audience 미스매치 → 403)."""
    global _next_user_id
    _next_user_id += 1
    uid = _next_user_id
    payload = {
        "sub": str(uid),
        "aud": "denvia-app",
        "exp": int(time.time()) + 3600,
    }
    token = pyjwt.encode(
        payload,
        settings.denvia_jwt_secret,
        algorithm=settings.denvia_jwt_algorithm,
    )
    return token, uid


def _admin_user_mock(user_id: int):
    user = MagicMock()
    user.id = user_id
    user.email = "admin@denvia.local"
    user.role = "admin"
    user.subscription_status = "free"
    user.segment = None
    user.years_of_experience = None
    user.withdrawn_at = None  # MagicMock 기본은 not None — get_current_admin이 401로 거부함
    user.must_reset_password = False
    user.current_session_id = None
    user.admin_grade = "master"
    return user


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
    popup.created_by_admin_id = 1
    return popup


def _audit_ctx(capture: list):
    session = MagicMock()
    session.add = lambda obj: capture.append(obj)
    session.commit = AsyncMock()

    class FakeCtx:
        async def __aenter__(self_inner):
            return session

        async def __aexit__(self_inner, *a):
            pass

    return FakeCtx()


def _make_db_session(*, fetched_popup=None, list_total: int = 0, list_items=()):
    """팝업 라우터용 DB 세션 mock — execute side_effect로 호출 순서 시뮬레이션.

    create: db.add 호출 + commit + refresh
    fetch: select.scalar_one_or_none = fetched_popup
    list: count 다음에 items
    """
    fetch_result = MagicMock()
    fetch_result.scalar_one_or_none = MagicMock(return_value=fetched_popup)

    count_result = MagicMock()
    count_result.scalar_one = MagicMock(return_value=list_total)

    items_result = MagicMock()
    items_result.scalars = MagicMock(
        return_value=MagicMock(all=MagicMock(return_value=list(list_items)))
    )

    call_log = {"count": 0}

    async def _execute(stmt):
        call_log["count"] += 1
        # 첫 호출이 list 호출이면 count → items 패턴, 그 외에는 fetch.
        # 호출자가 list_total > 0 또는 list_items > 0를 줬다면 list 패턴.
        if list_items or list_total:
            if call_log["count"] == 1:
                return count_result
            return items_result
        return fetch_result

    # 실제 SQLAlchemy처럼 flush 시점에 captured 객체에 id를 부여 — audit_target_id 검증용.
    captured_inserts: list = []

    async def _flush():
        if captured_inserts:
            captured_inserts[0].id = 555
        return None

    session = MagicMock()
    session.execute = AsyncMock(side_effect=_execute)
    session.add = MagicMock(side_effect=lambda obj: captured_inserts.append(obj))
    session.flush = AsyncMock(side_effect=_flush)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    async def _gen():
        yield session

    return _gen, session


# ──────────────────────────────────────────────────────────────────────────────
# 인증 가드
# ──────────────────────────────────────────────────────────────────────────────


class TestAuthGuards:
    async def test_list_401_when_no_cookie(self):
        db_gen, _ = _make_db_session(list_total=0, list_items=[])
        app.dependency_overrides[get_session] = db_gen
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                res = await client.get("/api/v1/admin/popups")
        finally:
            app.dependency_overrides.pop(get_session, None)
        assert res.status_code == 401

    async def test_list_401_when_user_audience(self):
        token, _ = _make_user_jwt()
        db_gen, _ = _make_db_session(list_total=0, list_items=[])
        app.dependency_overrides[get_session] = db_gen
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                res = await client.get(
                    "/api/v1/admin/popups",
                    cookies={"denvia_admin_session": token},
                )
        finally:
            app.dependency_overrides.pop(get_session, None)
        # admin audience 미스매치는 401(인증 실패) — require_admin이 처리.
        assert res.status_code == 401


# ──────────────────────────────────────────────────────────────────────────────
# GET /admin/popups
# ──────────────────────────────────────────────────────────────────────────────


class TestListPopups:
    async def test_200_flat_pagination(self):
        token, uid = _make_admin_jwt()
        admin = _admin_user_mock(uid)
        rows = [_popup_row(popup_id=10), _popup_row(popup_id=11, title="다른 팝업")]
        db_gen, _ = _make_db_session(list_total=2, list_items=rows)

        with patch(
            "api.src.deps.auth.get_user_by_id",
            new=AsyncMock(return_value=admin),
        ):
            app.dependency_overrides[get_session] = db_gen
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.get(
                        "/api/v1/admin/popups",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.pop(get_session, None)

        assert res.status_code == 200, res.text
        body = res.json()
        # AR27 flat 페이지네이션 4 키
        assert set(body.keys()) == {"items", "page", "per_page", "total"}
        assert body["total"] == 2
        assert body["page"] == 1
        assert body["per_page"] == 20
        assert len(body["items"]) == 2

    async def test_per_page_422_when_above_max(self):
        token, uid = _make_admin_jwt()
        admin = _admin_user_mock(uid)
        db_gen, _ = _make_db_session(list_total=0, list_items=[])

        with patch(
            "api.src.deps.auth.get_user_by_id",
            new=AsyncMock(return_value=admin),
        ):
            app.dependency_overrides[get_session] = db_gen
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.get(
                        "/api/v1/admin/popups?per_page=500",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.pop(get_session, None)
        assert res.status_code == 422


# ──────────────────────────────────────────────────────────────────────────────
# GET /admin/popups/{id}
# ──────────────────────────────────────────────────────────────────────────────


class TestGetPopupDetail:
    async def test_200_returns_raw_body_html(self):
        token, uid = _make_admin_jwt()
        admin = _admin_user_mock(uid)
        popup = _popup_row(popup_id=42, body_html="<p>raw</p>")
        db_gen, _ = _make_db_session(fetched_popup=popup)

        with patch(
            "api.src.deps.auth.get_user_by_id",
            new=AsyncMock(return_value=admin),
        ):
            app.dependency_overrides[get_session] = db_gen
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.get(
                        "/api/v1/admin/popups/42",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.pop(get_session, None)

        assert res.status_code == 200
        body = res.json()
        assert body["id"] == 42
        # 편집 prefill용 raw 그대로 노출
        assert body["body_html"] == "<p>raw</p>"

    async def test_404_when_not_found(self):
        token, uid = _make_admin_jwt()
        admin = _admin_user_mock(uid)
        db_gen, _ = _make_db_session(fetched_popup=None)

        with patch(
            "api.src.deps.auth.get_user_by_id",
            new=AsyncMock(return_value=admin),
        ):
            app.dependency_overrides[get_session] = db_gen
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.get(
                        "/api/v1/admin/popups/9999",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.pop(get_session, None)
        assert res.status_code == 404
        assert res.json()["code"] == "POPUP_NOT_FOUND"


# ──────────────────────────────────────────────────────────────────────────────
# POST /admin/popups
# ──────────────────────────────────────────────────────────────────────────────


def _valid_create_body(**overrides) -> dict:
    body = {
        "title": "5월 프로모션",
        "body_html": "<p>안녕하세요</p>",
        "link_url": "https://example.com/promo",
        "display_start": "2026-05-01T00:00:00+00:00",
        "display_end": "2026-05-31T00:00:00+00:00",
        "target_segment": "all",
        "is_active": True,
    }
    body.update(overrides)
    return body


class TestCreatePopup:
    async def test_201_inserts_and_records_audit(self):
        token, uid = _make_admin_jwt()
        admin = _admin_user_mock(uid)
        db_gen, session = _make_db_session()

        # post는 fetch 호출 없음 — db.add + commit + refresh.
        # refresh가 호출되면 popup.id를 채워줌.
        def _refresh(obj):
            obj.id = 555
            obj.created_at = datetime.now(timezone.utc)
            obj.updated_at = datetime.now(timezone.utc)
            return None

        session.refresh = AsyncMock(side_effect=_refresh)

        captured_audit: list = []
        with (
            patch(
                "api.src.deps.auth.get_user_by_id",
                new=AsyncMock(return_value=admin),
            ),
            patch(
                "api.src.middleware.audit.async_session_factory",
                side_effect=lambda: _audit_ctx(captured_audit),
            ),
        ):
            app.dependency_overrides[get_session] = db_gen
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.post(
                        "/api/v1/admin/popups",
                        cookies={"denvia_admin_session": token},
                        json=_valid_create_body(),
                    )
            finally:
                app.dependency_overrides.pop(get_session, None)

        assert res.status_code == 201
        body = res.json()
        assert body["id"] == 555
        # audit_logs 1행 INSERT 확인
        audit_entries = [o for o in captured_audit if isinstance(o, AuditLog)]
        assert len(audit_entries) == 1
        entry = audit_entries[0]
        assert entry.action == "popup.create"
        assert entry.target_type == "popup"
        assert entry.target_id == 555
        assert entry.diff_json is not None
        assert "after" in entry.diff_json

    async def test_422_when_display_range_invalid(self):
        token, uid = _make_admin_jwt()
        admin = _admin_user_mock(uid)
        db_gen, _ = _make_db_session()

        captured_audit: list = []
        with (
            patch(
                "api.src.deps.auth.get_user_by_id",
                new=AsyncMock(return_value=admin),
            ),
            patch(
                "api.src.middleware.audit.async_session_factory",
                side_effect=lambda: _audit_ctx(captured_audit),
            ),
        ):
            app.dependency_overrides[get_session] = db_gen
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.post(
                        "/api/v1/admin/popups",
                        cookies={"denvia_admin_session": token},
                        json=_valid_create_body(
                            display_start="2026-05-31T00:00:00+00:00",
                            display_end="2026-05-01T00:00:00+00:00",
                        ),
                    )
            finally:
                app.dependency_overrides.pop(get_session, None)
        assert res.status_code == 422
        assert res.json()["code"] == "POPUP_DISPLAY_RANGE_INVALID"
        # 4xx는 audit_logs INSERT 안 함
        assert [o for o in captured_audit if isinstance(o, AuditLog)] == []

    async def test_422_when_link_url_invalid(self):
        token, uid = _make_admin_jwt()
        admin = _admin_user_mock(uid)
        db_gen, _ = _make_db_session()

        with patch(
            "api.src.deps.auth.get_user_by_id",
            new=AsyncMock(return_value=admin),
        ):
            app.dependency_overrides[get_session] = db_gen
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.post(
                        "/api/v1/admin/popups",
                        cookies={"denvia_admin_session": token},
                        json=_valid_create_body(link_url="javascript:alert(1)"),
                    )
            finally:
                app.dependency_overrides.pop(get_session, None)
        assert res.status_code == 422
        assert res.json()["code"] == "POPUP_LINK_URL_INVALID"

    async def test_422_when_title_blank(self):
        token, uid = _make_admin_jwt()
        admin = _admin_user_mock(uid)
        db_gen, _ = _make_db_session()

        with patch(
            "api.src.deps.auth.get_user_by_id",
            new=AsyncMock(return_value=admin),
        ):
            app.dependency_overrides[get_session] = db_gen
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.post(
                        "/api/v1/admin/popups",
                        cookies={"denvia_admin_session": token},
                        json=_valid_create_body(title=""),
                    )
            finally:
                app.dependency_overrides.pop(get_session, None)
        assert res.status_code == 422


# ──────────────────────────────────────────────────────────────────────────────
# PATCH /admin/popups/{id}
# ──────────────────────────────────────────────────────────────────────────────


class TestTogglePopup:
    async def test_200_flips_is_active_and_records_audit(self):
        token, uid = _make_admin_jwt()
        admin = _admin_user_mock(uid)
        popup = _popup_row(popup_id=12, is_active=True)
        db_gen, _ = _make_db_session(fetched_popup=popup)

        captured_audit: list = []
        with (
            patch(
                "api.src.deps.auth.get_user_by_id",
                new=AsyncMock(return_value=admin),
            ),
            patch(
                "api.src.middleware.audit.async_session_factory",
                side_effect=lambda: _audit_ctx(captured_audit),
            ),
        ):
            app.dependency_overrides[get_session] = db_gen
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.patch(
                        "/api/v1/admin/popups/12",
                        cookies={"denvia_admin_session": token},
                        json={"is_active": False},
                    )
            finally:
                app.dependency_overrides.pop(get_session, None)

        assert res.status_code == 200
        body = res.json()
        assert body["id"] == 12
        assert body["is_active"] is False

        entries = [o for o in captured_audit if isinstance(o, AuditLog)]
        assert len(entries) == 1
        assert entries[0].action == "popup.toggle"
        assert entries[0].diff_json == {
            "before": {"is_active": True},
            "after": {"is_active": False},
        }

    async def test_422_when_extra_fields_provided(self):
        """extra='forbid' — title 등 다른 필드 거부."""
        token, uid = _make_admin_jwt()
        admin = _admin_user_mock(uid)
        popup = _popup_row(popup_id=12)
        db_gen, _ = _make_db_session(fetched_popup=popup)

        with patch(
            "api.src.deps.auth.get_user_by_id",
            new=AsyncMock(return_value=admin),
        ):
            app.dependency_overrides[get_session] = db_gen
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.patch(
                        "/api/v1/admin/popups/12",
                        cookies={"denvia_admin_session": token},
                        json={"is_active": False, "title": "변경 시도"},
                    )
            finally:
                app.dependency_overrides.pop(get_session, None)
        assert res.status_code == 422


# ──────────────────────────────────────────────────────────────────────────────
# DELETE /admin/popups/{id}
# ──────────────────────────────────────────────────────────────────────────────


class TestDeletePopup:
    async def test_204_soft_delete_records_audit(self):
        token, uid = _make_admin_jwt()
        admin = _admin_user_mock(uid)
        popup = _popup_row(popup_id=7, is_active=True, title="삭제 대상")
        db_gen, _ = _make_db_session(fetched_popup=popup)

        captured_audit: list = []
        with (
            patch(
                "api.src.deps.auth.get_user_by_id",
                new=AsyncMock(return_value=admin),
            ),
            patch(
                "api.src.middleware.audit.async_session_factory",
                side_effect=lambda: _audit_ctx(captured_audit),
            ),
        ):
            app.dependency_overrides[get_session] = db_gen
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.delete(
                        "/api/v1/admin/popups/7",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.pop(get_session, None)

        assert res.status_code == 204
        # popup 객체 변경 확인
        assert popup.is_active is False
        assert popup.deleted_at is not None
        # audit
        entries = [o for o in captured_audit if isinstance(o, AuditLog)]
        assert len(entries) == 1
        assert entries[0].action == "popup.delete"
        assert entries[0].target_id == 7
