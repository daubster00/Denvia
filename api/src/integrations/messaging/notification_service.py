"""NotificationService — 알림톡 + SMS 폴백 + 야간 차단 + 레이트 리밋 + 멱등성 (F-501)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import sentry_sdk
import structlog
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential

from api.src.integrations.messaging.port import MessagingProvider
from api.src.integrations.messaging.templates import (
    TemplateCategory,
    get_template,
    render_sms_body,
)
from api.src.models.notification_queue import (
    STATUS_DEFERRED,
    STATUS_FAILED,
    STATUS_RATE_LIMITED,
    STATUS_SENT,
    NotificationQueue,
)
from api.src.services.runtime_config_service import get_night_block_settings
from api.src.utils.korean_time import is_night_block_time, next_8am_kst

if TYPE_CHECKING:
    import redis.asyncio as aioredis

logger = structlog.get_logger(__name__)

_RATE_LIMIT_PER_MIN = 5
_RATE_LIMIT_PER_HOUR = 20


@dataclass
class SendResult:
    """send() 결과 — dispatch 태스크가 기존 큐 행을 정확히 업데이트하는 데 사용한다."""

    status: str
    deferred_until: datetime | None = field(default=None)
    error: str | None = field(default=None)


def _mask_phone(phone: str) -> str:
    """PII 스크러빙 — 마지막 4자리만 노출."""
    return "****" + phone[-4:] if len(phone) >= 4 else "****"


class NotificationService:
    """알림 발송 서비스 — 어댑터 호출·폴백·야간차단·레이트리밋·멱등성 관리."""

    def __init__(
        self,
        provider: MessagingProvider,
        session_factory: async_sessionmaker[AsyncSession],
        redis: aioredis.Redis,
        *,
        runtime_redis: aioredis.Redis,
    ) -> None:
        self._provider = provider
        self._session_factory = session_factory
        self._redis = redis                    # DB 2: rate limit
        self._runtime_redis = runtime_redis    # DB 3: runtime config

    async def send(
        self,
        user_id: int,
        phone: str,
        template_code: str,
        variables: dict[str, str],
        idempotency_key: str,
        urgent: bool = False,
    ) -> SendResult:
        """알림을 발송한다.

        Args:
            user_id: 수신자 사용자 ID
            phone: 수신자 휴대폰 번호
            template_code: TEMPLATE_CATALOG 키
            variables: 템플릿 변수
            idempotency_key: 중복 방지 키 (예: "payment_id:42:success")
            urgent: True면 야간 차단 판정을 우회한다 (AC-4)
        """
        template = get_template(template_code)

        # 1. 시간당 레이트 리밋 경고 (비차단, Redis 오류 무시)
        await self._check_hourly_rate(user_id, template_code)

        # 2. 분당 레이트 리밋 — 초과 시 1분 후 재시도로 큐 저장 (AC-7)
        if await self._is_per_minute_rate_limited(user_id):
            deferred_until = (
                datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=1)
            )
            await self._enqueue(
                user_id=user_id,
                template_code=template_code,
                variables=variables,
                idempotency_key=idempotency_key,
                channel="alimtalk",
                status=STATUS_RATE_LIMITED,
                deferred_until=deferred_until,
            )
            logger.info(
                "notification.rate_limited_deferred",
                user_id=user_id,
                template_code=template_code,
                deferred_until=str(deferred_until),
            )
            return SendResult(status=STATUS_RATE_LIMITED, deferred_until=deferred_until)

        # 3. 야간 차단 — NOTICE 카테고리 + urgent=False인 경우만 적용 (AC-3·4·6)
        if template.category == TemplateCategory.NOTICE and not urgent:
            night_settings = await get_night_block_settings(self._runtime_redis)
            if night_settings.enabled:
                # active가 None이면 시각 기반 이중 안전망 폴백 (AC-3 2차)
                is_night = (
                    night_settings.active
                    if night_settings.active is not None
                    else is_night_block_time()
                )
                if is_night:
                    deferred_until = next_8am_kst().astimezone(timezone.utc).replace(tzinfo=None)
                    await self._enqueue(
                        user_id=user_id,
                        template_code=template_code,
                        variables=variables,
                        idempotency_key=idempotency_key,
                        channel="alimtalk",
                        status=STATUS_DEFERRED,
                        deferred_until=deferred_until,
                    )
                    logger.info(
                        "notification.night_deferred",
                        user_id=user_id,
                        template_code=template_code,
                        deferred_until=str(deferred_until),
                    )
                    return SendResult(status=STATUS_DEFERRED, deferred_until=deferred_until)

        # urgent=True로 NOTICE 야간을 우회한 경우만 별도 로깅 (AC-4)
        if urgent and template.category == TemplateCategory.NOTICE and is_night_block_time():
            logger.info(
                "notification.night_block_bypassed",
                user_id=user_id,
                template_code=template_code,
                category=template.category.value,
                reason="manual_urgent",
            )

        # 4. 알림톡 발송 시도
        alimtalk_ok = await self._try_send_alimtalk(user_id, phone, template_code, variables)
        if alimtalk_ok:
            # 성공 기록 — 동일 idempotency_key 재호출 시 중복 발송 방지 (AC-6 Decision 1A)
            await self._enqueue(
                user_id=user_id,
                template_code=template_code,
                variables=variables,
                idempotency_key=idempotency_key,
                channel="alimtalk",
                status=STATUS_SENT,
            )
            return SendResult(status=STATUS_SENT)

        # 5. SMS 폴백
        sms_ok = await self._try_send_sms(user_id, phone, template, template_code, variables)
        if sms_ok:
            await self._enqueue(
                user_id=user_id,
                template_code=template_code,
                variables=variables,
                idempotency_key=idempotency_key,
                channel="sms",
                status=STATUS_SENT,
            )
            return SendResult(status=STATUS_SENT)

        # 6. 두 경로 모두 실패 → 큐 저장 + Sentry
        err = "alimtalk 및 SMS 폴백 모두 실패"
        await self._enqueue(
            user_id=user_id,
            template_code=template_code,
            variables=variables,
            idempotency_key=idempotency_key,
            channel="alimtalk",
            status=STATUS_FAILED,
            last_error=err,
        )
        sentry_sdk.capture_message(
            f"notification.failed: {template_code} for user {user_id}",
            level="error",
        )
        logger.error("notification.failed", user_id=user_id, template_code=template_code)
        return SendResult(status=STATUS_FAILED, error=err)

    # ── 내부 메서드 ──────────────────────────────────────────────────────────

    async def _try_send_alimtalk(
        self,
        user_id: int,
        phone: str,
        template_code: str,
        variables: dict[str, str],
    ) -> bool:
        """알림톡 발송 (tenacity 3회 재시도). 성공 시 True 반환."""
        result = None
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, min=2, max=30),
                reraise=True,
            ):
                with attempt:
                    result = await self._provider.send_alimtalk(phone, template_code, variables)

            if result and result["success"]:
                logger.info(
                    "notification.sent",
                    user_id=user_id,
                    phone=_mask_phone(phone),
                    template_code=template_code,
                    channel="alimtalk",
                    provider_response_code=result["provider_response_code"],
                )
                return True
        except Exception as exc:
            logger.warning(
                "notification.alimtalk_failed",
                user_id=user_id,
                template_code=template_code,
                error=str(exc),
            )
        return False

    async def _try_send_sms(
        self,
        user_id: int,
        phone: str,
        template,
        template_code: str,
        variables: dict[str, str],
    ) -> bool:
        """SMS 폴백 발송 (tenacity 3회 재시도). 성공 시 True 반환."""
        try:
            sms_body = render_sms_body(template, variables)
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, min=2, max=30),
                reraise=True,
            ):
                with attempt:
                    await self._provider.send_sms(phone, sms_body)

            logger.info(
                "notification.fallback_to_sms",
                user_id=user_id,
                phone=_mask_phone(phone),
                template_code=template_code,
                channel="sms",
            )
            return True
        except Exception as exc:
            logger.warning("notification.sms_failed", user_id=user_id, error=str(exc))
        return False

    async def _enqueue(
        self,
        user_id: int,
        template_code: str,
        variables: dict[str, str],
        idempotency_key: str,
        channel: str,
        status: str,
        deferred_until: datetime | None = None,
        last_error: str | None = None,
    ) -> None:
        """notification_queue에 항목을 삽입한다. 중복 idempotency_key는 무시된다."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        try:
            async with self._session_factory() as session:
                # 0002 의 idempotency 인덱스는 partial UNIQUE INDEX
                # (`WHERE user_id IS NOT NULL`). `constraint=...` 는 실제 CONSTRAINT 만
                # 인식하므로 `UndefinedObject` 로 항상 실패한다 — 컬럼 + index_where 로 명시.
                # QA-v3 G4 회귀: queue 행 0개로 발송 silent drop.
                stmt = (
                    pg_insert(NotificationQueue)
                    .values(
                        user_id=user_id,
                        template_code=template_code,
                        variables=variables,
                        channel=channel,
                        status=status,
                        idempotency_key=idempotency_key,
                        deferred_until=deferred_until,
                        last_error=last_error,
                        created_at=now,
                    )
                    .on_conflict_do_nothing(
                        index_elements=["user_id", "template_code", "idempotency_key"],
                        index_where=NotificationQueue.user_id.is_not(None),
                    )
                )
                await session.execute(stmt)
                await session.commit()
        except Exception as exc:
            sentry_sdk.capture_exception(exc)
            logger.error(
                "notification.enqueue_failed",
                user_id=user_id,
                template_code=template_code,
                status=status,
                error=str(exc),
            )

    async def _is_per_minute_rate_limited(self, user_id: int) -> bool:
        """분당 5건 초과 여부를 확인한다 (Redis DB 2 사용). Redis 오류 시 발송 허용."""
        try:
            import time
            minute_bucket = int(time.time()) // 60
            key = f"notif_rate:per_min:{user_id}:{minute_bucket}"
            count = await self._redis.incr(key)
            if count == 1:
                try:
                    await self._redis.expire(key, 60)
                except Exception:
                    pass
            return int(count) > _RATE_LIMIT_PER_MIN
        except Exception as exc:
            logger.warning(
                "notification.rate_limit_check_failed",
                user_id=user_id,
                error=str(exc),
            )
            return False  # fail open: Redis 장애 시 발송 허용

    async def _check_hourly_rate(self, user_id: int, template_code: str) -> None:
        """시간당 20건 초과 시 Sentry 경고를 발생시킨다 (비차단). Redis 오류는 무시."""
        try:
            import time
            hour_bucket = int(time.time()) // 3600
            key = f"notif_rate:per_hour:{user_id}:{hour_bucket}"
            count = await self._redis.incr(key)
            if count == 1:
                try:
                    await self._redis.expire(key, 3600)
                except Exception:
                    pass
            if int(count) > _RATE_LIMIT_PER_HOUR:
                sentry_sdk.capture_message(
                    f"notification rate limit 20/hr exceeded: user={user_id}, template={template_code}",
                    level="warning",
                )
        except Exception as exc:
            logger.warning(
                "notification.hourly_rate_check_failed",
                user_id=user_id,
                error=str(exc),
            )


def get_notification_service() -> NotificationService:
    """NotificationService 팩토리 — 환경 설정 기반으로 인스턴스를 생성한다."""
    import redis.asyncio as aioredis

    from api.src.integrations.messaging.adapters import get_adapter
    from api.src.models.base import async_session_factory
    from api.src.settings import REDIS_DB_RATE_LIMIT, REDIS_DB_RUNTIME_CONFIG, settings

    provider = get_adapter()
    rate_limit_redis = aioredis.from_url(
        f"{settings.redis_url}/{REDIS_DB_RATE_LIMIT}",
        decode_responses=True,
    )
    runtime_redis = aioredis.from_url(
        f"{settings.redis_url}/{REDIS_DB_RUNTIME_CONFIG}",
        decode_responses=True,
    )
    return NotificationService(
        provider,
        async_session_factory,
        rate_limit_redis,
        runtime_redis=runtime_redis,
    )
