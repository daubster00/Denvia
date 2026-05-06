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


@pytest.mark.asyncio
async def test_get_active_popup_returns_none_when_no_match() -> None:
    """매칭 0건 시 None 반환 → 라우터에서 204."""
    user = MagicMock()
    user.id = 1
    user.segment = None

    db = AsyncMock()
    select_result = MagicMock()
    select_result.scalar_one_or_none = MagicMock(return_value=None)
    db.execute = AsyncMock(return_value=select_result)

    out = await inbox_service.get_active_popup(db, user)
    assert out is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "unsafe_link",
    [
        "javascript:alert(1)",
        "JavaScript:alert(1)",
        "  javascript:alert(1)",  # whitespace prefix bypass 시도
        "data:text/html,<script>alert(1)</script>",
        "mailto:user@evil.example",
        "vbscript:msgbox(1)",
        "file:///etc/passwd",
        "//evil.example/x",  # 스킴 없는 protocol-relative
        "/relative/path",
    ],
)
async def test_get_active_popup_strips_unsafe_link_url(unsafe_link: str) -> None:
    """popups.link_url에 javascript:/data:/mailto: 등이 들어와도 응답에는 노출되지 않음."""
    user = MagicMock()
    user.id = 1
    user.segment = None

    popup = MagicMock()
    popup.id = 7
    popup.title = "T"
    popup.body_html = "<p>x</p>"
    popup.link_url = unsafe_link
    popup.display_end = datetime(2026, 12, 31, tzinfo=timezone.utc)

    db = AsyncMock()
    select_result = MagicMock()
    select_result.scalar_one_or_none = MagicMock(return_value=popup)
    db.execute = AsyncMock(return_value=select_result)

    out = await inbox_service.get_active_popup(db, user)
    assert out is not None
    assert out.link_url is None


@pytest.mark.asyncio
async def test_get_active_popup_passes_https_link_url() -> None:
    """https:// URL은 그대로 통과한다."""
    user = MagicMock()
    user.id = 1
    user.segment = None

    popup = MagicMock()
    popup.id = 7
    popup.title = "T"
    popup.body_html = "<p>x</p>"
    popup.link_url = "https://denvia.kr/announce"
    popup.display_end = datetime(2026, 12, 31, tzinfo=timezone.utc)

    db = AsyncMock()
    select_result = MagicMock()
    select_result.scalar_one_or_none = MagicMock(return_value=popup)
    db.execute = AsyncMock(return_value=select_result)

    out = await inbox_service.get_active_popup(db, user)
    assert out is not None
    assert out.link_url == "https://denvia.kr/announce"


@pytest.mark.asyncio
async def test_get_active_popup_query_includes_deleted_at_is_null_filter() -> None:
    """Story 7.2: SELECT WHERE 절에 popups.deleted_at IS NULL 필터가 반드시 포함된다."""
    user = MagicMock()
    user.id = 1
    user.segment = None

    captured: list = []

    async def _capture(stmt):
        captured.append(stmt)
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=None)
        return result

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=_capture)

    await inbox_service.get_active_popup(db, user)
    assert len(captured) == 1
    sql = str(captured[0].compile(compile_kwargs={"literal_binds": False}))
    assert "deleted_at IS NULL" in sql, sql


@pytest.mark.asyncio
async def test_mark_popup_seen_excludes_soft_deleted() -> None:
    """Story 7.2: soft delete된 팝업은 mark_popup_seen에서 not_found 분기."""
    db = AsyncMock()
    select_result = MagicMock()
    select_result.scalar_one_or_none = MagicMock(return_value=None)
    db.execute = AsyncMock(return_value=select_result)

    out = await inbox_service.mark_popup_seen(db, user_id=1, popup_id=999)
    assert out == "not_found"
