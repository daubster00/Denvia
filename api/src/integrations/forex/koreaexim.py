"""한국수출입은행 환율 API 클라이언트 — USD→KRW 매매기준율 조회.

API 명세:
- Endpoint: https://oapi.koreaexim.go.kr/site/program/financial/exchangeJSON
- Query: authkey, searchdate=YYYYMMDD, data=AP01 (환율)
- Response: 통화별 객체 배열. cur_unit="USD" 항목의 deal_bas_r(매매기준율)을 사용.
- 게시 시각: 영업일 11:00 KST 이후 (그 이전·주말·공휴일은 빈 배열 반환).
- result 코드: 1=성공, 2=인증실패, 3=일자형식에러, 4=일일횟수초과.

운영 정책:
- 매일 09:00 KST 갱신 → 오늘 데이터는 아직 미게시 → 최근 영업일을 거슬러 재시도
  (최대 7일: 3일 연휴 + 주말 커버).
- 모든 영업일에 미게시 / 인증 실패 / 네트워크 실패 → ``ForexFetchError`` raise.
  호출자(forex_tasks) 는 이를 catch 하여 기존 Redis 값을 유지.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

import httpx
import structlog
from tenacity import (
    RetryError,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

logger = structlog.get_logger(__name__)


class ForexFetchError(RuntimeError):
    """환율 조회 실패 — 호출자는 기존 값을 유지해야 한다."""


@dataclass(frozen=True)
class UsdKrwRate:
    rate: int            # 매매기준율 (원 단위, 반올림)
    search_date: date    # API 가 실제로 데이터를 반환한 영업일
    raw_deal_bas_r: str  # 원문(소수점 포함) — 감사 로그용


def _retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return 500 <= exc.response.status_code < 600
    if isinstance(exc, (httpx.RequestError, httpx.TimeoutException)):
        return True
    return False


_retry = retry(
    retry=retry_if_exception(_retryable),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(3),
    reraise=True,
)


class KoreaeximClient:
    """한국수출입은행 환율 API 비동기 클라이언트.

    timeout 10s · 5xx 재시도 3회. 4xx 및 비정상 페이로드는 즉시 ForexFetchError.
    """

    def __init__(self, api_key: str, base_url: str, *, timeout: float = 10.0) -> None:
        if not api_key:
            raise ForexFetchError("KOREAEXIM_API_KEY is not set")
        self._api_key = api_key
        self._base_url = base_url
        self._timeout = timeout

    async def fetch_usd_to_krw(self, *, today: date | None = None, lookback_days: int = 7) -> UsdKrwRate:
        """오늘부터 최대 lookback_days 영업일을 거슬러 USD 매매기준율을 가져온다.

        영업일 외·게시 전·공휴일은 빈 배열 반환되므로 직전 날짜로 재시도.
        모든 시도 실패 시 ForexFetchError.
        """
        anchor = today or date.today()
        last_exc: BaseException | None = None
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for offset in range(lookback_days):
                search_date = anchor - timedelta(days=offset)
                try:
                    payload = await self._call(client, search_date)
                except (RetryError, httpx.HTTPStatusError, httpx.RequestError, httpx.TimeoutException) as exc:
                    last_exc = exc
                    logger.warning(
                        "forex.koreaexim.http_error",
                        search_date=search_date.isoformat(),
                        error=str(exc),
                    )
                    continue
                usd_row = _find_usd(payload)
                if usd_row is None:
                    # 빈 배열 또는 USD 항목 부재 — 직전 영업일로 폴백.
                    logger.info(
                        "forex.koreaexim.no_data",
                        search_date=search_date.isoformat(),
                    )
                    continue
                # result=1 이외(인증 실패 등)는 즉시 실패 — 키 문제는 다음 날짜에서도 같음.
                result_code = usd_row.get("result")
                if result_code is not None and int(result_code) != 1:
                    raise ForexFetchError(f"koreaexim result={result_code}")
                rate = _parse_deal_bas_r(usd_row.get("deal_bas_r"))
                if rate is None:
                    raise ForexFetchError(f"invalid deal_bas_r: {usd_row.get('deal_bas_r')!r}")
                return UsdKrwRate(
                    rate=rate,
                    search_date=search_date,
                    raw_deal_bas_r=str(usd_row.get("deal_bas_r")),
                )
        raise ForexFetchError(
            f"no usd data within {lookback_days} days "
            f"(last error: {last_exc!r})" if last_exc else f"no usd data within {lookback_days} days"
        )

    async def _call(self, client: httpx.AsyncClient, search_date: date) -> list[dict]:
        params = {
            "authkey": self._api_key,
            "searchdate": search_date.strftime("%Y%m%d"),
            "data": "AP01",
        }

        @_retry
        async def _do() -> httpx.Response:
            resp = await client.get(self._base_url, params=params)
            if 500 <= resp.status_code < 600:
                raise httpx.HTTPStatusError(
                    f"koreaexim {resp.status_code}",
                    request=httpx.Request("GET", self._base_url),
                    response=resp,
                )
            return resp

        resp = await _do()
        if resp.status_code != 200:
            raise ForexFetchError(f"koreaexim status={resp.status_code}")
        try:
            body = resp.json()
        except ValueError as exc:
            raise ForexFetchError("koreaexim json decode") from exc
        if not isinstance(body, list):
            raise ForexFetchError(f"koreaexim unexpected body type: {type(body).__name__}")
        return body


def _find_usd(rows: list[dict]) -> dict | None:
    for row in rows:
        # cur_unit 은 "USD" 또는 "USD" 등 공백/주석 없이 단순. 안전하게 strip.
        unit = str(row.get("cur_unit") or "").strip().upper()
        if unit == "USD":
            return row
    return None


def _parse_deal_bas_r(raw: str | None) -> int | None:
    """매매기준율 문자열("1,392.5") → 정수 KRW 반올림."""
    if raw is None:
        return None
    cleaned = str(raw).replace(",", "").strip()
    if not cleaned:
        return None
    try:
        dec = Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None
    return int(dec.quantize(Decimal("1")))
