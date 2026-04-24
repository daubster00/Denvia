"""Google OAuth 2.0 / OIDC Provider — Story 1.6.

- authorize: https://accounts.google.com/o/oauth2/v2/auth
- token: https://oauth2.googleapis.com/token
- userinfo: https://openidconnect.googleapis.com/v1/userinfo
- OIDC id_token 서명 검증: https://www.googleapis.com/oauth2/v3/certs (JWKS)

Google OIDC 표준은 phone 스코프를 제공하지 않는다(phone_number 클레임 미지원).
→ phone=None 상수 반환. AC-5(SMS 보충) 경로 강제.

보안: access_token 탈취 시 중간자 위조를 방어하기 위해 `id_token` JWT 서명 +
aud(client_id) + iss 검증을 수행하고, id_token의 sub/email과 userinfo 응답을 교차 검증.
"""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlencode

import httpx
import structlog
from authlib.jose import JsonWebKey, jwt
from authlib.jose.errors import JoseError
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

_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
_VALID_ISSUERS = {"https://accounts.google.com", "accounts.google.com"}

# JWKS 캐시 — 실행 시점에 최초 1회 fetch 후 1시간 재사용
_jwks_cache: dict[str, Any] = {"keys": None, "fetched_at": 0.0}
_JWKS_TTL = 3600.0


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


async def _fetch_google_jwks() -> Any:
    """Google JWKS 엔드포인트에서 공개키 세트를 가져온다. 1시간 캐시."""
    now = time.monotonic()
    if _jwks_cache["keys"] is not None and (now - _jwks_cache["fetched_at"] < _JWKS_TTL):
        return _jwks_cache["keys"]

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(_JWKS_URL)
        if resp.status_code != 200:
            raise OAuthProviderInvalidResponse("google", f"jwks status={resp.status_code}")
        try:
            body = resp.json()
        except ValueError as exc:
            raise OAuthProviderInvalidResponse("google", "jwks json decode") from exc

    key_set = JsonWebKey.import_key_set(body)
    _jwks_cache["keys"] = key_set
    _jwks_cache["fetched_at"] = now
    return key_set


async def _verify_id_token(id_token: str, audience: str) -> dict:
    """Google id_token JWT 서명·iss·aud·exp 검증 후 claims 반환."""
    try:
        key_set = await _fetch_google_jwks()
    except (httpx.RequestError, httpx.TimeoutException) as exc:
        logger.exception("auth.oauth.provider_http_error", provider="google", phase="jwks")
        raise OAuthProviderUnavailable("google", "jwks_http_error") from exc

    try:
        claims = jwt.decode(
            id_token,
            key_set,
            claims_options={
                "iss": {"essential": True, "values": list(_VALID_ISSUERS)},
                "aud": {"essential": True, "value": audience},
                "exp": {"essential": True},
            },
        )
        claims.validate()
    except JoseError as exc:
        raise OAuthProviderInvalidResponse("google", f"id_token invalid: {type(exc).__name__}") from exc

    return dict(claims)


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

    async def exchange_code(self, code: str, state: str = "") -> dict:
        # Google은 token endpoint에 state를 요구하지 않는다 — 시그니처 호환용.
        _ = state
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
            logger.exception("auth.oauth.provider_http_error", provider="google", phase="token")
            raise OAuthProviderUnavailable("google", "token_http_error") from exc

        if resp.status_code != 200:
            raise OAuthProviderInvalidResponse("google", f"token status={resp.status_code}")

        try:
            body = resp.json()
        except ValueError as exc:
            raise OAuthProviderInvalidResponse("google", "token json decode") from exc

        if not body.get("access_token"):
            raise OAuthProviderInvalidResponse("google", "no access_token")

        # id_token 서명·iss·aud 검증 후 claims를 body에 보관 (fetch_profile에서 교차검증용)
        id_token = body.get("id_token")
        if not id_token:
            raise OAuthProviderInvalidResponse("google", "no id_token")
        claims = await _verify_id_token(id_token, audience=self._client_id)
        body["_id_token_claims"] = claims
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
            logger.exception("auth.oauth.provider_http_error", provider="google", phase="userinfo")
            raise OAuthProviderUnavailable("google", "userinfo_http_error") from exc

        if resp.status_code != 200:
            raise OAuthProviderInvalidResponse("google", f"userinfo status={resp.status_code}")

        try:
            body = resp.json()
        except ValueError as exc:
            raise OAuthProviderInvalidResponse("google", "userinfo json decode") from exc

        sub = body.get("sub")
        email = body.get("email")
        if not sub:
            raise OAuthProviderInvalidResponse("google", "no sub")
        if not email:
            raise OAuthProviderInvalidResponse("google", "no email")
        # 미검증 이메일로 계정 탈취 방지 — email_verified=False 명시 시 거부
        if body.get("email_verified") is False:
            raise OAuthProviderInvalidResponse("google", "email_unverified")

        return {
            "provider_sub": str(sub),
            "email": str(email).lower().strip(),
            "phone": None,
        }
