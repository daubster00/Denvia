"""한국수출입은행 환율 API 클라이언트 단위 테스트.

httpx.AsyncClient.get 을 monkeypatch 로 가짜 응답화하여:
- 정상 USD 매매기준율 파싱
- 영업일 외(빈 배열) → 직전 영업일로 폴백
- 전 lookback 실패 → ForexFetchError
- result!=1 인증 실패 → ForexFetchError
- 잘못된 deal_bas_r → ForexFetchError
"""

from __future__ import annotations

from datetime import date

import httpx
import pytest

from api.src.integrations.forex.koreaexim import (
    ForexFetchError,
    KoreaeximClient,
)


def _resp_ok(rate_text: str) -> httpx.Response:
    return httpx.Response(
        200,
        json=[
            {"result": 1, "cur_unit": "JPY(100)", "deal_bas_r": "905.12"},
            {"result": 1, "cur_unit": "USD", "deal_bas_r": rate_text},
            {"result": 1, "cur_unit": "EUR", "deal_bas_r": "1,510.00"},
        ],
    )


def _resp_empty() -> httpx.Response:
    return httpx.Response(200, json=[])


@pytest.mark.asyncio
async def test_fetch_usd_to_krw_success(monkeypatch):
    client = KoreaeximClient(api_key="K", base_url="https://example.test/forex")

    async def fake_get(self, url, *args, **kwargs):
        # searchdate 가 정확히 전달됐는지 확인.
        assert kwargs["params"]["searchdate"] == "20260521"
        assert kwargs["params"]["data"] == "AP01"
        assert kwargs["params"]["authkey"] == "K"
        return _resp_ok("1,392.5")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    result = await client.fetch_usd_to_krw(today=date(2026, 5, 21))
    # Decimal("1392.5") → quantize("1") = 1392 (반올림 ROUND_HALF_EVEN).
    assert result.rate == 1392
    assert result.search_date == date(2026, 5, 21)
    assert result.raw_deal_bas_r == "1,392.5"


@pytest.mark.asyncio
async def test_fetch_usd_to_krw_falls_back_to_prev_business_day(monkeypatch):
    """주말 또는 게시 전: 오늘 빈 배열 → 어제 빈 배열 → 그제 성공."""
    client = KoreaeximClient(api_key="K", base_url="https://example.test/forex")
    seen_dates: list[str] = []

    async def fake_get(self, url, *args, **kwargs):
        d = kwargs["params"]["searchdate"]
        seen_dates.append(d)
        if d in ("20260524", "20260523"):  # 일요일, 토요일
            return _resp_empty()
        return _resp_ok("1,398.0")  # 금요일

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    result = await client.fetch_usd_to_krw(today=date(2026, 5, 24))  # 일요일
    assert result.rate == 1398
    assert result.search_date == date(2026, 5, 22)
    assert seen_dates == ["20260524", "20260523", "20260522"]


@pytest.mark.asyncio
async def test_fetch_usd_to_krw_all_empty_raises(monkeypatch):
    client = KoreaeximClient(api_key="K", base_url="https://example.test/forex")

    async def fake_get(self, url, *args, **kwargs):
        return _resp_empty()

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    with pytest.raises(ForexFetchError):
        await client.fetch_usd_to_krw(today=date(2026, 5, 24), lookback_days=3)


@pytest.mark.asyncio
async def test_fetch_usd_to_krw_auth_failure_raises(monkeypatch):
    """result=2 는 인증 실패 — 다음 날짜로 폴백하지 않고 즉시 실패."""
    client = KoreaeximClient(api_key="K", base_url="https://example.test/forex")

    async def fake_get(self, url, *args, **kwargs):
        return httpx.Response(
            200,
            json=[{"result": 2, "cur_unit": "USD", "deal_bas_r": "1,400.0"}],
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    with pytest.raises(ForexFetchError, match="result=2"):
        await client.fetch_usd_to_krw(today=date(2026, 5, 21))


@pytest.mark.asyncio
async def test_fetch_usd_to_krw_invalid_deal_bas_r(monkeypatch):
    client = KoreaeximClient(api_key="K", base_url="https://example.test/forex")

    async def fake_get(self, url, *args, **kwargs):
        return httpx.Response(
            200,
            json=[{"result": 1, "cur_unit": "USD", "deal_bas_r": "invalid"}],
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    with pytest.raises(ForexFetchError, match="invalid deal_bas_r"):
        await client.fetch_usd_to_krw(today=date(2026, 5, 21))


@pytest.mark.asyncio
async def test_fetch_usd_to_krw_4xx_raises(monkeypatch):
    """4xx 는 즉시 실패 (재시도 없음)."""
    client = KoreaeximClient(api_key="K", base_url="https://example.test/forex")

    async def fake_get(self, url, *args, **kwargs):
        return httpx.Response(403, json={"detail": "forbidden"})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    with pytest.raises(ForexFetchError):
        await client.fetch_usd_to_krw(today=date(2026, 5, 21), lookback_days=1)


@pytest.mark.asyncio
async def test_fetch_usd_to_krw_5xx_retried_then_fallback_date(monkeypatch):
    """5xx 는 재시도 3회 후 RetryError → 직전 영업일로 폴백."""
    client = KoreaeximClient(api_key="K", base_url="https://example.test/forex")
    call_count = {"n": 0}

    async def fake_get(self, url, *args, **kwargs):
        call_count["n"] += 1
        d = kwargs["params"]["searchdate"]
        if d == "20260521":
            return httpx.Response(503)
        return _resp_ok("1,388.0")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    result = await client.fetch_usd_to_krw(today=date(2026, 5, 21))
    # 첫 날짜에서 5xx 3회 재시도 + 직전 날짜 1회 → 4회 이상 호출.
    assert call_count["n"] >= 4
    assert result.rate == 1388
    assert result.search_date == date(2026, 5, 20)


def test_init_requires_api_key():
    with pytest.raises(ForexFetchError, match="not set"):
        KoreaeximClient(api_key="", base_url="https://example.test/forex")
