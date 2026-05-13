"""야간 차단 토글 통합 테스트 — Story 4.2 (AC-3·5).

Redis DB 3 키 SET → notification_service.send() → notification_queue 행 검증.
4.1 dispatch_deferred 경로 회귀 영향 없음 확인.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.src.integrations.messaging.notification_service import NotificationService
from api.src.models.notification_queue import STATUS_DEFERRED, STATUS_SENT


# ── 공통 헬퍼 ───────────────────────────────────────────────────────────────

def _make_provider(success: bool = True):
    provider = AsyncMock()
    provider.send_alimtalk.return_value = MagicMock(
        success=success, provider_response_code="OK" if success else "ERR", message_id="m1"
    )
    provider.send_sms.return_value = None
    return provider


def _make_rate_redis():
    r = AsyncMock()
    r.incr.return_value = 1
    r.expire.return_value = True
    return r


def _make_runtime_redis(enabled: str = "true", active: str | None = None):
    r = AsyncMock()
    r.get.side_effect = [enabled, active]
    return r


def _make_session_factory():
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    factory = MagicMock(return_value=session)
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory, session


# ── 실 Redis 시뮬레이션 통합 테스트 ──────────────────────────────────────────

@pytest.mark.asyncio
class TestNightBlockToggleIntegration:
    async def test_active_true_defers_notice_and_enqueues_row(self):
        """Redis active=true → NOTICE 발송 → notification_queue DEFERRED 행 INSERT (AC-3)."""
        provider = _make_provider()
        factory, session = _make_session_factory()

        service = NotificationService(
            provider,
            factory,
            _make_rate_redis(),
            runtime_redis=_make_runtime_redis(enabled="true", active="true"),
        )

        result = await service.send(
            user_id=42,
            phone="01011112222",
            template_code="notice.generic",
            variables={"title": "야간공지", "body": "내용"},
            idempotency_key="int-test:42:001",
        )

        assert result.status == STATUS_DEFERRED
        assert result.deferred_until is not None
        # _enqueue → session.execute 호출로 DB 저장 확인
        session.execute.assert_awaited()
        provider.send_alimtalk.assert_not_awaited()

    async def test_active_false_sends_notice_immediately(self):
        """Redis active=false → NOTICE 발송 → STATUS_SENT (AC-3 1차 게이트 통과)."""
        provider = _make_provider(success=True)
        factory, session = _make_session_factory()

        service = NotificationService(
            provider,
            factory,
            _make_rate_redis(),
            runtime_redis=_make_runtime_redis(enabled="true", active="false"),
        )

        result = await service.send(
            user_id=42,
            phone="01011112222",
            template_code="notice.generic",
            variables={"title": "낮공지", "body": "내용"},
            idempotency_key="int-test:42:002",
        )

        assert result.status == STATUS_SENT
        provider.send_alimtalk.assert_awaited_once()

    async def test_toggle_off_sends_notice_at_night(self):
        """마스터 토글 OFF → 시각 무관 즉시 발송 (AC-6)."""
        provider = _make_provider(success=True)
        factory, session = _make_session_factory()

        service = NotificationService(
            provider,
            factory,
            _make_rate_redis(),
            runtime_redis=_make_runtime_redis(enabled="false", active="true"),
        )

        with patch(
            "api.src.integrations.messaging.notification_service.is_night_block_time",
            return_value=True,
        ):
            result = await service.send(
                user_id=42,
                phone="01011112222",
                template_code="notice.generic",
                variables={"title": "토글OFF공지", "body": "내용"},
                idempotency_key="int-test:42:003",
            )

        assert result.status == STATUS_SENT
        provider.send_alimtalk.assert_awaited_once()


# ── AC-5 회귀: 4.2 변경이 dispatch_deferred 경로에 회귀 없음 ─────────────────

@pytest.mark.asyncio
class TestDispatchDeferredRegression:
    async def test_service_send_daytime_from_dispatch_deferred_context(self):
        """4.1 회귀: dispatch_deferred가 send()를 호출하는 컨텍스트(낮) — 정상 발송.

        dispatch_deferred는 deferred_until이 지난 NOTICE 행을 다시 send()한다.
        4.2의 urgent=False(default), 낮 시간 시뮬레이션이면 즉시 발송되어야 한다.
        """
        provider = _make_provider(success=True)
        factory, session = _make_session_factory()

        service = NotificationService(
            provider,
            factory,
            _make_rate_redis(),
            # active=false → 낮 시간으로 간주, 즉시 발송
            runtime_redis=_make_runtime_redis(enabled="true", active="false"),
        )

        # dispatch_deferred에서 send() 호출하는 것과 동일한 시그니처
        result = await service.send(
            user_id=10,
            phone="01099998888",
            template_code="notice.generic",
            variables={"title": "공지재발송", "body": "내용"},
            idempotency_key="dispatch-regression:10:001",
            urgent=False,  # dispatch_deferred는 urgent=False(기본값)
        )

        assert result.status == STATUS_SENT
        provider.send_alimtalk.assert_awaited_once()

    async def test_service_send_nighttime_from_dispatch_deferred_context(self):
        """4.1 회귀: dispatch_deferred 발화 시각이 여전히 야간(edge case) — 재지연.

        08:05 KST dispatch_deferred가 실행될 때는 낮이지만, active가 여전히 true인
        edge case에서도 행이 다시 deferred되어 데이터 손실 없음.
        """
        provider = _make_provider(success=True)
        factory, session = _make_session_factory()

        service = NotificationService(
            provider,
            factory,
            _make_rate_redis(),
            runtime_redis=_make_runtime_redis(enabled="true", active="true"),
        )

        result = await service.send(
            user_id=10,
            phone="01099998888",
            template_code="notice.generic",
            variables={"title": "재지연공지", "body": "내용"},
            idempotency_key="dispatch-regression:10:002",
        )

        # 여전히 야간 active=true → 다시 deferred (데이터 손실 없음)
        assert result.status == STATUS_DEFERRED
        session.execute.assert_awaited()
