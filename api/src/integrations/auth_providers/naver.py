"""Naver OAuth 2.0 Provider — Story 1.6.

- authorize: https://nid.naver.com/oauth2.0/authorize
- token: https://nid.naver.com/oauth2.0/token (쿼리 파라미터)
- profile: https://openapi.naver.com/v1/nid/me (Bearer)

네이버 `mobile` 스코프는 앱 신청 시 상대적으로 승인 쉬움. 초기 개발에서는 phone=None로
취급해도 AC-5 경로로 폴백되어 문제 없음.
"""

from __future__ import annotations

import re
from urllib.parse import urlencode

import httpx
import structlog
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from api.src.integrations.auth_providers.base import (
    OAuthProfile,
    OAuthProviderInvalidResponse,
    OAuthProviderUnavailable,
)

logger = structlog.get_logger(__name__)

_AUTHORIZE_URL = "https://nid.naver.com/oauth2.0/authorize"
_TOKEN_URL = "https://nid.naver.com/oauth2.0/token"
_PROFILE_URL = "https://openapi.naver.com/v1/nid/me"


_retry = retry(
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.RequestError, httpx.TimeoutException)),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(3),
    reraise=True,
)


class NaverProvider:
    name = "naver"

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri

    def get_authorization_url(self, state: str) -> str:
        params = {
            "response_type": "code",
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "state": state,
        }
        return f"{_AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> dict:
        params = {
            "grant_type": "authorization_code",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "code": code,
            "state": "",  # 네이버는 state를 token endpoint에도 요구하지만 빈 값 허용
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                @_retry
                async def _do() -> httpx.Response:
                    # 네이버는 GET으로 token 교환
                    resp = await client.get(_TOKEN_URL, params=params)
                    if 500 <= resp.status_code < 600:
                        raise httpx.HTTPStatusError(
                            f"naver token {resp.status_code}",
                            request=httpx.Request("GET", _TOKEN_URL),
                            response=resp,
                        )
                    return resp

                resp = await _do()
        except (RetryError, httpx.HTTPStatusError, httpx.RequestError, httpx.TimeoutException) as exc:
            raise OAuthProviderUnavailable("naver", repr(exc)) from exc

        if resp.status_code != 200:
            raise OAuthProviderInvalidResponse("naver", f"token status={resp.status_code}")

        body = resp.json()
        if not body.get("access_token"):
            raise OAuthProviderInvalidResponse("naver", "no access_token")
        return body

    async def fetch_profile(self, access_token: str) -> OAuthProfile:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                @_retry
                async def _do() -> httpx.Response:
                    resp = await client.get(
                        _PROFILE_URL,
                        headers={"Authorization": f"Bearer {access_token}"},
                    )
                    if 500 <= resp.status_code < 600:
                        raise httpx.HTTPStatusError(
                            f"naver profile {resp.status_code}",
                            request=httpx.Request("GET", _PROFILE_URL),
                            response=resp,
                        )
                    return resp

                resp = await _do()
        except (RetryError, httpx.HTTPStatusError, httpx.RequestError, httpx.TimeoutException) as exc:
            raise OAuthProviderUnavailable("naver", repr(exc)) from exc

        if resp.status_code != 200:
            raise OAuthProviderInvalidResponse("naver", f"profile status={resp.status_code}")

        body = resp.json()
        response = body.get("response", {}) or {}
        sub = response.get("id")
        email = response.get("email")
        mobile = response.get("mobile")

        if not sub:
            raise OAuthProviderInvalidResponse("naver", "no id")
        if not email:
            raise OAuthProviderInvalidResponse("naver", "no email")

        phone = _normalize_kr_phone(mobile) if mobile else None

        return {
            "provider_sub": str(sub),
            "email": str(email).lower().strip(),
            "phone": phone,
        }


def _normalize_kr_phone(raw: str) -> str | None:
    digits = re.sub(r"[^0-9]", "", raw)
    if digits.startswith("82"):
        digits = "0" + digits[2:]
    if re.match(r"^010\d{8}$", digits):
        return digits
    return None
