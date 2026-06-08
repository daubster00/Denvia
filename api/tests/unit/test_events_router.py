"""POST /api/v1/events/client 단위 테스트 — Story 2.5.

structlog.testing.capture_logs()로 로그 기록을 직접 검증한다.
"""

import pytest
import structlog
from structlog.testing import capture_logs
from unittest.mock import MagicMock

from api.src.models.user import User
from api.src.routers.events import log_client_event
from api.src.schemas.events import ClientEventRequest


def _make_user(user_id: int = 42) -> MagicMock:
    u = MagicMock(spec=User)
    u.id = user_id
    u.subscription_status = "pro"
    u.current_session_id = None
    u.admin_grade = "master"
    return u


@pytest.mark.asyncio
async def test_인증_사용자_POST_204_and_structlog_event_기록():
    """인증 사용자 → structlog에 qa.conversation.reset 이벤트 기록."""
    body = ClientEventRequest(event="qa.conversation.reset")
    user = _make_user(user_id=99)

    with capture_logs() as cap:
        result = await log_client_event(body=body, user=user)

    assert result is None  # 204 No Content
    assert len(cap) == 1
    assert cap[0]["event"] == "qa.conversation.reset"
    assert cap[0]["user_id"] == 99
    assert cap[0].get("client_trace_id") is None


@pytest.mark.asyncio
async def test_trace_id_없는_요청_정상_처리():
    """trace_id: None 포함 요청 → client_trace_id=None 기록 정상 처리."""
    body = ClientEventRequest(event="qa.conversation.reset", trace_id=None)
    user = _make_user(user_id=1)

    with capture_logs() as cap:
        await log_client_event(body=body, user=user)

    assert cap[0]["client_trace_id"] is None


@pytest.mark.asyncio
async def test_trace_id_있는_요청_structlog에_첨부():
    """trace_id: 'abc-123' 포함 요청 → structlog에 client_trace_id='abc-123' 첨부."""
    body = ClientEventRequest(event="qa.conversation.reset", trace_id="abc-123")
    user = _make_user(user_id=7)

    with capture_logs() as cap:
        await log_client_event(body=body, user=user)

    assert cap[0]["client_trace_id"] == "abc-123"
    assert cap[0]["user_id"] == 7
