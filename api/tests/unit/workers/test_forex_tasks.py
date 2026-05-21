"""USD→KRW 환율 일일 갱신 워커 단위 테스트.

KoreaeximClient.fetch_usd_to_krw 를 monkeypatch 로 가짜화하고
fakeredis 로 Redis SET 결과를 검증한다.
"""

from __future__ import annotations

from datetime import date

import fakeredis.aioredis
import pytest

from api.src.integrations.forex import koreaexim as kx
from api.src.services import runtime_config_service
from api.src.workers import forex_tasks


@pytest.fixture
def fake_redis(monkeypatch):
    """forex_tasks 내부의 aioredis.from_url 을 fakeredis 인스턴스로 대체."""
    server = fakeredis.aioredis.FakeRedis(decode_responses=True)

    class _Module:
        @staticmethod
        def from_url(*args, **kwargs):  # pragma: no cover — signature stub
            return server

    import redis.asyncio as aioredis_real

    monkeypatch.setattr(aioredis_real, "from_url", _Module.from_url)
    return server


@pytest.mark.asyncio
async def test_skipped_when_api_key_missing(monkeypatch, fake_redis):
    monkeypatch.setattr(forex_tasks.settings, "koreaexim_api_key", "")
    result = await forex_tasks._update_usd_krw_async()
    assert result["status"] == "skipped"
    # Redis 에 아무것도 SET 되지 않아야 함.
    assert await fake_redis.get(runtime_config_service.KEY_USD_TO_KRW) is None


@pytest.mark.asyncio
async def test_success_sets_rate_and_meta(monkeypatch, fake_redis):
    monkeypatch.setattr(forex_tasks.settings, "koreaexim_api_key", "TESTKEY")
    monkeypatch.setattr(
        forex_tasks.settings, "koreaexim_base_url", "https://example.test/forex"
    )

    async def fake_fetch(self, *, today=None, lookback_days=7):
        return kx.UsdKrwRate(rate=1388, search_date=date(2026, 5, 20), raw_deal_bas_r="1,388.0")

    monkeypatch.setattr(kx.KoreaeximClient, "fetch_usd_to_krw", fake_fetch)

    # 사전: 다른 값이 있어도 자동이 덮어쓰기 (자동 우선 정책).
    await fake_redis.set(runtime_config_service.KEY_USD_TO_KRW, "1500")

    result = await forex_tasks._update_usd_krw_async()

    assert result["status"] == "ok"
    assert result["rate"] == 1388
    assert result["previous"] == "1500"
    assert await fake_redis.get(runtime_config_service.KEY_USD_TO_KRW) == "1388"
    assert await fake_redis.get(forex_tasks.KEY_UPDATED_AT) is not None
    assert await fake_redis.get(forex_tasks.KEY_SEARCH_DATE) == "2026-05-20"


@pytest.mark.asyncio
async def test_fetch_failure_keeps_existing_value(monkeypatch, fake_redis):
    monkeypatch.setattr(forex_tasks.settings, "koreaexim_api_key", "TESTKEY")

    async def fake_fetch(self, *, today=None, lookback_days=7):
        raise kx.ForexFetchError("network down")

    monkeypatch.setattr(kx.KoreaeximClient, "fetch_usd_to_krw", fake_fetch)

    await fake_redis.set(runtime_config_service.KEY_USD_TO_KRW, "1420")

    result = await forex_tasks._update_usd_krw_async()

    assert result["status"] == "failed"
    # 기존 값 보존.
    assert await fake_redis.get(runtime_config_service.KEY_USD_TO_KRW) == "1420"
    # 메타키도 갱신되지 않음.
    assert await fake_redis.get(forex_tasks.KEY_UPDATED_AT) is None


@pytest.mark.asyncio
async def test_rate_out_of_range_keeps_existing_value(monkeypatch, fake_redis):
    """API 가 미친 값(5000) 을 돌려줘도 기존값 유지 — 데이터 손상 방어."""
    monkeypatch.setattr(forex_tasks.settings, "koreaexim_api_key", "TESTKEY")

    async def fake_fetch(self, *, today=None, lookback_days=7):
        return kx.UsdKrwRate(rate=5000, search_date=date(2026, 5, 21), raw_deal_bas_r="5,000.0")

    monkeypatch.setattr(kx.KoreaeximClient, "fetch_usd_to_krw", fake_fetch)

    await fake_redis.set(runtime_config_service.KEY_USD_TO_KRW, "1420")

    result = await forex_tasks._update_usd_krw_async()

    assert result["status"] == "failed"
    assert result["reason"] == "rate_out_of_range"
    assert await fake_redis.get(runtime_config_service.KEY_USD_TO_KRW) == "1420"
