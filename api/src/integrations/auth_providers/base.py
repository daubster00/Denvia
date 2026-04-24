"""OAuth Provider 포트 인터페이스 — Story 1.6."""

from typing import Literal, Protocol, TypedDict


ProviderName = Literal["kakao", "google", "naver"]


class OAuthProfile(TypedDict):
    """Provider가 반환하는 표준화된 프로필."""

    provider_sub: str
    email: str
    phone: str | None  # Google OIDC · 비즈검수 전 Kakao는 None


class OAuthProvider(Protocol):
    """OAuth 2.0 Authorization Code Flow 포트."""

    name: ProviderName

    def get_authorization_url(self, state: str) -> str:
        """authorize URL 생성 — state는 호출자가 Redis에 기록 후 전달."""
        ...

    async def exchange_code(self, code: str, state: str) -> dict:
        """code → access_token 교환. {'access_token': str, ...} 반환.

        네이버는 token endpoint에도 authorize state와 동일 값을 요구하므로 state 인자를 필수로 한다.
        다른 provider는 state를 사용하지 않을 수 있다.
        """
        ...

    async def fetch_profile(self, access_token: str) -> OAuthProfile:
        """access_token → OAuthProfile 조회."""
        ...


class OAuthProviderUnavailable(Exception):
    """Provider HTTP 호출이 3회 재시도 후에도 실패."""

    code: str = "OAUTH_PROVIDER_UNAVAILABLE"
    http_status: int = 502

    def __init__(self, provider: str, reason: str = ""):
        super().__init__(f"{provider} unavailable: {reason}")
        self.provider = provider
        self.reason = reason


class OAuthProviderInvalidResponse(Exception):
    """Provider 응답 스키마가 예상과 다름(필수 필드 누락 등) — 5xx와 구분."""

    code: str = "OAUTH_PROVIDER_INVALID_RESPONSE"
    http_status: int = 502

    def __init__(self, provider: str, reason: str = ""):
        super().__init__(f"{provider} invalid response: {reason}")
        self.provider = provider
        self.reason = reason
