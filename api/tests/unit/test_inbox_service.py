"""api/src/services/inbox_service 단위 테스트 — Story 4.5 (T3.4 일부)."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.src.models.inbox_message import InboxMessage
from api.src.services import inbox_service


@pytest.mark.asyncio
async def test_mark_read_returns_none_when_not_found() -> None:
    """타인 row 또는 미존재 → None (404 분기용)."""
    db = AsyncMock()
    select_result = MagicMock()
    select_result.scalar_one_or_none = MagicMock(return_value=None)
    db.execute = AsyncMock(return_value=select_result)

    out = await inbox_service.mark_read(db, user_id=1, message_id=999)
    assert out is None
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_mark_read_idempotent_on_already_read() -> None:
    """이미 읽음 → True 반환 + commit 호출 안 함."""
    msg = MagicMock(spec=InboxMessage)
    msg.is_read = True

    db = AsyncMock()
    select_result = MagicMock()
    select_result.scalar_one_or_none = MagicMock(return_value=msg)
    db.execute = AsyncMock(return_value=select_result)

    out = await inbox_service.mark_read(db, user_id=1, message_id=10)
    assert out is True
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_mark_read_flips_unread_to_read() -> None:
    """미읽음 → False 반환 + is_read 토글 + commit."""
    msg = MagicMock(spec=InboxMessage)
    msg.is_read = False

    db = AsyncMock()
    select_result = MagicMock()
    select_result.scalar_one_or_none = MagicMock(return_value=msg)
    db.execute = AsyncMock(return_value=select_result)

    out = await inbox_service.mark_read(db, user_id=1, message_id=10)
    assert out is False
    assert msg.is_read is True
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_unread_count_returns_int() -> None:
    db = AsyncMock()
    count_result = MagicMock()
    count_result.scalar_one = MagicMock(return_value=7)
    db.execute = AsyncMock(return_value=count_result)

    out = await inbox_service.get_unread_count(db, user_id=42)
    assert out == 7


@pytest.mark.asyncio
async def test_list_inbox_sanitizes_body_html() -> None:
    """list_inbox 응답에 sanitize 적용된 body_html_safe가 포함된다."""
    msg = MagicMock(spec=InboxMessage)
    msg.id = 1
    msg.type = "notice"
    msg.title = "title"
    msg.body_html = "<p>안녕</p><script>evil()</script>"
    msg.is_read = False
    msg.created_at = datetime(2026, 4, 30, tzinfo=timezone.utc)
    msg.notice_id = 5
    msg.popup_id = None

    db = AsyncMock()
    count_result = MagicMock()
    count_result.scalar_one = MagicMock(return_value=1)
    unread_result = MagicMock()
    unread_result.scalar_one = MagicMock(return_value=1)
    rows_result = MagicMock()
    rows_result.scalars = MagicMock(
        return_value=MagicMock(all=MagicMock(return_value=[msg]))
    )
    db.execute = AsyncMock(side_effect=[count_result, unread_result, rows_result])

    response = await inbox_service.list_inbox(
        db, user_id=1, page=1, per_page=20, filter_unread=False
    )
    assert response.total == 1
    assert response.unread_count == 1
    assert len(response.items) == 1
    item = response.items[0]
    assert "<script>" not in item.body_html_safe
    assert "<p>안녕</p>" in item.body_html_safe
    assert item.message_id == 1
    assert item.notice_id == 5


# ── Story 7.2 v2: get_active_popups (배열) — 디바이스 필터 + 빈 결과 ─────────


def _mock_scalars(rows: list) -> MagicMock:
    """db.execute().scalars().all() 체이닝을 흉내내는 MagicMock 헬퍼."""
    result = MagicMock()
    scalars = MagicMock()
    scalars.all = MagicMock(return_value=rows)
    result.scalars = MagicMock(return_value=scalars)
    return result


@pytest.mark.asyncio
async def test_get_active_popups_returns_empty_when_no_match() -> None:
    user = MagicMock()
    user.id = 1
    user.segment = None

    db = AsyncMock()
    db.execute = AsyncMock(return_value=_mock_scalars([]))

    out = await inbox_service.get_active_popups(db, user, device="pc")
    assert out == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "unsafe_link",
    [
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "//evil.example/x",
        "/relative/path",
    ],
)
async def test_get_active_popups_strips_unsafe_link_url(unsafe_link: str) -> None:
    user = MagicMock()
    user.id = 1
    user.segment = None

    popup = MagicMock()
    popup.id = 7
    popup.title = "T"
    popup.body_html = "<p>x</p>"
    popup.image_url = None
    popup.popup_type = "editor"
    popup.link_url = unsafe_link
    popup.display_end = datetime(2026, 12, 31, tzinfo=timezone.utc)

    db = AsyncMock()
    db.execute = AsyncMock(return_value=_mock_scalars([popup]))

    out = await inbox_service.get_active_popups(db, user, device="pc")
    assert len(out) == 1
    assert out[0].link_url is None


@pytest.mark.asyncio
async def test_get_active_popups_query_includes_device_and_deleted_filters() -> None:
    """SELECT 절에 deleted_at IS NULL + target_device 필터가 모두 포함된다."""
    user = MagicMock()
    user.id = 1
    user.segment = None

    captured: list = []

    async def _capture(stmt):
        captured.append(stmt)
        return _mock_scalars([])

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=_capture)

    await inbox_service.get_active_popups(db, user, device="mobile")
    assert len(captured) == 1
    sql = str(captured[0].compile(compile_kwargs={"literal_binds": False}))
    assert "deleted_at IS NULL" in sql
    assert "target_device" in sql
