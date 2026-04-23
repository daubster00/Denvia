"""OAuth Provider 팩토리 — Story 1.6."""

from __future__ import annotations

from fastapi import HTTPException

from api.src.integrations.auth_providers.base import OAuthProvider, ProviderName
from api.src.integrations.auth_providers.google import GoogleProvider
from api.src.integrations.auth_providers.kakao import KakaoProvider
from api.src.integrations.auth_providers.naver import NaverProvider
from api.src.settings import settings


_VALID: set[ProviderName] = {"kakao", "google", "naver"}


def get_provider(name: str) -> OAuthProvider:
    """provider 이름으로 어댑터 인스턴스 반환. 잘못된 이름은 404."""
    if name not in _VALID:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "OAUTH_PROVIDER_UNKNOWN",
                "message": "지원하지 않는 소셜 로그인입니다.",
            },
        )

    if name == "kakao":
        return KakaoProvider(
            client_id=settings.kakao_client_id,
            client_secret=settings.kakao_client_secret,
            redirect_uri=settings.kakao_redirect_uri,
        )
    if name == "google":
        return GoogleProvider(
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            redirect_uri=settings.google_redirect_uri,
        )
    # naver
    return NaverProvider(
        client_id=settings.naver_client_id,
        client_secret=settings.naver_client_secret,
        redirect_uri=settings.naver_redirect_uri,
    )
