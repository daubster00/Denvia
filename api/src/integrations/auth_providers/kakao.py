"""Kakao OAuth 2.0 Provider — Story 1.6.

- authorize: https://kauth.kakao.com/oauth/authorize
- token: https://kauth.kakao.com/oauth/token (form-encoded POST)
- profile: https://kapi.kakao.com/v2/user/me (Bearer)

주의: `phone_number` 스코프는 비즈 앱 심사가 필요하므로 개발 단계에서는
대부분 phone=None 반환을 가정하고 AC-5(SMS 보충) 경로가 기본 플로우.
"""

from __future__ import annotations

import re
from datetime import date
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

_AUTHORIZE_URL = "https://kauth.kakao.com/oauth/authorize"
_TOKEN_URL = "https://kauth.kakao.com/oauth/token"
_PROFILE_URL = "https://kapi.kakao.com/v2/user/me"


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


class KakaoProvider:
    name = "kakao"

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri

    def get_authorization_url(self, state: str) -> str:
        # prompt=login: 카카오 세션이 남아있어도 매번 로그인/계정선택 화면을 강제.
        # 공유 기기에서 다른 사용자가 본인 계정으로 로그인하거나, provider-collision
        # 알림이 무한 재노출되는 것을 방지한다.
        # 운영 카카오 비즈니스 앱은 콘솔에서 이름·성별·생일·생년·휴대전화·배송지
        # 동의항목이 승인되어 있다. scope는 콘솔과의 정합성 표기 — 미승인 항목은
        # provider가 응답에 포함하지 않으므로 자동으로 None 폴백된다.
        scope_items = [
            "account_email",
            "name",
            "gender",
            "birthday",
            "birthyear",
            "phone_number",
            "shipping_address",
        ]
        params = {
            "response_type": "code",
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "state": state,
            "scope": " ".join(scope_items),
            "prompt": "login",
        }
        return f"{_AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str, state: str = "") -> dict:
        # Kakao는 token endpoint에 state를 요구하지 않는다 — 시그니처 호환용.
        _ = state
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
            logger.exception("auth.oauth.provider_http_error", provider="kakao", phase="token")
            raise OAuthProviderUnavailable("kakao", "token_http_error") from exc

        if resp.status_code != 200:
            raise OAuthProviderInvalidResponse("kakao", f"token status={resp.status_code}")

        try:
            body = resp.json()
        except ValueError as exc:
            raise OAuthProviderInvalidResponse("kakao", "token json decode") from exc
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
            logger.exception("auth.oauth.provider_http_error", provider="kakao", phase="profile")
            raise OAuthProviderUnavailable("kakao", "profile_http_error") from exc

        if resp.status_code != 200:
            raise OAuthProviderInvalidResponse("kakao", f"profile status={resp.status_code}")

        try:
            body = resp.json()
        except ValueError as exc:
            raise OAuthProviderInvalidResponse("kakao", "profile json decode") from exc
        sub = body.get("id")
        if sub is None:
            raise OAuthProviderInvalidResponse("kakao", "no id")

        account = body.get("kakao_account", {}) or {}
        email = account.get("email")
        if not email:
            raise OAuthProviderInvalidResponse("kakao", "no email")
        # 미검증 이메일로 계정 탈취 방지 — 카카오가 명시적으로 False인 경우만 거부
        # (필드 부재 시 True 간주: 비즈검수 전 앱은 이 필드를 제공하지 않는 경우가 있음)
        if account.get("is_email_verified", True) is False:
            raise OAuthProviderInvalidResponse("kakao", "email_unverified")

        phone_raw = account.get("phone_number")
        # 미인증 phone은 SMS 보충 경로 강제 — phone=None 취급
        phone_verified = account.get("is_phone_number_verified", True)
        if phone_raw and phone_verified is not False:
            phone = _normalize_kr_phone(phone_raw)
        else:
            phone = None

        # 추가 동의 항목 — 콘솔에서 승인 + 사용자가 동의한 경우에만 채워진다.
        # `*_needs_agreement=True`(추가 동의 필요)면 값 없음으로 간주 — 비동의 폴백.
        name = _account_field(account, "name")
        gender = _kakao_gender(account)
        birthdate = _compose_birthdate(
            account.get("birthyear") if not account.get("birthyear_needs_agreement") else None,
            account.get("birthday") if not account.get("birthday_needs_agreement") else None,
        )
        # shipping_addresses → 기본 주소 1건 추출 (도로명 우선, 없으면 첫 번째).
        postcode, address_road, address_detail = _kakao_shipping_address(account)

        profile: OAuthProfile = {
            "provider_sub": str(sub),
            "email": str(email).lower().strip(),
            "phone": phone,
            "name": name,
            "gender": gender,
            "birthdate": birthdate,
            "postcode": postcode,
            "address_road": address_road,
            "address_detail": address_detail,
        }
        return profile


def _normalize_kr_phone(raw: str) -> str | None:
    """'+82 10-1234-5678' / '010-1234-5678' → '01012345678'."""
    digits = re.sub(r"[^0-9]", "", raw)
    if digits.startswith("82"):
        digits = "0" + digits[2:]
    if re.match(r"^010\d{8}$", digits):
        return digits
    return None


def _account_field(account: dict, key: str) -> str | None:
    """kakao_account의 단순 문자열 필드 추출 — `*_needs_agreement=True`면 None 폴백."""
    if account.get(f"{key}_needs_agreement") is True:
        return None
    val = account.get(key)
    if not isinstance(val, str):
        return None
    stripped = val.strip()
    return stripped or None


def _kakao_gender(account: dict) -> str | None:
    """kakao_account.gender: 'female'|'male'|기타 → 표준화. needs_agreement 시 None."""
    if account.get("gender_needs_agreement") is True:
        return None
    val = account.get("gender")
    if not isinstance(val, str):
        return None
    norm = val.strip().lower()
    if norm in ("male", "female"):
        return norm
    return None


def _compose_birthdate(year: object, mmdd: object) -> date | None:
    """birthyear='YYYY' + birthday='MMDD' → date. 잘못된 값이면 None."""
    if not isinstance(year, str) or not isinstance(mmdd, str):
        return None
    y = year.strip()
    md = mmdd.strip()
    if not re.match(r"^\d{4}$", y) or not re.match(r"^\d{4}$", md):
        return None
    try:
        return date(int(y), int(md[:2]), int(md[2:4]))
    except ValueError:
        return None


def _kakao_shipping_address(account: dict) -> tuple[str | None, str | None, str | None]:
    """kakao_account.shipping_addresses → (postcode, road, detail).

    기본 주소(is_default=True) 우선, 그 다음 첫 번째 항목. 도로명 우선 — type='NEW'면
    base_address를 도로명으로 본다. 'OLD'면 도로명 컬럼은 비우고 detail에 합쳐 둔다.
    동의 미승인(`shipping_addresses_needs_agreement=True`)이면 모두 None.
    """
    if account.get("shipping_addresses_needs_agreement") is True:
        return None, None, None
    addrs = account.get("shipping_addresses")
    if not isinstance(addrs, list) or not addrs:
        return None, None, None

    chosen: dict | None = None
    for a in addrs:
        if isinstance(a, dict) and a.get("is_default") is True:
            chosen = a
            break
    if chosen is None:
        first = addrs[0]
        if isinstance(first, dict):
            chosen = first
    if chosen is None:
        return None, None, None

    zone = chosen.get("zone_number")
    postcode = zone.strip() if isinstance(zone, str) and zone.strip() else None
    base = chosen.get("base_address")
    base_str = base.strip() if isinstance(base, str) and base.strip() else None
    detail = chosen.get("detail_address")
    detail_str = detail.strip() if isinstance(detail, str) and detail.strip() else None

    addr_type = chosen.get("type")
    if isinstance(addr_type, str) and addr_type.strip().upper() == "OLD":
        # 지번 주소 — 도로명 컬럼은 비우고 base를 detail 앞에 합쳐 보존.
        combined = base_str if detail_str is None else (
            f"{base_str} {detail_str}" if base_str else detail_str
        )
        return postcode, None, combined
    return postcode, base_str, detail_str
