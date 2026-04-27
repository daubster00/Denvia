"""QAService.preflight() 단위 테스트 — fakeredis + Mock User (Story 2.3 AC-1~AC-5, AC-11)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fakeredis.aioredis import FakeRedis
from fastapi import HTTPException

from api.src.models.user import User
from api.src.services.qa_service import QAService, _today_key_kst


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


async def _make_quota_redis() -> FakeRedis:
    return FakeRedis(decode_responses=True)


async def _make_runtime_redis(values: dict | None = None) -> FakeRedis:
    r = FakeRedis(decode_responses=True)
    for k, v in (values or {}).items():
        await r.set(k, v)
    return r


class TestPreflightAdmin:
    @pytest.mark.asyncio
    async def test_admin_bypasses_quota_and_delay(self):
        """admin 사용자는 quota/delay를 모두 우회한다."""
        user = _make_user(subscription_status="admin")
        quota = await _make_quota_redis()
        runtime = await _make_runtime_redis()
        svc = QAService()
        await svc.preflight(user=user, redis_quota=quota, redis_runtime=runtime)
        # INCR 미발생 확인
        key = _today_key_kst(user.id)
        assert await quota.get(key) is None


class TestPreflightFreeUser:
    @pytest.mark.asyncio
    async def test_incr_and_expire_on_first_call(self):
        """첫 요청에 INCR=1 + EXPIRE 86400."""
        user = _make_user(subscription_status="free")
        quota = await _make_quota_redis()
        runtime = await _make_runtime_redis({
            "runtime:free_daily_quota": "10",
            "runtime:free_delay_enabled": "false",
        })
        svc = QAService()
        await svc.preflight(user=user, redis_quota=quota, redis_runtime=runtime)
        key = _today_key_kst(user.id)
        assert await quota.get(key) == "1"
        ttl = await quota.ttl(key)
        assert 0 < ttl <= 86400

    @pytest.mark.asyncio
    async def test_within_limit_no_exception(self):
        """한도 내 요청은 예외 없이 통과한다."""
        user = _make_user(subscription_status="free")
        quota = await _make_quota_redis()
        runtime = await _make_runtime_redis({
            "runtime:free_daily_quota": "10",
            "runtime:free_delay_enabled": "false",
        })
        svc = QAService()
        for _ in range(10):
            await svc.preflight(user=user, redis_quota=quota, redis_runtime=runtime)

    @pytest.mark.asyncio
    async def test_exceeds_limit_raises_429(self):
        """한도 초과 시 HTTPException(429, code=QUOTA_EXCEEDED) raise."""
        user = _make_user(subscription_status="free")
        quota = await _make_quota_redis()
        runtime = await _make_runtime_redis({
            "runtime:free_daily_quota": "3",
            "runtime:free_delay_enabled": "false",
            "runtime:show_upgrade_prompt": "true",
            "runtime:show_subscribe_button": "true",
        })
        svc = QAService()
        for _ in range(3):
            await svc.preflight(user=user, redis_quota=quota, redis_runtime=runtime)

        with pytest.raises(HTTPException) as exc_info:
            await svc.preflight(user=user, redis_quota=quota, redis_runtime=runtime)

        assert exc_info.value.status_code == 429
        detail = exc_info.value.detail
        assert detail["code"] == "QUOTA_EXCEEDED"
        assert detail["used_today"] == 4
        assert detail["daily_limit"] == 3
        assert "show_upgrade_prompt" in detail
        assert "+09:00" in detail["reset_at"]

    @pytest.mark.asyncio
    async def test_user_override_zero_blocks_immediately(self):
        """daily_quota_override=0은 첫 번째 요청부터 차단한다 (AC-2)."""
        user = _make_user(subscription_status="free", daily_quota_override=0)
        quota = await _make_quota_redis()
        runtime = await _make_runtime_redis({"runtime:free_delay_enabled": "false"})
        svc = QAService()
        with pytest.raises(HTTPException) as exc_info:
            await svc.preflight(user=user, redis_quota=quota, redis_runtime=runtime)
        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_free_delay_applied(self):
        """delay=2 설정 시 asyncio.sleep(2) 호출."""
        user = _make_user(subscription_status="free")
        quota = await _make_quota_redis()
        runtime = await _make_runtime_redis({
            "runtime:free_daily_quota": "10",
            "runtime:free_delay_enabled": "true",
            "runtime:free_delay": "2",
        })
        svc = QAService()
        with patch("api.src.services.qa_service.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await svc.preflight(user=user, redis_quota=quota, redis_runtime=runtime)
            mock_sleep.assert_awaited_once_with(2)

    @pytest.mark.asyncio
    async def test_free_delay_disabled_no_sleep(self):
        """runtime:free_delay_enabled=false 시 sleep 미호출."""
        user = _make_user(subscription_status="free")
        quota = await _make_quota_redis()
        runtime = await _make_runtime_redis({
            "runtime:free_daily_quota": "10",
            "runtime:free_delay_enabled": "false",
        })
        svc = QAService()
        with patch("api.src.services.qa_service.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await svc.preflight(user=user, redis_quota=quota, redis_runtime=runtime)
            mock_sleep.assert_not_awaited()


class TestPreflightProUser:
    @pytest.mark.asyncio
    async def test_pro_no_delay(self):
        """유료 사용자는 delay 미적용 (AC-3, NFR-P2)."""
        user = _make_user(subscription_status="pro")
        quota = await _make_quota_redis()
        runtime = await _make_runtime_redis({
            "runtime:pro_internal_cap": "500",
            "runtime:free_delay": "3",
        })
        svc = QAService()
        with patch("api.src.services.qa_service.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await svc.preflight(user=user, redis_quota=quota, redis_runtime=runtime)
            mock_sleep.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_pro_exceeds_internal_cap_raises_429(self):
        """유료 사용자 내부 안전망 초과 — code=QUOTA_EXCEEDED_INTERNAL_SAFETY_LIMIT (AC-5)."""
        user = _make_user(subscription_status="pro")
        quota = await _make_quota_redis()
        runtime = await _make_runtime_redis({"runtime:pro_internal_cap": "2"})
        svc = QAService()
        for _ in range(2):
            await svc.preflight(user=user, redis_quota=quota, redis_runtime=runtime)

        with pytest.raises(HTTPException) as exc_info:
            await svc.preflight(user=user, redis_quota=quota, redis_runtime=runtime)

        assert exc_info.value.status_code == 429
        detail = exc_info.value.detail
        assert detail["code"] == "QUOTA_EXCEEDED_INTERNAL_SAFETY_LIMIT"
        assert detail["show_upgrade_prompt"] is False
        assert detail["show_subscribe_button"] is False

    @pytest.mark.asyncio
    async def test_pro_quota_key_shared_pattern(self):
        """유료 사용자도 quota:user:{id}:{date} 동일 키 패턴 사용 — INCR 발생 확인 (AC-5)."""
        user = _make_user(subscription_status="pro")
        quota = await _make_quota_redis()
        runtime = await _make_runtime_redis({"runtime:pro_internal_cap": "500"})
        svc = QAService()
        await svc.preflight(user=user, redis_quota=quota, redis_runtime=runtime)
        key = _today_key_kst(user.id)
        assert await quota.get(key) == "1"
