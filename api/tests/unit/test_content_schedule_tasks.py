"""content_schedule_tasks 유닛 테스트 — toggle_night_block_on/off (Story 4.2)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest


def _make_redis_mock():
    """redis.asyncio 클라이언트 mock."""
    mock = AsyncMock()
    mock.set = AsyncMock(return_value=True)
    mock.aclose = AsyncMock()
    return mock


class TestSetActive:
    """_set_active(active) 비동기 헬퍼 — Redis SET 동작 검증."""

    @pytest.mark.asyncio
    async def test_set_active_true_sets_true_in_redis(self):
        """active=True → Redis SET night_block_active='true'."""
        mock_redis = _make_redis_mock()

        with patch("redis.asyncio.from_url", return_value=mock_redis):
            from api.src.workers.content_schedule_tasks import _set_active
            result = await _set_active(True)

        mock_redis.set.assert_awaited_once()
        _key, value = mock_redis.set.call_args[0]
        assert value == "true"
        assert result == {"active": True}
        mock_redis.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_set_active_false_sets_false_in_redis(self):
        """active=False → Redis SET night_block_active='false'."""
        mock_redis = _make_redis_mock()

        with patch("redis.asyncio.from_url", return_value=mock_redis):
            from api.src.workers.content_schedule_tasks import _set_active
            result = await _set_active(False)

        _key, value = mock_redis.set.call_args[0]
        assert value == "false"
        assert result == {"active": False}

    @pytest.mark.asyncio
    async def test_idempotent_double_call(self):
        """동일 active 값으로 2회 호출 — 최종 SET 값 동일 (idempotent)."""
        mock_redis = _make_redis_mock()

        with patch("redis.asyncio.from_url", return_value=mock_redis):
            from api.src.workers.content_schedule_tasks import _set_active
            result1 = await _set_active(True)
            # from_url은 호출마다 새 mock 반환 — 두 번째 호출도 같은 값 SET
            result2 = await _set_active(True)

        assert result1 == {"active": True}
        assert result2 == {"active": True}

    @pytest.mark.asyncio
    async def test_redis_set_exception_propagates(self):
        """Redis SET 예외 → 예외 전파 (Celery 재시도 정책에 위임)."""
        mock_redis = _make_redis_mock()
        mock_redis.set.side_effect = Exception("redis 장애")

        with patch("redis.asyncio.from_url", return_value=mock_redis):
            from api.src.workers.content_schedule_tasks import _set_active
            with pytest.raises(Exception, match="redis 장애"):
                await _set_active(True)

        # 예외가 발생해도 aclose는 finally에서 실행되어야 함
        mock_redis.aclose.assert_awaited_once()
