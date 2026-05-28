"""QAService.preflight() 단위 테스트 — fakeredis + Mock User (Story 2.3 AC-1~AC-5, AC-11)."""

import time as _time

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fakeredis.aioredis import FakeRedis
from fastapi import HTTPException

from api.src.models.user import User
from api.src.services.qa_service import (
    PreflightResult,
    QAService,
    _today_key_kst,
    catch_up_to_deadline,
)


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
    # spec=User 만으로는 ORM 속성이 truthy MagicMock 으로 채워지므로 throttle 분기를 잘못 켠다.
    u.anomaly_throttled_at = None
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
    async def test_free_delay_sets_deadline_not_sleep(self):
        """delay=2 설정 시 preflight 는 sleep 하지 않고 PreflightResult.deadline_perf 만 설정.

        실제 sleep 은 stream() 이 첫 토큰 emit 직전에 catch_up_to_deadline 으로 수행 —
        "관리자 딜레이 = 사용자 체감 지연" 정책. preflight 자체는 비차단.
        """
        import time as _time
        user = _make_user(subscription_status="free")
        quota = await _make_quota_redis()
        runtime = await _make_runtime_redis({
            "runtime:free_daily_quota": "10",
            "runtime:free_delay_enabled": "true",
            "runtime:free_delay": "2",
        })
        svc = QAService()
        t_before = _time.perf_counter()
        with patch("api.src.services.qa_service.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await svc.preflight(user=user, redis_quota=quota, redis_runtime=runtime)
            mock_sleep.assert_not_awaited()
        assert result.delay_seconds == 2.0
        assert result.delay_source == "runtime"
        assert result.deadline_perf is not None
        # deadline 은 호출 시점 + 2초 부근.
        assert t_before + 1.8 <= result.deadline_perf <= t_before + 2.5

    @pytest.mark.asyncio
    async def test_free_delay_disabled_no_deadline(self):
        """runtime:free_delay_enabled=false 시 sleep 미호출 + deadline_perf=None."""
        user = _make_user(subscription_status="free")
        quota = await _make_quota_redis()
        runtime = await _make_runtime_redis({
            "runtime:free_daily_quota": "10",
            "runtime:free_delay_enabled": "false",
        })
        svc = QAService()
        with patch("api.src.services.qa_service.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await svc.preflight(user=user, redis_quota=quota, redis_runtime=runtime)
            mock_sleep.assert_not_awaited()
        assert result.deadline_perf is None
        assert result.delay_seconds == 0.0


class TestCatchUpToDeadline:
    """체감 지연 catch-up 헬퍼 — stream() 첫 토큰 emit 직전 호출되는 함수."""

    @pytest.mark.asyncio
    async def test_none_preflight_is_noop(self):
        """preflight_result=None ⇒ sleep 없이 즉시 반환."""
        with patch("api.src.services.qa_service.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await catch_up_to_deadline(None)
            mock_sleep.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_none_deadline_is_noop(self):
        """deadline_perf=None (admin/delay=0) ⇒ sleep 없이 즉시 반환."""
        pr = PreflightResult(
            throttled=False, throttle_just_applied=False,
            deadline_perf=None, delay_seconds=0.0, delay_source="paid_skip",
        )
        with patch("api.src.services.qa_service.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await catch_up_to_deadline(pr)
            mock_sleep.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_deadline_already_passed_skips_sleep(self):
        """이미 deadline 초과(AI 가 더 오래 걸린 경우) ⇒ sleep 생략 — 즉시 출력."""
        pr = PreflightResult(
            throttled=False, throttle_just_applied=False,
            deadline_perf=_time.perf_counter() - 0.5,  # 0.5s 이전 시각 = 이미 초과
            delay_seconds=2.0, delay_source="runtime",
        )
        with patch("api.src.services.qa_service.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await catch_up_to_deadline(pr)
            mock_sleep.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_deadline_in_future_sleeps_remainder(self):
        """deadline 미도달 ⇒ 남은 시간만큼만 sleep."""
        pr = PreflightResult(
            throttled=False, throttle_just_applied=False,
            deadline_perf=_time.perf_counter() + 1.0,  # 약 1.0초 뒤
            delay_seconds=2.0, delay_source="runtime",
        )
        with patch("api.src.services.qa_service.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await catch_up_to_deadline(pr)
            mock_sleep.assert_awaited_once()
            ((arg,), _) = mock_sleep.await_args
            # 호출 직전 perf_counter 기준 잔여 시간 = 약 1.0초 (작업 지연으로 [0.7, 1.05] 범위 허용).
            assert 0.7 <= arg <= 1.05


class TestPreflightProUser:
    @pytest.mark.asyncio
    async def test_pro_no_delay(self):
        """유료 사용자는 delay 미적용 (AC-3, NFR-P2) — deadline 도 None."""
        user = _make_user(subscription_status="pro")
        quota = await _make_quota_redis()
        runtime = await _make_runtime_redis({
            "runtime:pro_internal_cap": "500",
            "runtime:free_delay": "3",
        })
        svc = QAService()
        with patch("api.src.services.qa_service.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await svc.preflight(user=user, redis_quota=quota, redis_runtime=runtime)
            mock_sleep.assert_not_awaited()
        assert result.deadline_perf is None
        assert result.delay_seconds == 0.0
        assert result.delay_source == "paid_skip"

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
