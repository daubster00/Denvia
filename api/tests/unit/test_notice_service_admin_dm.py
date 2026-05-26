"""notice_service의 관리자 1:1 쪽지 관련 신규 함수 단위 테스트.

대상:
- get_admin_dm_detail: row 존재/미존재(404) 분기
- delete_admin_dm: row 존재 시 hard delete, 미존재 시 404, audit_diff 설정
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from api.src.models.inbox_message import InboxMessage
from api.src.models.user import User
from api.src.services import notice_service


def _make_admin(admin_id: int = 99) -> MagicMock:
    a = MagicMock(spec=User)
    a.id = admin_id
    a.email = "admin@example.com"
    return a


def _make_dm_row(message_id: int = 10, user_id: int = 7) -> MagicMock:
    msg = MagicMock(spec=InboxMessage)
    msg.id = message_id
    msg.user_id = user_id
    msg.title = "공지 제목"
    msg.body_html = "<p>본문</p>"
    msg.is_read = False
    msg.created_by_admin_id = 99
    msg.created_at = datetime(2026, 5, 26, tzinfo=timezone.utc)
    msg.deleted_at = None
    msg.type = "admin_dm"
    return msg


@pytest.mark.asyncio
async def test_get_admin_dm_detail_returns_404_when_missing() -> None:
    db = AsyncMock()
    result = MagicMock()
    result.one_or_none = MagicMock(return_value=None)
    db.execute = AsyncMock(return_value=result)

    with pytest.raises(HTTPException) as exc:
        await notice_service.get_admin_dm_detail(
            message_id=12345, admin=_make_admin(), db=db
        )
    assert exc.value.status_code == 404
    assert exc.value.detail["code"] == "ADMIN_DM_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_admin_dm_detail_returns_payload_with_user_email() -> None:
    msg = _make_dm_row()
    db = AsyncMock()
    result = MagicMock()
    result.one_or_none = MagicMock(
        return_value=(msg, "target@example.com", "타깃 사용자")
    )
    db.execute = AsyncMock(return_value=result)

    out = await notice_service.get_admin_dm_detail(
        message_id=msg.id, admin=_make_admin(), db=db
    )
    assert out.id == msg.id
    assert out.target_user_id == msg.user_id
    assert out.target_user_email == "target@example.com"
    assert out.target_user_name == "타깃 사용자"
    assert out.is_read is False
    assert out.title == "공지 제목"


@pytest.mark.asyncio
async def test_delete_admin_dm_404_when_missing() -> None:
    db = AsyncMock()
    select_result = MagicMock()
    select_result.scalar_one_or_none = MagicMock(return_value=None)
    db.execute = AsyncMock(return_value=select_result)

    request = MagicMock()
    request.state = MagicMock()

    with pytest.raises(HTTPException) as exc:
        await notice_service.delete_admin_dm(
            request=request, message_id=999, admin=_make_admin(), db=db
        )
    assert exc.value.status_code == 404
    assert exc.value.detail["code"] == "ADMIN_DM_NOT_FOUND"
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_delete_admin_dm_hard_deletes_and_records_audit() -> None:
    msg = _make_dm_row()
    db = AsyncMock()

    select_result = MagicMock()
    select_result.scalar_one_or_none = MagicMock(return_value=msg)
    delete_result = MagicMock()

    db.execute = AsyncMock(side_effect=[select_result, delete_result])

    request = MagicMock()
    request.state = MagicMock()

    await notice_service.delete_admin_dm(
        request=request, message_id=msg.id, admin=_make_admin(), db=db
    )

    assert db.execute.await_count == 2
    db.commit.assert_awaited_once()
    assert request.state.audit_target_type == "inbox_message"
    assert request.state.audit_target_id == msg.id
    assert request.state.audit_diff["before"]["target_user_id"] == msg.user_id
    assert request.state.audit_diff["after"] == {"deleted": True}
