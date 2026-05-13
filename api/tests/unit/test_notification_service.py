"""NotificationService 유닛 테스트 — 폴백·야간차단·레이트리밋 로직 검증."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.src.integrations.messaging.notification_service import (
    NotificationService,
    _mask_phone,
)
from api.src.integrations.messaging.port import AlimtalkResult
from api.src.integrations.messaging.templates import TemplateCategory
from api.src.services.runtime_config_service import NightBlockSettings


# ── Fixtures ────────────────────────────────────────────────────────────────

def _make_alimtalk_result(success: bool) -> AlimtalkResult:
    return AlimtalkResult(
        success=success,
        provider_response_code="OK" if success else "ERR",
        message_id="msg-1" if success else None,
    )


def _make_provider(alimtalk_success: bool = True, sms_raises: bool = False):
    provider = AsyncMock()
    provider.send_alimtalk.return_value = _make_alimtalk_result(alimtalk_success)
    if sms_raises:
        provider.send_sms.side_effect = Exception("SMS 발송 실패")
    else:
        provider.send_sms.return_value = None
    return provider


def _make_redis(per_min_count: int = 1, per_hour_count: int = 1):
    """Redis mock — incr 호출 시 지정된 count 반환 (DB 2 rate limit용)."""
    redis = AsyncMock()
    redis.incr.return_value = per_min_count
    redis.expire.return_value = True
    return redis


def _make_runtime_redis(enabled: bool = True, active: bool | None = None):
    """runtime Redis mock (DB 3) — get_night_block_settings()가 사용하는 키 반환.

    active=None이면 active 키가 존재하지 않는 상태(이중 안전망 폴백 트리거).
    """
    redis = AsyncMock()
    enabled_raw = "true" if enabled else "false"
    active_raw = None if active is None else ("true" if active else "false")
    redis.get.side_effect = [enabled_raw, active_raw]
    return redis


def _make_session_factory():
    """async_session_factory mock — enqueue 시 DB 호출 성공 처리."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    factory = MagicMock(return_value=session)
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory, session


# ── Tests: Phone Masking ─────────────────────────────────────────────────────

class TestMaskPhone:
    def test_masks_all_but_last_4(self):
        assert _mask_phone("01012345678") == "****5678"

    def test_short_phone_returns_mask(self):
        assert _mask_phone("010") == "****"


# ── Tests: Alimtalk 발송 성공 경로 ──────────────────────────────────────────

class TestNotificationServiceAlimtalkSuccess:
    @pytest.mark.asyncio
    async def test_alimtalk_success_inserts_sent_record(self):
        """알림톡 성공 시 STATUS_SENT 레코드가 notification_queue에 삽입된다 (AC-6 Decision 1A)."""
        provider = _make_provider(alimtalk_success=True)
        factory, session = _make_session_factory()
        redis = _make_redis(per_min_count=1)
        runtime_redis = _make_runtime_redis(enabled=True, active=False)

        service = NotificationService(provider, factory, redis, runtime_redis=runtime_redis)

        await service.send(
            user_id=1,
            phone="01012345678",
            template_code="billing.first_charge_success",
            variables={"amount_krw": "9900", "next_charge_at": "2026-05-23"},
            idempotency_key="payment:1:success",
        )

        provider.send_alimtalk.assert_awaited_once()
        provider.send_sms.assert_not_awaited()
        # AC-6 Decision 1A: 성공 시 STATUS_SENT 기록 → session.execute 호출됨
        session.execute.assert_awaited()


# ── Tests: SMS 폴백 ──────────────────────────────────────────────────────────

class TestNotificationServiceSmsFallback:
    @pytest.mark.asyncio
    async def test_alimtalk_failure_triggers_sms_fallback(self):
        """알림톡 실패 시 SMS 폴백이 호출된다."""
        provider = _make_provider(alimtalk_success=False)
        factory, session = _make_session_factory()
        redis = _make_redis(per_min_count=1)
        runtime_redis = _make_runtime_redis(enabled=True, active=False)

        service = NotificationService(provider, factory, redis, runtime_redis=runtime_redis)

        await service.send(
            user_id=1,
            phone="01012345678",
            template_code="billing.retry_failed_1",
            variables={},
            idempotency_key="payment:1:retry1",
        )

        provider.send_alimtalk.assert_awaited()
        provider.send_sms.assert_awaited_once()
        # AC-6 Decision 1A: SMS 성공 시에도 STATUS_SENT 기록 → session.execute 호출됨
        session.execute.assert_awaited()

    @pytest.mark.asyncio
    async def test_both_fail_enqueues_failed_status(self):
        """알림톡 + SMS 모두 실패 시 notification_queue에 failed로 INSERT된다."""
        provider = _make_provider(alimtalk_success=False, sms_raises=True)
        factory, session = _make_session_factory()
        redis = _make_redis(per_min_count=1)
        runtime_redis = _make_runtime_redis(enabled=True, active=False)

        service = NotificationService(provider, factory, redis, runtime_redis=runtime_redis)

        with patch("sentry_sdk.capture_message"):
            await service.send(
                user_id=1,
                phone="01012345678",
                template_code="billing.retry_failed_1",
                variables={},
                idempotency_key="payment:1:retry1",
            )

        # enqueue가 실행되어야 함
        session.execute.assert_awaited()


# ── Tests: 야간 차단 ─────────────────────────────────────────────────────────

class TestNotificationServiceNightBlock:
    # ── 4.1 회귀 케이스 ─────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_notice_category_deferred_at_night(self):
        """4.1 회귀: NOTICE 카테고리는 야간(21~08 KST)에 deferred로 큐 저장된다.

        runtime_redis가 enabled=True + active=None을 반환하면
        is_night_block_time() 폴백(이중 안전망)이 호출된다.
        """
        provider = _make_provider()
        factory, session = _make_session_factory()
        redis = _make_redis(per_min_count=1)
        # active=None → is_night_block_time() 폴백 트리거
        runtime_redis = _make_runtime_redis(enabled=True, active=None)

        service = NotificationService(provider, factory, redis, runtime_redis=runtime_redis)

        with patch(
            "api.src.integrations.messaging.notification_service.is_night_block_time",
            return_value=True,
        ):
            await service.send(
                user_id=1,
                phone="01012345678",
                template_code="notice.generic",
                variables={"title": "공지", "body": "내용"},
                idempotency_key="notice:1:20260423",
            )

        # 야간 차단 → 즉시 발송하지 않음
        provider.send_alimtalk.assert_not_awaited()
        # deferred 큐 저장
        session.execute.assert_awaited()

    @pytest.mark.asyncio
    async def test_billing_category_not_deferred_at_night(self):
        """4.1 회귀: BILLING 카테고리는 야간에도 즉시 발송된다."""
        provider = _make_provider(alimtalk_success=True)
        factory, session = _make_session_factory()
        redis = _make_redis(per_min_count=1)
        runtime_redis = _make_runtime_redis(enabled=True, active=True)

        service = NotificationService(provider, factory, redis, runtime_redis=runtime_redis)

        with patch(
            "api.src.integrations.messaging.notification_service.is_night_block_time",
            return_value=True,
        ):
            await service.send(
                user_id=1,
                phone="01012345678",
                template_code="billing.first_charge_success",
                variables={"amount_krw": "9900", "next_charge_at": "2026-05-23"},
                idempotency_key="payment:1:success",
            )

        # BILLING은 야간 차단 면제 → 즉시 알림톡 발송
        provider.send_alimtalk.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_notice_not_deferred_during_day(self):
        """4.1 회귀: 낮 시간(08~21 KST)에는 NOTICE도 즉시 발송된다."""
        provider = _make_provider(alimtalk_success=True)
        factory, session = _make_session_factory()
        redis = _make_redis(per_min_count=1)
        # active=None → is_night_block_time() 폴백 트리거
        runtime_redis = _make_runtime_redis(enabled=True, active=None)

        service = NotificationService(provider, factory, redis, runtime_redis=runtime_redis)

        with patch(
            "api.src.integrations.messaging.notification_service.is_night_block_time",
            return_value=False,
        ):
            await service.send(
                user_id=1,
                phone="01012345678",
                template_code="notice.generic",
                variables={"title": "공지", "body": "내용"},
                idempotency_key="notice:1:20260423",
            )

        provider.send_alimtalk.assert_awaited_once()

    # ── 4.2 신규 케이스 ─────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_toggle_off_notice_night_sends_immediately(self):
        """4.2 신규: 토글 OFF + NOTICE 야간 → 즉시 발송 (AC-6)."""
        provider = _make_provider(alimtalk_success=True)
        factory, session = _make_session_factory()
        redis = _make_redis(per_min_count=1)
        runtime_redis = _make_runtime_redis(enabled=False, active=True)

        service = NotificationService(provider, factory, redis, runtime_redis=runtime_redis)

        with patch(
            "api.src.integrations.messaging.notification_service.is_night_block_time",
            return_value=True,
        ):
            result = await service.send(
                user_id=1,
                phone="01012345678",
                template_code="notice.generic",
                variables={"title": "공지", "body": "내용"},
                idempotency_key="notice:toggle-off:1",
            )

        # 토글 OFF → 야간이어도 즉시 발송
        provider.send_alimtalk.assert_awaited_once()
        assert result.status != "deferred"

    @pytest.mark.asyncio
    async def test_active_none_daytime_fallback_sends(self):
        """4.2 신규: 토글 ON + active=None + 낮 시각 → 즉시 발송 (이중 안전망 폴백)."""
        provider = _make_provider(alimtalk_success=True)
        factory, session = _make_session_factory()
        redis = _make_redis(per_min_count=1)
        runtime_redis = _make_runtime_redis(enabled=True, active=None)

        service = NotificationService(provider, factory, redis, runtime_redis=runtime_redis)

        with patch(
            "api.src.integrations.messaging.notification_service.is_night_block_time",
            return_value=False,
        ):
            result = await service.send(
                user_id=1,
                phone="01012345678",
                template_code="notice.generic",
                variables={"title": "공지", "body": "내용"},
                idempotency_key="notice:daytime-fallback:1",
            )

        provider.send_alimtalk.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_active_none_nighttime_fallback_defers(self):
        """4.2 신규: 토글 ON + active=None + 밤 시각 → deferred (이중 안전망 폴백)."""
        provider = _make_provider()
        factory, session = _make_session_factory()
        redis = _make_redis(per_min_count=1)
        runtime_redis = _make_runtime_redis(enabled=True, active=None)

        service = NotificationService(provider, factory, redis, runtime_redis=runtime_redis)

        with patch(
            "api.src.integrations.messaging.notification_service.is_night_block_time",
            return_value=True,
        ):
            result = await service.send(
                user_id=1,
                phone="01012345678",
                template_code="notice.generic",
                variables={"title": "공지", "body": "내용"},
                idempotency_key="notice:night-fallback:1",
            )

        provider.send_alimtalk.assert_not_awaited()
        assert result.status == "deferred"

    @pytest.mark.asyncio
    async def test_urgent_true_notice_night_bypasses_and_logs(self, caplog):
        """4.2 신규: urgent=True + NOTICE 야간 → 즉시 발송 + night_block_bypassed 로그 (AC-4)."""
        provider = _make_provider(alimtalk_success=True)
        factory, session = _make_session_factory()
        redis = _make_redis(per_min_count=1)
        runtime_redis = _make_runtime_redis(enabled=True, active=True)

        service = NotificationService(provider, factory, redis, runtime_redis=runtime_redis)

        with patch(
            "api.src.integrations.messaging.notification_service.is_night_block_time",
            return_value=True,
        ):
            result = await service.send(
                user_id=1,
                phone="01012345678",
                template_code="notice.generic",
                variables={"title": "긴급", "body": "내용"},
                idempotency_key="notice:urgent:1",
                urgent=True,
            )

        # urgent=True → 야간이어도 즉시 발송
        provider.send_alimtalk.assert_awaited_once()
        assert result.status != "deferred"

    @pytest.mark.asyncio
    async def test_night_deferred_until_is_utc_naive(self):
        """4.2 버그픽스: 야간 차단 시 deferred_until이 UTC naive여야 한다.

        dispatcher(notification_tasks.py)는 datetime.now(timezone.utc).replace(tzinfo=None)와
        비교하므로, KST naive를 저장하면 약 9시간 지연된다.
        next_8am_kst()가 KST 08:00을 반환할 때 → UTC naive는 전날 23:00이어야 한다.
        """
        from api.src.utils.korean_time import KST

        provider = _make_provider()
        factory, session = _make_session_factory()
        redis = _make_redis(per_min_count=1)
        runtime_redis = _make_runtime_redis(enabled=True, active=True)

        service = NotificationService(provider, factory, redis, runtime_redis=runtime_redis)

        fixed_8am_kst = datetime(2026, 5, 9, 8, 0, 0, tzinfo=KST)
        expected_utc_naive = datetime(2026, 5, 8, 23, 0, 0)

        with patch(
            "api.src.integrations.messaging.notification_service.next_8am_kst",
            return_value=fixed_8am_kst,
        ), patch(
            "api.src.integrations.messaging.notification_service.is_night_block_time",
            return_value=True,
        ):
            result = await service.send(
                user_id=1,
                phone="01012345678",
                template_code="notice.generic",
                variables={"title": "공지", "body": "내용"},
                idempotency_key="notice:utc-naive-check:1",
            )

        assert result.status == "deferred"
        assert result.deferred_until == expected_utc_naive
        assert result.deferred_until.tzinfo is None

    @pytest.mark.asyncio
    async def test_urgent_true_billing_night_no_bypass_log(self):
        """4.2 신규: urgent=True + BILLING 야간 → 즉시 발송 + bypassed 로그 미발생 (AC-4, 노이즈 방지)."""
        provider = _make_provider(alimtalk_success=True)
        factory, session = _make_session_factory()
        redis = _make_redis(per_min_count=1)
        runtime_redis = _make_runtime_redis(enabled=True, active=True)

        service = NotificationService(provider, factory, redis, runtime_redis=runtime_redis)

        logged_events = []
        with patch(
            "api.src.integrations.messaging.notification_service.is_night_block_time",
            return_value=True,
        ), patch(
            "api.src.integrations.messaging.notification_service.logger"
        ) as mock_logger:
            mock_logger.info = MagicMock()
            result = await service.send(
                user_id=1,
                phone="01012345678",
                template_code="billing.first_charge_success",
                variables={"amount_krw": "9900", "next_charge_at": "2026-05-23"},
                idempotency_key="billing:urgent:1",
                urgent=True,
            )
            # night_block_bypassed는 NOTICE에만 발생해야 함
            for call in mock_logger.info.call_args_list:
                logged_events.append(call[0][0] if call[0] else "")

        provider.send_alimtalk.assert_awaited_once()
        assert "notification.night_block_bypassed" not in logged_events

    @pytest.mark.asyncio
    async def test_runtime_redis_exception_fail_closed(self):
        """4.2 신규: runtime_redis 호출 예외 → fail-closed (NOTICE 야간 deferred) (AC-3)."""
        provider = _make_provider()
        factory, session = _make_session_factory()
        redis = _make_redis(per_min_count=1)

        runtime_redis = AsyncMock()
        runtime_redis.get.side_effect = Exception("redis 장애")

        service = NotificationService(provider, factory, redis, runtime_redis=runtime_redis)

        with patch(
            "api.src.integrations.messaging.notification_service.is_night_block_time",
            return_value=True,
        ):
            result = await service.send(
                user_id=1,
                phone="01012345678",
                template_code="notice.generic",
                variables={"title": "공지", "body": "내용"},
                idempotency_key="notice:redis-fail:1",
            )

        # Redis 실패 → fail-closed → 야간 deferred
        provider.send_alimtalk.assert_not_awaited()
        assert result.status == "deferred"


# ── Tests: 레이트 리밋 ───────────────────────────────────────────────────────

class TestNotificationServiceRateLimit:
    @pytest.mark.asyncio
    async def test_per_minute_rate_limit_defers_excess(self):
        """분당 5건 초과 시 rate_limited_deferred로 큐 저장된다."""
        provider = _make_provider()
        factory, session = _make_session_factory()
        # incr이 6을 반환 → 5 초과
        redis = _make_redis(per_min_count=6)
        runtime_redis = _make_runtime_redis(enabled=True, active=False)

        service = NotificationService(provider, factory, redis, runtime_redis=runtime_redis)

        with patch(
            "api.src.integrations.messaging.notification_service.is_night_block_time",
            return_value=False,
        ):
            await service.send(
                user_id=1,
                phone="01012345678",
                template_code="billing.first_charge_success",
                variables={"amount_krw": "9900", "next_charge_at": "2026-05-23"},
                idempotency_key="payment:1:success",
            )

        # 레이트 리밋 → 즉시 발송하지 않음
        provider.send_alimtalk.assert_not_awaited()
        # rate_limited_deferred 큐 저장
        session.execute.assert_awaited()

    @pytest.mark.asyncio
    async def test_within_rate_limit_sends_immediately(self):
        """분당 5건 이하면 즉시 발송된다."""
        provider = _make_provider(alimtalk_success=True)
        factory, session = _make_session_factory()
        redis = _make_redis(per_min_count=3)
        runtime_redis = _make_runtime_redis(enabled=True, active=False)

        service = NotificationService(provider, factory, redis, runtime_redis=runtime_redis)

        with patch(
            "api.src.integrations.messaging.notification_service.is_night_block_time",
            return_value=False,
        ):
            await service.send(
                user_id=1,
                phone="01012345678",
                template_code="billing.first_charge_success",
                variables={"amount_krw": "9900", "next_charge_at": "2026-05-23"},
                idempotency_key="payment:1:success",
            )

        provider.send_alimtalk.assert_awaited_once()


# ── Tests: 유효하지 않은 template_code ─────────────────────────────────────

class TestNotificationServiceInvalidTemplate:
    @pytest.mark.asyncio
    async def test_invalid_template_code_raises(self):
        """존재하지 않는 template_code는 ValueError를 발생시킨다."""
        provider = _make_provider()
        factory, _ = _make_session_factory()
        redis = _make_redis()
        runtime_redis = _make_runtime_redis()

        service = NotificationService(provider, factory, redis, runtime_redis=runtime_redis)

        with pytest.raises(ValueError, match="알 수 없는 template_code"):
            await service.send(
                user_id=1,
                phone="01012345678",
                template_code="invalid.unknown",
                variables={},
                idempotency_key="key:1",
            )
