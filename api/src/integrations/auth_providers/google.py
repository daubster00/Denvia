"""Google OAuth 2.0 / OIDC Provider — Story 1.6.

- authorize: https://accounts.google.com/o/oauth2/v2/auth
- token: https://oauth2.googleapis.com/token
- userinfo: https://openidconnect.googleapis.com/v1/userinfo

Google OIDC 표준은 phone 스코프를 제공하지 않는다(phone_number 클레임 미지원).
→ phone=None 상수 반환. AC-5(SMS 보충) 경로 강제.
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

_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


_retry = retry(
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.RequestError, httpx.TimeoutException)),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(3),
    reraise=True,
)


class GoogleProvider:
    name = "google"

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
            "scope": "openid email profile",
            "access_type": "online",
            "prompt": "select_account",
        }
        return f"{_AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> dict:
        data = {
            "grant_type": "authorization_code",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "redirect_uri": self._redirect_uri,
            "code": code,
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                @_retry
                async def _do() -> httpx.Response:
                    resp = await client.post(_TOKEN_URL, data=data)
                    if 500 <= resp.status_code < 600:
                        raise httpx.HTTPStatusError(
                            f"google token {resp.status_code}",
                            request=httpx.Request("POST", _TOKEN_URL),
                            response=resp,
                        )
                    return resp

                resp = await _do()
        except (RetryError, httpx.HTTPStatusError, httpx.RequestError, httpx.TimeoutException) as exc:
            raise OAuthProviderUnavailable("google", repr(exc)) from exc

        if resp.status_code != 200:
            raise OAuthProviderInvalidResponse("google", f"token status={resp.status_code}")

        body = resp.json()
        if not body.get("access_token"):
            raise OAuthProviderInvalidResponse("google", "no access_token")
        return body

    async def fetch_profile(self, access_token: str) -> OAuthProfile:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                @_retry
                async def _do() -> httpx.Response:
                    resp = await client.get(
                        _USERINFO_URL,
                        headers={"Authorization": f"Bearer {access_token}"},
                    )
                    if 500 <= resp.status_code < 600:
                        raise httpx.HTTPStatusError(
                            f"google userinfo {resp.status_code}",
                            request=httpx.Request("GET", _USERINFO_URL),
                            response=resp,
                        )
                    return resp

                resp = await _do()
        except (RetryError, httpx.HTTPStatusError, httpx.RequestError, httpx.TimeoutException) as exc:
            raise OAuthProviderUnavailable("google", repr(exc)) from exc

        if resp.status_code != 200:
            raise OAuthProviderInvalidResponse("google", f"userinfo status={resp.status_code}")

        body = resp.json()
        sub = body.get("sub")
        email = body.get("email")
        if not sub:
            raise OAuthProviderInvalidResponse("google", "no sub")
        if not email:
            raise OAuthProviderInvalidResponse("google", "no email")

        return {
            "provider_sub": str(sub),
            "email": str(email).lower().strip(),
            "phone": None,
        }
