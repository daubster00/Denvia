"""POST /api/v1/qa/stream 통합 테스트 — FastAPI app.dependency_overrides + mock."""

import json
import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from api.src.integrations.openai.client import TokenUsage
from api.src.main import app
from api.src.deps.auth import get_current_user
from api.src.deps.redis import get_redis_quota, get_redis_runtime
from api.src.models.base import get_session
from api.src.models.user import User

NEEDS_OPENAI = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY 없음 — OpenAI 필요 테스트 skip",
)


def _make_user(user_id: int = 1, subscription_status: str = "admin") -> MagicMock:
    user = MagicMock(spec=User)
    user.id = user_id
    user.subscription_status = subscription_status
    user.daily_quota_override = None
    user.free_delay_override = None
    user.current_session_id = None
    user.admin_grade = "master"
    return user


def _make_db(log_id: int = 1):
    """AsyncGenerator를 반환하는 DB 세션 목 (FastAPI Depends 호환).

    killswitch_service.get_active_modes 가 첫 가드로 호출되므로
    db.execute() → result.scalars().all() 체인이 빈 리스트를 반환하도록 명시한다.
    """
    db = AsyncMock()

    async def _fake_refresh(obj):
        obj.id = log_id

    db.refresh = _fake_refresh
    db.add = MagicMock()

    # killswitch_service 기본 응답: 활성 모드 없음.
    _ks_result = MagicMock()
    _ks_result.scalars.return_value.all.return_value = []
    _ks_result.scalar_one_or_none.return_value = None
    _ks_result.scalar_one.return_value = 0
    db.execute = AsyncMock(return_value=_ks_result)

    async def _gen():
        yield db

    return _gen


def _make_admin_user(user_id: int = 1) -> MagicMock:
    """admin 사용자 — preflight 우회 (quota/delay 없음)."""
    user = MagicMock(spec=User)
    user.id = user_id
    user.subscription_status = "admin"
    user.daily_quota_override = None
    user.free_delay_override = None
    user.current_session_id = None
    user.admin_grade = "master"
    return user


def _make_redis_mock() -> AsyncMock:
    """preflight를 통과시키기 위한 Redis mock (admin user는 INCR 미발생)."""
    return AsyncMock()


def _parse_sse_lines(text: str) -> list[dict]:
    """SSE 응답 본문을 파싱해 이벤트 리스트로 반환한다."""
    events = []
    current: dict = {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("event:"):
            current["event"] = line[len("event:"):].strip()
        elif line.startswith("data:"):
            current["data"] = line[len("data:"):].strip()
        elif line == "" and current:
            events.append(current)
            current = {}
    if current:
        events.append(current)
    return events


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    """각 테스트 후 dependency_overrides를 초기화한다."""
    yield
    app.dependency_overrides.clear()


class TestQAStreamEndpoint:
    async def test_stream_endpoint_returns_sse_content_type(self):
        """POST /api/v1/qa/stream이 text/event-stream을 반환한다."""
        user = _make_user()
        db_gen = _make_db()
        redis_mock = _make_redis_mock()

        async def _mock_stream(self, db, user, question_text, **kwargs):
            yield {"event": "token", "data": json.dumps({"delta": "답변"})}
            yield {"event": "done", "data": json.dumps({"qa_log_id": 1, "total_tokens": 5, "cost_usd": 0.0, "latency_ms": 100, "rule_matched": False})}

        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = db_gen
        app.dependency_overrides[get_redis_quota] = lambda: redis_mock
        app.dependency_overrides[get_redis_runtime] = lambda: redis_mock

        from unittest.mock import patch
        with patch("api.src.services.qa_service.QAService.stream", _mock_stream):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post(
                    "/api/v1/qa/stream",
                    json={"question_text": "임플란트 보험"},
                )

        assert res.status_code == 200
        assert "text/event-stream" in res.headers.get("content-type", "")

    async def test_stream_response_contains_token_and_done_events(self):
        """응답 본문에 event: token과 event: done이 존재한다."""
        user = _make_user()
        db_gen = _make_db()
        redis_mock = _make_redis_mock()

        async def _mock_stream(self, db, user, question_text, **kwargs):
            yield {"event": "token", "data": json.dumps({"delta": "치료"})}
            yield {"event": "token", "data": json.dumps({"delta": "방법"})}
            yield {"event": "done", "data": json.dumps({"qa_log_id": 7, "total_tokens": 10, "cost_usd": 0.001, "latency_ms": 200, "rule_matched": False})}

        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = db_gen
        app.dependency_overrides[get_redis_quota] = lambda: redis_mock
        app.dependency_overrides[get_redis_runtime] = lambda: redis_mock

        from unittest.mock import patch
        with patch("api.src.services.qa_service.QAService.stream", _mock_stream):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post(
                    "/api/v1/qa/stream",
                    json={"question_text": "발치 후 주의사항"},
                )

        events = _parse_sse_lines(res.text)
        event_names = [e.get("event") for e in events]
        assert "token" in event_names
        assert "done" in event_names

    async def test_stream_rule_matched_question(self):
        """룰 매칭 질의 — event: rule_matched + token + done."""
        user = _make_user()
        db_gen = _make_db(log_id=20)
        redis_mock = _make_redis_mock()

        async def _mock_stream(self, db, user, question_text, **kwargs):
            yield {"event": "rule_matched", "data": json.dumps({"procedure_count": 1})}
            yield {"event": "token", "data": json.dumps({"delta": "장애인가산 300% 적용."})}
            yield {"event": "done", "data": json.dumps({"qa_log_id": 20, "total_tokens": 0, "cost_usd": 0.0, "latency_ms": 50, "rule_matched": True})}

        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = db_gen
        app.dependency_overrides[get_redis_quota] = lambda: redis_mock
        app.dependency_overrides[get_redis_runtime] = lambda: redis_mock

        from unittest.mock import patch
        with patch("api.src.services.qa_service.QAService.stream", _mock_stream):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post(
                    "/api/v1/qa/stream",
                    json={"question_text": "장애인 발치 가산 가능?"},
                )

        events = _parse_sse_lines(res.text)
        event_names = [e.get("event") for e in events]
        assert "rule_matched" in event_names
        assert "token" in event_names
        assert "done" in event_names

    async def test_stream_empty_question_returns_422(self):
        """question_text가 빈 문자열이면 인증 통과 후 422 Unprocessable Entity."""
        user = _make_user()
        db_gen = _make_db()
        redis_mock = _make_redis_mock()

        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = db_gen
        app.dependency_overrides[get_redis_quota] = lambda: redis_mock
        app.dependency_overrides[get_redis_runtime] = lambda: redis_mock

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.post(
                "/api/v1/qa/stream",
                json={"question_text": ""},
            )
        assert res.status_code == 422

    async def test_stream_question_too_long_returns_422(self):
        """question_text가 2001자 이상이면 422 Unprocessable Entity."""
        user = _make_user()
        db_gen = _make_db()
        redis_mock = _make_redis_mock()

        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = db_gen
        app.dependency_overrides[get_redis_quota] = lambda: redis_mock
        app.dependency_overrides[get_redis_runtime] = lambda: redis_mock

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.post(
                "/api/v1/qa/stream",
                json={"question_text": "a" * 2001},
            )
        assert res.status_code == 422
