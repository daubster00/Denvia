"""GET/PATCH/POST /api/v1/me/inbox|popups 통합 테스트 — Story 4.5 (T3.5).

ASGI 스택으로 라우터 호출 → 인증 가드·422·404·sanitize·invalidate 분기 검증.
DB는 inbox_service 함수를 직접 monkeypatch하여 모킹한다.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from api.src.deps.auth import get_current_user
from api.src.main import app
from api.src.models.base import get_session
from api.src.models.user import User
from api.src.schemas.inbox import (
    ActivePopupResponse,
    InboxItem,
    InboxListResponse,
)


def _make_user(user_id: int = 1, segment: str | None = None) -> MagicMock:
    u = MagicMock(spec=User)
    u.id = user_id
    u.segment = segment
    u.email = "user@example.com"
    u.current_session_id = None
    u.admin_grade = "master"
    return u


def _stub_session():
    """라우터가 db.execute()를 직접 호출하지 않으므로 빈 세션이면 충분."""
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()

    async def gen():
        yield session

    return gen


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
class TestInboxEndpoints:
    async def test_inbox_unauth_returns_401(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.get("/api/v1/me/inbox")
        assert res.status_code == 401
        assert res.json()["code"] == "AUTH_NOT_AUTHENTICATED"

    async def test_inbox_invalid_per_page_returns_422(self):
        user = _make_user()
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = _stub_session()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.get("/api/v1/me/inbox?per_page=15")
        assert res.status_code == 422
        assert res.json()["code"] == "INVALID_PARAM"

    async def test_inbox_page_zero_returns_422(self):
        user = _make_user()
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = _stub_session()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.get("/api/v1/me/inbox?page=0")
        assert res.status_code == 422

    async def test_inbox_filter_invalid_returns_422(self):
        user = _make_user()
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = _stub_session()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.get("/api/v1/me/inbox?filter=garbage")
        assert res.status_code == 422

    async def test_inbox_returns_empty_list(self, monkeypatch):
        user = _make_user()
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = _stub_session()

        async def _list_inbox(*args, **kwargs):
            return InboxListResponse(
                items=[], page=1, per_page=20, total=0, unread_count=0
            )

        monkeypatch.setattr("api.src.routers.me.inbox_service.list_inbox", _list_inbox)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.get("/api/v1/me/inbox")
        assert res.status_code == 200
        body = res.json()
        assert body["items"] == []
        assert body["unread_count"] == 0

    async def test_inbox_one_item_payload(self, monkeypatch):
        user = _make_user()
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = _stub_session()

        async def _list_inbox(*args, **kwargs):
            return InboxListResponse(
                items=[
                    InboxItem(
                        message_id=4521,
                        type="notice",
                        title="5월 정기점검 안내",
                        body_html_safe="<p>점검</p>",
                        is_read=False,
                        created_at="2026-04-30T05:23:11+00:00",
                        notice_id=12,
                        popup_id=None,
                        inquiry_id=None,
                    )
                ],
                page=1,
                per_page=20,
                total=1,
                unread_count=1,
            )

        monkeypatch.setattr("api.src.routers.me.inbox_service.list_inbox", _list_inbox)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.get("/api/v1/me/inbox")
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 1
        assert body["unread_count"] == 1
        item = body["items"][0]
        # AR27 flat 키 정합
        assert set(item.keys()) == {
            "message_id",
            "type",
            "title",
            "body_html_safe",
            "is_read",
            "created_at",
            "notice_id",
            "popup_id",
            "inquiry_id",
        }
        assert item["message_id"] == 4521
        assert item["body_html_safe"] == "<p>점검</p>"


@pytest.mark.asyncio
class TestInboxReadEndpoint:
    async def test_unauth_returns_401(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.patch("/api/v1/me/inbox/1/read")
        assert res.status_code == 401

    async def test_returns_204_for_first_read(self, monkeypatch):
        user = _make_user()
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = _stub_session()

        async def _mark_read(db, user_id, message_id):
            return False  # 미읽음 → 읽음으로 전환

        monkeypatch.setattr("api.src.routers.me.inbox_service.mark_read", _mark_read)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.patch("/api/v1/me/inbox/1/read")
        assert res.status_code == 204

    async def test_returns_204_for_already_read(self, monkeypatch):
        user = _make_user()
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = _stub_session()

        async def _mark_read(db, user_id, message_id):
            return True  # 멱등

        monkeypatch.setattr("api.src.routers.me.inbox_service.mark_read", _mark_read)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.patch("/api/v1/me/inbox/1/read")
        assert res.status_code == 204

    async def test_returns_404_for_other_user_message(self, monkeypatch):
        user = _make_user()
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = _stub_session()

        async def _mark_read(db, user_id, message_id):
            return None  # 타인 row

        monkeypatch.setattr("api.src.routers.me.inbox_service.mark_read", _mark_read)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.patch("/api/v1/me/inbox/999/read")
        assert res.status_code == 404
        assert res.json()["code"] == "INBOX_MESSAGE_NOT_FOUND"


@pytest.mark.asyncio
class TestInboxReadAllEndpoint:
    """#118: POST /api/v1/me/inbox/read-all — 전체읽음."""

    async def test_unauth_returns_401(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.post("/api/v1/me/inbox/read-all")
        assert res.status_code == 401

    async def test_returns_updated_count(self, monkeypatch):
        user = _make_user()
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = _stub_session()

        captured_user_ids: list[int] = []

        async def _mark_all(db, user_id):
            captured_user_ids.append(user_id)
            return 5

        monkeypatch.setattr(
            "api.src.routers.me.inbox_service.mark_all_read", _mark_all
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.post("/api/v1/me/inbox/read-all")
        assert res.status_code == 200
        assert res.json() == {"updated_count": 5}
        # 본인 user_id로만 일괄 처리한다.
        assert captured_user_ids == [user.id]

    async def test_idempotent_zero_when_nothing_unread(self, monkeypatch):
        user = _make_user()
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = _stub_session()

        async def _mark_all(db, user_id):
            return 0

        monkeypatch.setattr(
            "api.src.routers.me.inbox_service.mark_all_read", _mark_all
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.post("/api/v1/me/inbox/read-all")
        assert res.status_code == 200
        assert res.json() == {"updated_count": 0}


@pytest.mark.asyncio
class TestUnreadCountEndpoint:
    async def test_unauth_returns_401(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.get("/api/v1/me/inbox/unread-count")
        assert res.status_code == 401

    async def test_returns_count(self, monkeypatch):
        user = _make_user()
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = _stub_session()

        async def _count(db, user_id):
            return 3

        monkeypatch.setattr(
            "api.src.routers.me.inbox_service.get_unread_count", _count
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.get("/api/v1/me/inbox/unread-count")
        assert res.status_code == 200
        assert res.json() == {"unread_count": 3}


@pytest.mark.asyncio
class TestActivePopupsEndpoint:
    """Story 7.2 v2: 배열 응답 + 디바이스 쿼리 + seen 엔드포인트 제거 회귀."""

    async def test_unauth_returns_401(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.get("/api/v1/me/popups/active")
        assert res.status_code == 401

    async def test_returns_empty_array_when_no_match(self, monkeypatch):
        user = _make_user()
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = _stub_session()

        async def _active(db, u, device):
            return []

        monkeypatch.setattr(
            "api.src.routers.me.inbox_service.get_active_popups", _active
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.get("/api/v1/me/popups/active?device=pc")
        assert res.status_code == 200
        assert res.json() == []

    async def test_returns_array_with_popups(self, monkeypatch):
        user = _make_user()
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = _stub_session()

        captured_device: list[str] = []

        async def _active(db, u, device):
            captured_device.append(device)
            return [
                ActivePopupResponse(
                    popup_id=12,
                    title="신규 서비스 안내",
                    popup_type="editor",
                    display_position="center",
                    display_position_top_px=None,
                    display_position_left_px=None,
                    image_url=None,
                    body_html_safe="<p>안녕</p>",
                    link_url="https://denvia.kr",
                    display_end="2026-05-31T00:00:00+00:00",
                ),
                ActivePopupResponse(
                    popup_id=13,
                    title="이미지 팝업",
                    popup_type="image",
                    display_position="center",
                    display_position_top_px=None,
                    display_position_left_px=None,
                    image_url="/static/popup-images/abc.png",
                    body_html_safe=None,
                    link_url=None,
                    display_end="2026-05-31T00:00:00+00:00",
                ),
            ]

        monkeypatch.setattr(
            "api.src.routers.me.inbox_service.get_active_popups", _active
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.get("/api/v1/me/popups/active?device=mobile")
        assert res.status_code == 200
        body = res.json()
        assert len(body) == 2
        assert body[0]["popup_id"] == 12
        assert body[1]["popup_type"] == "image"
        assert captured_device == ["mobile"]

    async def test_invalid_device_returns_422(self):
        user = _make_user()
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = _stub_session()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.get("/api/v1/me/popups/active?device=tablet")
        assert res.status_code == 422


@pytest.mark.asyncio
class TestPopupSeenEndpointRemoved:
    """Story 7.2 v2: seen 엔드포인트는 완전히 제거되어 404를 반환한다."""

    async def test_seen_endpoint_returns_404(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.post("/api/v1/me/popups/1/seen")
        # 라우트 자체가 없으므로 인증 검사 전에 404. (인증되어 있어도 동일)
        assert res.status_code == 404
