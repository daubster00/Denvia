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
    """Redis mock — incr 호출 시 지정된 count 반환."""
    redis = AsyncMock()
    redis.incr.return_value = per_min_count
    redis.expire.return_value = True
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

        service = NotificationService(provider, factory, redis)

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

        service = NotificationService(provider, factory, redis)

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

        service = NotificationService(provider, factory, redis)

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
    @pytest.mark.asyncio
    async def test_notice_category_deferred_at_night(self):
        """NOTICE 카테고리는 야간(21~08 KST)에 deferred로 큐 저장된다."""
        provider = _make_provider()
        factory, session = _make_session_factory()
        redis = _make_redis(per_min_count=1)

        service = NotificationService(provider, factory, redis)

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
        """BILLING 카테고리는 야간에도 즉시 발송된다."""
        provider = _make_provider(alimtalk_success=True)
        factory, session = _make_session_factory()
        redis = _make_redis(per_min_count=1)

        service = NotificationService(provider, factory, redis)

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
        """낮 시간(08~21 KST)에는 NOTICE도 즉시 발송된다."""
        provider = _make_provider(alimtalk_success=True)
        factory, session = _make_session_factory()
        redis = _make_redis(per_min_count=1)

        service = NotificationService(provider, factory, redis)

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


# ── Tests: 레이트 리밋 ───────────────────────────────────────────────────────

class TestNotificationServiceRateLimit:
    @pytest.mark.asyncio
    async def test_per_minute_rate_limit_defers_excess(self):
        """분당 5건 초과 시 rate_limited_deferred로 큐 저장된다."""
        provider = _make_provider()
        factory, session = _make_session_factory()
        # incr이 6을 반환 → 5 초과
        redis = _make_redis(per_min_count=6)

        service = NotificationService(provider, factory, redis)

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

        service = NotificationService(provider, factory, redis)

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

        service = NotificationService(provider, factory, redis)

        with pytest.raises(ValueError, match="알 수 없는 template_code"):
            await service.send(
                user_id=1,
                phone="01012345678",
                template_code="invalid.unknown",
                variables={},
                idempotency_key="key:1",
            )
