"""USD→KRW 환율 일일 자동 갱신 — Celery Beat.

정책 (Story 5.5 후속):
- 매일 09:00 KST 한국수출입은행 환율 API 호출.
- 성공: Redis(DB 3) ``runtime:usd_to_krw`` 갱신 + 메타키 함께 SET.
- 실패(키 미설정·네트워크·영업일 부재 등): 기존 값을 유지 (no-op + WARN 로그).
- 자동 우선 정책: 관리자가 수동으로 SET 한 값도 다음 갱신 시점에 자동으로 덮어쓴다.

메타 키:
- runtime:usd_to_krw_updated_at  — 마지막 자동 갱신 ISO8601 (UTC).
- runtime:usd_to_krw_search_date — API 가 실제로 데이터를 반환한 영업일 (YYYY-MM-DD).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import structlog

from api.src.integrations.forex.koreaexim import (
    ForexFetchError,
    KoreaeximClient,
    UsdKrwRate,
)
from api.src.services import runtime_config_service
from api.src.settings import REDIS_DB_RUNTIME_CONFIG, settings
from api.src.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


KEY_UPDATED_AT = "runtime:usd_to_krw_updated_at"
KEY_SEARCH_DATE = "runtime:usd_to_krw_search_date"


@celery_app.task(name="forex_tasks.update_usd_krw")
def update_usd_krw() -> dict:
    """매일 09:00 KST 호출 — 동기 wrapper."""
    return asyncio.run(_update_usd_krw_async())


async def _update_usd_krw_async() -> dict:
    import redis.asyncio as aioredis

    if not settings.koreaexim_api_key:
        logger.warning("forex.update.skipped", reason="api_key_missing")
        return {"status": "skipped", "reason": "api_key_missing"}

    runtime_redis = aioredis.from_url(
        f"{settings.redis_url}/{REDIS_DB_RUNTIME_CONFIG}", decode_responses=True
    )
    try:
        client = KoreaeximClient(
            api_key=settings.koreaexim_api_key,
            base_url=settings.koreaexim_base_url,
        )
        try:
            result: UsdKrwRate = await client.fetch_usd_to_krw()
        except ForexFetchError as exc:
            logger.warning("forex.update.fetch_failed", error=str(exc))
            return {"status": "failed", "reason": str(exc)}

        # sanity 범위 — runtime_config_service 와 동일 정책 (1000~3000).
        if not (
            runtime_config_service.USD_TO_KRW_MIN
            <= result.rate
            <= runtime_config_service.USD_TO_KRW_MAX
        ):
            logger.warning(
                "forex.update.rate_out_of_range",
                rate=result.rate,
                raw=result.raw_deal_bas_r,
            )
            return {
                "status": "failed",
                "reason": "rate_out_of_range",
                "rate": result.rate,
            }

        previous = await runtime_redis.get(runtime_config_service.KEY_USD_TO_KRW)
        await runtime_redis.set(
            runtime_config_service.KEY_USD_TO_KRW, str(result.rate)
        )
        now_iso = datetime.now(timezone.utc).isoformat()
        await runtime_redis.set(KEY_UPDATED_AT, now_iso)
        await runtime_redis.set(KEY_SEARCH_DATE, result.search_date.isoformat())

        logger.info(
            "forex.update.success",
            rate=result.rate,
            previous=previous,
            search_date=result.search_date.isoformat(),
            raw=result.raw_deal_bas_r,
        )
        return {
            "status": "ok",
            "rate": result.rate,
            "previous": previous,
            "search_date": result.search_date.isoformat(),
        }
    finally:
        await runtime_redis.aclose()
