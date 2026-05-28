"""Story 6.3 — preflight + _resolve_delay 결정 우선순위 통합 테스트.

epics.md 6.3 AC-7 명세 — 4 케이스 (체감-지연 정책 적용 후):
1. 전역 3초 + override NULL → PreflightResult.delay_seconds=3.0, deadline_perf=t+3
2. 전역 3초 + override 1.5 → delay_seconds=1.5, source=user_override
3. 전역 3초 + override 0   → delay_seconds=0.0, deadline_perf=None (개별 OFF)
4. Pro + override 5         → delay_seconds=0.0, deadline_perf=None (paid_skip)

preflight 는 더이상 직접 sleep 하지 않는다. 실제 sleep 은 stream() 이 첫 토큰 emit 직전 수행.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fakeredis.aioredis import FakeRedis

from api.src.models.user import User
from api.src.services import qa_service
from api.src.services.qa_service import QAService


def _make_user(
    user_id: int = 1,
    subscription_status: str = "free",
    free_delay_override: Decimal | None = None,
) -> MagicMock:
    u = MagicMock(spec=User)
    u.id = user_id
    u.subscription_status = subscription_status
    u.daily_quota_override = None
    u.free_delay_override = free_delay_override
    # spec=User 만으로는 ORM 속성이 truthy MagicMock 으로 채워져 throttle 분기를 잘못 켠다.
    u.anomaly_throttled_at = None
    return u


async def _make_quota_redis() -> FakeRedis:
    return FakeRedis(decode_responses=True)


async def _make_runtime_redis(values: dict | None = None) -> FakeRedis:
    r = FakeRedis(decode_responses=True)
    for k, v in (values or {}).items():
        await r.set(k, v)
    return r


@pytest.mark.asyncio
class TestSpeedOverridePreflight:
    """preflight 가 PreflightResult 에 채우는 delay_seconds/delay_source/deadline_perf 를 검증.

    preflight 는 더이상 sleep 하지 않음 — sleep mock 이 호출되지 않아야 정상.
    """

    async def test_runtime_3s_no_override_sets_3(self, monkeypatch):
        """전역 runtime:free_delay=3 + override NULL → delay=3.0, source=runtime, deadline 설정."""
        import time as _time
        sleep_mock = AsyncMock()
        monkeypatch.setattr("api.src.services.qa_service.asyncio.sleep", sleep_mock)
        user = _make_user(free_delay_override=None)
        quota = await _make_quota_redis()
        runtime = await _make_runtime_redis({
            "runtime:free_daily_quota": "10",
            "runtime:free_delay_enabled": "true",
            "runtime:free_delay": "3",
        })
        svc = QAService()
        t_before = _time.perf_counter()
        result = await svc.preflight(user=user, redis_quota=quota, redis_runtime=runtime)
        sleep_mock.assert_not_awaited()
        assert result.delay_seconds == 3.0
        assert result.delay_source == "runtime"
        assert result.deadline_perf is not None
        assert t_before + 2.8 <= result.deadline_perf <= t_before + 3.5

    async def test_runtime_3s_with_override_15_sets_1_5(self, monkeypatch):
        """전역 3초 + 개별 1.5초 → delay=1.5, source=user_override."""
        sleep_mock = AsyncMock()
        monkeypatch.setattr("api.src.services.qa_service.asyncio.sleep", sleep_mock)
        user = _make_user(free_delay_override=Decimal("1.5"))
        quota = await _make_quota_redis()
        runtime = await _make_runtime_redis({
            "runtime:free_daily_quota": "10",
            "runtime:free_delay_enabled": "true",
            "runtime:free_delay": "3",
        })
        svc = QAService()
        result = await svc.preflight(user=user, redis_quota=quota, redis_runtime=runtime)
        sleep_mock.assert_not_awaited()
        assert result.delay_seconds == 1.5
        assert result.delay_source == "user_override"
        assert result.deadline_perf is not None

    async def test_runtime_3s_with_override_0_no_deadline(self, monkeypatch):
        """전역 3초 + 개별 0초 → delay=0.0, deadline_perf=None (개별 OFF)."""
        sleep_mock = AsyncMock()
        monkeypatch.setattr("api.src.services.qa_service.asyncio.sleep", sleep_mock)
        user = _make_user(free_delay_override=Decimal("0.0"))
        quota = await _make_quota_redis()
        runtime = await _make_runtime_redis({
            "runtime:free_daily_quota": "10",
            "runtime:free_delay_enabled": "true",
            "runtime:free_delay": "3",
        })
        svc = QAService()
        result = await svc.preflight(user=user, redis_quota=quota, redis_runtime=runtime)
        sleep_mock.assert_not_awaited()
        assert result.delay_seconds == 0.0
        assert result.deadline_perf is None
        assert result.delay_source == "user_override"

    async def test_pro_with_override_no_deadline(self, monkeypatch):
        """Pro 사용자 + 개별 5초 → delay=0.0, deadline_perf=None (paid_skip)."""
        sleep_mock = AsyncMock()
        monkeypatch.setattr("api.src.services.qa_service.asyncio.sleep", sleep_mock)
        user = _make_user(
            subscription_status="pro", free_delay_override=Decimal("5.0")
        )
        quota = await _make_quota_redis()
        runtime = await _make_runtime_redis({
            "runtime:pro_internal_cap": "500",
        })
        svc = QAService()
        result = await svc.preflight(user=user, redis_quota=quota, redis_runtime=runtime)
        sleep_mock.assert_not_awaited()
        assert result.delay_seconds == 0.0
        assert result.deadline_perf is None
        assert result.delay_source == "paid_skip"


@pytest.mark.asyncio
class TestResolveDelayDecimalReturn:
    """_resolve_delay이 Decimal을 반환함을 별도로 검증."""

    async def test_user_override_returns_decimal_unchanged(self):
        user = _make_user(free_delay_override=Decimal("1.5"))
        runtime = await _make_runtime_redis({"runtime:free_delay": "3"})
        delay, src = await qa_service._resolve_delay(user, runtime)
        assert isinstance(delay, Decimal)
        assert delay == Decimal("1.5")
        assert src == "user_override"

    async def test_paid_skip_returns_decimal_zero(self):
        user = _make_user(
            subscription_status="pro", free_delay_override=Decimal("5.0")
        )
        runtime = await _make_runtime_redis({})
        delay, src = await qa_service._resolve_delay(user, runtime)
        assert isinstance(delay, Decimal)
        assert delay == Decimal("0")
        assert src == "paid_skip"
