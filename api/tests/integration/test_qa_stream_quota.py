"""POST /api/v1/qa/stream quota 분기 통합 테스트 — Story 2.3 (AC-1~AC-5)."""

import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient

from api.src.deps.auth import get_current_user
from api.src.deps.redis import get_redis_quota, get_redis_runtime
from api.src.main import app
from api.src.models.base import get_session
from api.src.models.user import User


def _make_user(
    user_id: int = 1,
    subscription_status: str = "free",
    daily_quota_override: int | None = None,
    free_delay_override: int | None = None,
) -> MagicMock:
    u = MagicMock(spec=User)
    u.id = user_id
    u.subscription_status = subscription_status
    u.daily_quota_override = daily_quota_override
    u.free_delay_override = free_delay_override
    return u


def _make_db(log_id: int = 1):
    db = AsyncMock()

    async def _fake_refresh(obj):
        obj.id = log_id

    db.refresh = _fake_refresh
    db.add = MagicMock()

    async def _gen():
        yield db

    return _gen


async def _mock_stream_ok(self, db, user, question_text):
    yield {"event": "token", "data": json.dumps({"delta": "답변"})}
    yield {"event": "done", "data": json.dumps({"qa_log_id": 1, "total_tokens": 5, "cost_usd": 0.0, "latency_ms": 10, "rule_matched": False})}


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


class TestStreamQuotaFreeUser:
    @pytest.mark.asyncio
    async def test_within_limit_returns_sse(self):
        """무료 사용자 — 한도(10) 이내 정상 SSE 응답."""
        user = _make_user(subscription_status="free")
        quota_redis = FakeRedis(decode_responses=True)
        runtime_redis = FakeRedis(decode_responses=True)
        await runtime_redis.set("runtime:free_daily_quota", "10")
        await runtime_redis.set("runtime:free_delay_enabled", "false")

        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = _make_db()
        app.dependency_overrides[get_redis_quota] = lambda: quota_redis
        app.dependency_overrides[get_redis_runtime] = lambda: runtime_redis

        with patch("api.src.services.qa_service.QAService.stream", _mock_stream_ok):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post("/api/v1/qa/stream", json={"question_text": "질문"})

        assert res.status_code == 200
        assert "text/event-stream" in res.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_exceeds_limit_returns_429(self):
        """무료 사용자 한도 초과 — 429 + code=QUOTA_EXCEEDED + details."""
        user = _make_user(user_id=100, subscription_status="free")
        quota_redis = FakeRedis(decode_responses=True)
        runtime_redis = FakeRedis(decode_responses=True)
        await runtime_redis.set("runtime:free_daily_quota", "3")
        await runtime_redis.set("runtime:free_delay_enabled", "false")
        await runtime_redis.set("runtime:show_upgrade_prompt", "true")
        await runtime_redis.set("runtime:show_subscribe_button", "true")

        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = _make_db()
        app.dependency_overrides[get_redis_quota] = lambda: quota_redis
        app.dependency_overrides[get_redis_runtime] = lambda: runtime_redis

        # 3회 소진
        with patch("api.src.services.qa_service.QAService.stream", _mock_stream_ok):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                for _ in range(3):
                    await client.post("/api/v1/qa/stream", json={"question_text": "질문"})
                # 4번째 = 초과
                res = await client.post("/api/v1/qa/stream", json={"question_text": "초과"})

        assert res.status_code == 429
        body = res.json()
        assert body["code"] == "QUOTA_EXCEEDED"
        assert "details" in body
        assert body["details"]["daily_limit"] == 3
        assert body["details"]["used_today"] == 4
        assert "+09:00" in body["details"]["reset_at"]
        assert body["details"]["show_upgrade_prompt"] is True

    @pytest.mark.asyncio
    async def test_user_override_quota_respected(self):
        """users.daily_quota_override=2 사용자 — 3회째 429 (override 우선, AC-2)."""
        user = _make_user(user_id=200, subscription_status="free", daily_quota_override=2)
        quota_redis = FakeRedis(decode_responses=True)
        runtime_redis = FakeRedis(decode_responses=True)
        await runtime_redis.set("runtime:free_daily_quota", "10")
        await runtime_redis.set("runtime:free_delay_enabled", "false")

        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = _make_db()
        app.dependency_overrides[get_redis_quota] = lambda: quota_redis
        app.dependency_overrides[get_redis_runtime] = lambda: runtime_redis

        with patch("api.src.services.qa_service.QAService.stream", _mock_stream_ok):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                for _ in range(2):
                    r = await client.post("/api/v1/qa/stream", json={"question_text": "질문"})
                    assert r.status_code == 200
                res = await client.post("/api/v1/qa/stream", json={"question_text": "초과"})

        assert res.status_code == 429
        assert res.json()["code"] == "QUOTA_EXCEEDED"

    @pytest.mark.asyncio
    async def test_runtime_quota_5_blocks_on_6th(self):
        """runtime:free_daily_quota=5 설정 시 6번째 요청 차단."""
        user = _make_user(user_id=300, subscription_status="free")
        quota_redis = FakeRedis(decode_responses=True)
        runtime_redis = FakeRedis(decode_responses=True)
        await runtime_redis.set("runtime:free_daily_quota", "5")
        await runtime_redis.set("runtime:free_delay_enabled", "false")

        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = _make_db()
        app.dependency_overrides[get_redis_quota] = lambda: quota_redis
        app.dependency_overrides[get_redis_runtime] = lambda: runtime_redis

        with patch("api.src.services.qa_service.QAService.stream", _mock_stream_ok):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                for _ in range(5):
                    r = await client.post("/api/v1/qa/stream", json={"question_text": "질문"})
                    assert r.status_code == 200
                res = await client.post("/api/v1/qa/stream", json={"question_text": "초과"})

        assert res.status_code == 429

    @pytest.mark.asyncio
    async def test_delay_disabled_no_sleep(self):
        """runtime:free_delay_enabled=false — sleep 미적용 확인."""
        user = _make_user(user_id=400, subscription_status="free")
        quota_redis = FakeRedis(decode_responses=True)
        runtime_redis = FakeRedis(decode_responses=True)
        await runtime_redis.set("runtime:free_daily_quota", "10")
        await runtime_redis.set("runtime:free_delay_enabled", "false")

        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = _make_db()
        app.dependency_overrides[get_redis_quota] = lambda: quota_redis
        app.dependency_overrides[get_redis_runtime] = lambda: runtime_redis

        with patch("api.src.services.qa_service.QAService.stream", _mock_stream_ok):
            with patch("api.src.services.qa_service.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    await client.post("/api/v1/qa/stream", json={"question_text": "질문"})
                mock_sleep.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delay_applied_sleep_called(self):
        """runtime:free_delay=2 — asyncio.sleep(2) 호출 확인 (실제 대기 없이 mock)."""
        user = _make_user(user_id=500, subscription_status="free")
        quota_redis = FakeRedis(decode_responses=True)
        runtime_redis = FakeRedis(decode_responses=True)
        await runtime_redis.set("runtime:free_daily_quota", "10")
        await runtime_redis.set("runtime:free_delay_enabled", "true")
        await runtime_redis.set("runtime:free_delay", "2")

        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = _make_db()
        app.dependency_overrides[get_redis_quota] = lambda: quota_redis
        app.dependency_overrides[get_redis_runtime] = lambda: runtime_redis

        with patch("api.src.services.qa_service.QAService.stream", _mock_stream_ok):
            with patch("api.src.services.qa_service.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.post("/api/v1/qa/stream", json={"question_text": "질문"})
                mock_sleep.assert_awaited_once_with(2)
        assert res.status_code == 200


class TestStreamQuotaProUser:
    @pytest.mark.asyncio
    async def test_pro_user_no_sleep(self):
        """유료 사용자 — delay 미적용 (NFR-P2)."""
        user = _make_user(user_id=600, subscription_status="pro")
        quota_redis = FakeRedis(decode_responses=True)
        runtime_redis = FakeRedis(decode_responses=True)
        await runtime_redis.set("runtime:pro_internal_cap", "500")

        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = _make_db()
        app.dependency_overrides[get_redis_quota] = lambda: quota_redis
        app.dependency_overrides[get_redis_runtime] = lambda: runtime_redis

        with patch("api.src.services.qa_service.QAService.stream", _mock_stream_ok):
            with patch("api.src.services.qa_service.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.post("/api/v1/qa/stream", json={"question_text": "질문"})
                mock_sleep.assert_not_awaited()
        assert res.status_code == 200

    @pytest.mark.asyncio
    async def test_pro_exceeds_internal_cap_returns_429(self):
        """유료 사용자 501회 초과 — 429 + code=QUOTA_EXCEEDED_INTERNAL_SAFETY_LIMIT."""
        user = _make_user(user_id=700, subscription_status="pro")
        quota_redis = FakeRedis(decode_responses=True)
        runtime_redis = FakeRedis(decode_responses=True)
        await runtime_redis.set("runtime:pro_internal_cap", "2")

        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = _make_db()
        app.dependency_overrides[get_redis_quota] = lambda: quota_redis
        app.dependency_overrides[get_redis_runtime] = lambda: runtime_redis

        with patch("api.src.services.qa_service.QAService.stream", _mock_stream_ok):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                for _ in range(2):
                    r = await client.post("/api/v1/qa/stream", json={"question_text": "질문"})
                    assert r.status_code == 200
                res = await client.post("/api/v1/qa/stream", json={"question_text": "초과"})

        assert res.status_code == 429
        body = res.json()
        assert body["code"] == "QUOTA_EXCEEDED_INTERNAL_SAFETY_LIMIT"
        assert body["details"]["show_upgrade_prompt"] is False
        assert body["details"]["show_subscribe_button"] is False
