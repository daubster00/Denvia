"""OAuth Provider 어댑터 유닛 테스트 — Story 1.6.

httpx.MockTransport로 외부 호출을 가짜로 대체하여 token 교환·profile 조회의
정상·실패 경로를 검증한다. tenacity 재시도와 5xx 최종 실패 시
OAuthProviderUnavailable 전환을 포함한다.
"""

from __future__ import annotations

import json

import httpx
import pytest

from api.src.integrations.auth_providers import (
    OAuthProviderInvalidResponse,
    OAuthProviderUnavailable,
)
from api.src.integrations.auth_providers.google import GoogleProvider
from api.src.integrations.auth_providers.kakao import KakaoProvider
from api.src.integrations.auth_providers.naver import NaverProvider


# ── Kakao ─────────────────────────────────────────────────────────────────────

class TestKakaoProvider:
    def test_authorization_url_includes_state(self):
        p = KakaoProvider("CID", "CSECRET", "http://localhost/cb")
        url = p.get_authorization_url(state="abc123")
        assert url.startswith("https://kauth.kakao.com/oauth/authorize?")
        assert "state=abc123" in url
        assert "client_id=CID" in url
        assert "redirect_uri=http" in url

    @pytest.mark.asyncio
    async def test_exchange_code_success(self, monkeypatch):
        p = KakaoProvider("CID", "", "http://localhost/cb")

        called = {"n": 0}

        async def fake_post(self, url, *args, **kwargs):
            called["n"] += 1
            return httpx.Response(200, json={"access_token": "AT"})

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

        result = await p.exchange_code(code="code-xyz")
        assert result["access_token"] == "AT"
        assert called["n"] == 1

    @pytest.mark.asyncio
    async def test_fetch_profile_with_phone(self, monkeypatch):
        p = KakaoProvider("CID", "", "http://localhost/cb")

        async def fake_get(self, url, *args, **kwargs):
            return httpx.Response(
                200,
                json={
                    "id": 123456789,
                    "kakao_account": {
                        "email": "user@kakao.com",
                        "phone_number": "+82 10-1234-5678",
                    },
                },
            )

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        profile = await p.fetch_profile("AT")
        assert profile["provider_sub"] == "123456789"
        assert profile["email"] == "user@kakao.com"
        assert profile["phone"] == "01012345678"

    @pytest.mark.asyncio
    async def test_fetch_profile_without_phone(self, monkeypatch):
        p = KakaoProvider("CID", "", "http://localhost/cb")

        async def fake_get(self, url, *args, **kwargs):
            return httpx.Response(
                200,
                json={
                    "id": 999,
                    "kakao_account": {"email": "user@kakao.com"},
                },
            )

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        profile = await p.fetch_profile("AT")
        assert profile["phone"] is None

    @pytest.mark.asyncio
    async def test_exchange_code_retries_on_5xx_then_fails(self, monkeypatch):
        p = KakaoProvider("CID", "", "http://localhost/cb")
        calls = {"n": 0}

        async def fake_post(self, url, *args, **kwargs):
            calls["n"] += 1
            return httpx.Response(503, text="unavailable")

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

        # 재시도 wait 시간을 0으로 줄이기 (빠른 테스트)
        from api.src.integrations.auth_providers import kakao as kakao_mod
        from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_none
        monkeypatch.setattr(
            kakao_mod,
            "_retry",
            retry(
                retry=retry_if_exception_type(
                    (httpx.HTTPStatusError, httpx.RequestError, httpx.TimeoutException)
                ),
                wait=wait_none(),
                stop=stop_after_attempt(3),
                reraise=True,
            ),
        )

        with pytest.raises(OAuthProviderUnavailable):
            await p.exchange_code("c")
        assert calls["n"] == 3  # 3회 재시도 후 실패

    @pytest.mark.asyncio
    async def test_exchange_code_4xx_does_not_retry(self, monkeypatch):
        p = KakaoProvider("CID", "", "http://localhost/cb")
        calls = {"n": 0}

        async def fake_post(self, url, *args, **kwargs):
            calls["n"] += 1
            return httpx.Response(400, text="bad code")

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

        with pytest.raises(OAuthProviderInvalidResponse):
            await p.exchange_code("c")
        assert calls["n"] == 1  # 4xx는 재시도 안 함


# ── Google ────────────────────────────────────────────────────────────────────

class TestGoogleProvider:
    def test_authorization_url_scopes(self):
        p = GoogleProvider("GID", "GS", "http://localhost/cb")
        url = p.get_authorization_url("s1")
        assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
        assert "scope=openid+email+profile" in url or "openid%20email%20profile" in url
        assert "state=s1" in url

    @pytest.mark.asyncio
    async def test_fetch_profile_phone_always_none(self, monkeypatch):
        p = GoogleProvider("GID", "GS", "http://localhost/cb")

        async def fake_get(self, url, *args, **kwargs):
            return httpx.Response(
                200,
                json={"sub": "google-abc", "email": "User@gmail.com"},
            )

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        profile = await p.fetch_profile("AT")
        assert profile["provider_sub"] == "google-abc"
        assert profile["email"] == "user@gmail.com"
        assert profile["phone"] is None


# ── Naver ─────────────────────────────────────────────────────────────────────

class TestNaverProvider:
    def test_authorization_url(self):
        p = NaverProvider("NID", "NS", "http://localhost/cb")
        url = p.get_authorization_url("st")
        assert url.startswith("https://nid.naver.com/oauth2.0/authorize?")
        assert "state=st" in url

    @pytest.mark.asyncio
    async def test_fetch_profile_mobile(self, monkeypatch):
        p = NaverProvider("NID", "NS", "http://localhost/cb")

        async def fake_get(self, url, *args, **kwargs):
            return httpx.Response(
                200,
                json={
                    "resultcode": "00",
                    "message": "success",
                    "response": {
                        "id": "naver-xyz",
                        "email": "u@naver.com",
                        "mobile": "010-2222-3333",
                    },
                },
            )

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        profile = await p.fetch_profile("AT")
        assert profile["provider_sub"] == "naver-xyz"
        assert profile["email"] == "u@naver.com"
        assert profile["phone"] == "01022223333"

    @pytest.mark.asyncio
    async def test_fetch_profile_missing_email_raises(self, monkeypatch):
        p = NaverProvider("NID", "NS", "http://localhost/cb")

        async def fake_get(self, url, *args, **kwargs):
            return httpx.Response(200, json={"response": {"id": "nx"}})

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        with pytest.raises(OAuthProviderInvalidResponse):
            await p.fetch_profile("AT")
