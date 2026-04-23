"""Kakao OAuth 2.0 Provider — Story 1.6.

- authorize: https://kauth.kakao.com/oauth/authorize
- token: https://kauth.kakao.com/oauth/token (form-encoded POST)
- profile: https://kapi.kakao.com/v2/user/me (Bearer)

주의: `phone_number` 스코프는 비즈 앱 심사가 필요하므로 개발 단계에서는
대부분 phone=None 반환을 가정하고 AC-5(SMS 보충) 경로가 기본 플로우.
"""

from __future__ import annotations

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

_AUTHORIZE_URL = "https://kauth.kakao.com/oauth/authorize"
_TOKEN_URL = "https://kauth.kakao.com/oauth/token"
_PROFILE_URL = "https://kapi.kakao.com/v2/user/me"


def _retryable_http_error(exc: BaseException) -> bool:
    """5xx와 네트워크 오류만 재시도. 4xx는 재시도하지 않음."""
    if isinstance(exc, httpx.HTTPStatusError):
        return 500 <= exc.response.status_code < 600
    if isinstance(exc, (httpx.RequestError, httpx.TimeoutException)):
        return True
    return False


_retry = retry(
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.RequestError, httpx.TimeoutException)),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(3),
    reraise=True,
)


class KakaoProvider:
    name = "kakao"

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
            "scope": "account_email",
        }
        return f"{_AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> dict:
        data = {
            "grant_type": "authorization_code",
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "code": code,
        }
        if self._client_secret:
            data["client_secret"] = self._client_secret

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                @_retry
                async def _do() -> httpx.Response:
                    resp = await client.post(
                        _TOKEN_URL,
                        data=data,
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    )
                    if 500 <= resp.status_code < 600:
                        raise httpx.HTTPStatusError(
                            f"kakao token {resp.status_code}",
                            request=httpx.Request("POST", _TOKEN_URL),
                            response=resp,
                        )
                    return resp

                resp = await _do()
        except (RetryError, httpx.HTTPStatusError, httpx.RequestError, httpx.TimeoutException) as exc:
            raise OAuthProviderUnavailable("kakao", repr(exc)) from exc

        if resp.status_code != 200:
            raise OAuthProviderInvalidResponse("kakao", f"token status={resp.status_code}")

        body = resp.json()
        access_token = body.get("access_token")
        if not access_token:
            raise OAuthProviderInvalidResponse("kakao", "no access_token")
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
                            f"kakao profile {resp.status_code}",
                            request=httpx.Request("GET", _PROFILE_URL),
                            response=resp,
                        )
                    return resp

                resp = await _do()
        except (RetryError, httpx.HTTPStatusError, httpx.RequestError, httpx.TimeoutException) as exc:
            raise OAuthProviderUnavailable("kakao", repr(exc)) from exc

        if resp.status_code != 200:
            raise OAuthProviderInvalidResponse("kakao", f"profile status={resp.status_code}")

        body = resp.json()
        sub = body.get("id")
        if sub is None:
            raise OAuthProviderInvalidResponse("kakao", "no id")

        account = body.get("kakao_account", {}) or {}
        email = account.get("email")
        if not email:
            raise OAuthProviderInvalidResponse("kakao", "no email")

        phone_raw = account.get("phone_number")
        phone = _normalize_kr_phone(phone_raw) if phone_raw else None

        return {
            "provider_sub": str(sub),
            "email": str(email).lower().strip(),
            "phone": phone,
        }


def _normalize_kr_phone(raw: str) -> str | None:
    """'+82 10-1234-5678' / '010-1234-5678' → '01012345678'."""
    import re

    digits = re.sub(r"[^0-9]", "", raw)
    if digits.startswith("82"):
        digits = "0" + digits[2:]
    if re.match(r"^010\d{8}$", digits):
        return digits
    return None
