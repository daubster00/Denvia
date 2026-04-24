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
    retry_if_exception,
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


def _retryable_http_error(exc: BaseException) -> bool:
    """5xx + 네트워크/타임아웃만 재시도. 4xx는 즉시 실패."""
    if isinstance(exc, httpx.HTTPStatusError):
        return 500 <= exc.response.status_code < 600
    if isinstance(exc, (httpx.RequestError, httpx.TimeoutException)):
        return True
    return False


_retry = retry(
    retry=retry_if_exception(_retryable_http_error),
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
        # 마지막 authorize 호출의 state — exchange_code에서 동일 값을 전달하기 위해 기억
        # 네이버 사양은 token endpoint에서도 authorize state와 동일 값을 요구한다.
        self._last_state: str = ""

    def get_authorization_url(self, state: str) -> str:
        # scope는 네이버 앱 콘솔에서 허용된 항목만 유효. email은 기본 허용.
        # 동의 범위를 코드에서 명시하여 provider 응답 스키마 변화를 줄인다.
        params = {
            "response_type": "code",
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "state": state,
            "scope": "name email",
        }
        self._last_state = state
        return f"{_AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str, state: str = "") -> dict:
        # 네이버 사양: authorize 시 전달한 state와 동일 값을 token endpoint에도 요구.
        # state 인자가 비면 최근 authorize 시의 state로 폴백(같은 인스턴스에서 호출된 경우).
        effective_state = state or self._last_state
        params = {
            "grant_type": "authorization_code",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "code": code,
            "state": effective_state,
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                @_retry
                async def _do() -> httpx.Response:
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
            logger.exception("auth.oauth.provider_http_error", provider="naver", phase="token")
            raise OAuthProviderUnavailable("naver", "token_http_error") from exc

        if resp.status_code != 200:
            raise OAuthProviderInvalidResponse("naver", f"token status={resp.status_code}")

        try:
            body = resp.json()
        except ValueError as exc:
            raise OAuthProviderInvalidResponse("naver", "token json decode") from exc

        # 네이버 token 응답은 에러 시에도 200 반환하고 body에 error 필드를 담는다.
        if body.get("error"):
            raise OAuthProviderInvalidResponse("naver", f"token error={body.get('error')}")
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
            logger.exception("auth.oauth.provider_http_error", provider="naver", phase="profile")
            raise OAuthProviderUnavailable("naver", "profile_http_error") from exc

        if resp.status_code != 200:
            raise OAuthProviderInvalidResponse("naver", f"profile status={resp.status_code}")

        try:
            body = resp.json()
        except ValueError as exc:
            raise OAuthProviderInvalidResponse("naver", "profile json decode") from exc

        # 네이버 profile 응답 형식: {"resultcode":"00","message":"success","response":{...}}
        if body.get("resultcode") != "00":
            raise OAuthProviderInvalidResponse(
                "naver",
                f"resultcode={body.get('resultcode')}",
            )

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
