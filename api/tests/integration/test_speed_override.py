"""Story 6.3 — preflight + _resolve_delay 결정 우선순위 통합 테스트.

epics.md 6.3 AC-7 명세 — 4 케이스:
1. 전역 3초 + override NULL → sleep(3.0)
2. 전역 3초 + override 1.5 → sleep(1.5)
3. 전역 3초 + override 0   → sleep 호출 안 함 (개별 OFF)
4. Pro + override 5         → sleep 호출 안 함 (paid_skip)
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
    """preflight 단계에서 asyncio.sleep을 mock한 뒤, 의도된 sleep 인자를 검증."""

    async def test_runtime_3s_no_override_sleeps_3(self, monkeypatch):
        """전역 runtime:free_delay=3 + free_delay_override=NULL → sleep(3.0)."""
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
        await svc.preflight(user=user, redis_quota=quota, redis_runtime=runtime)
        sleep_mock.assert_awaited_once()
        ((arg,), _) = sleep_mock.await_args
        assert arg == 3.0
        assert isinstance(arg, float)

    async def test_runtime_3s_with_override_15_sleeps_1_5(self, monkeypatch):
        """전역 3초 + 개별 1.5초 → sleep(1.5)."""
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
        await svc.preflight(user=user, redis_quota=quota, redis_runtime=runtime)
        sleep_mock.assert_awaited_once()
        ((arg,), _) = sleep_mock.await_args
        assert arg == 1.5
        assert isinstance(arg, float)

    async def test_runtime_3s_with_override_0_no_sleep(self, monkeypatch):
        """전역 3초 + 개별 0초 → sleep 호출 안 함 (개별 OFF, 0과 NULL 명확 구분)."""
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
        await svc.preflight(user=user, redis_quota=quota, redis_runtime=runtime)
        sleep_mock.assert_not_awaited()

    async def test_pro_with_override_no_sleep(self, monkeypatch):
        """Pro 사용자 + 개별 5초 → sleep 호출 안 함 (paid_skip)."""
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
        await svc.preflight(user=user, redis_quota=quota, redis_runtime=runtime)
        sleep_mock.assert_not_awaited()


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
