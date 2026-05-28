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
        # 공유 기기 / provider-collision 무한 알림 방지: 매번 카카오 로그인/계정선택 화면 강제.
        assert "prompt=login" in url

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

    @pytest.mark.asyncio
    async def test_exchange_code_timeout_raises_unavailable(self, monkeypatch):
        """TimeoutException은 재시도 대상. 3회 후 OAuthProviderUnavailable."""
        from tenacity import retry, retry_if_exception, stop_after_attempt, wait_none
        from api.src.integrations.auth_providers import kakao as kakao_mod

        p = KakaoProvider("CID", "", "http://localhost/cb")
        calls = {"n": 0}

        async def fake_post(self, url, *args, **kwargs):
            calls["n"] += 1
            raise httpx.TimeoutException("timeout")

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
        monkeypatch.setattr(
            kakao_mod,
            "_retry",
            retry(
                retry=retry_if_exception(kakao_mod._retryable_http_error),
                wait=wait_none(),
                stop=stop_after_attempt(3),
                reraise=True,
            ),
        )
        with pytest.raises(OAuthProviderUnavailable):
            await p.exchange_code("c")
        assert calls["n"] == 3

    @pytest.mark.asyncio
    async def test_exchange_code_connect_error_retries(self, monkeypatch):
        """ConnectError(네트워크 장애)도 재시도 대상."""
        from tenacity import retry, retry_if_exception, stop_after_attempt, wait_none
        from api.src.integrations.auth_providers import kakao as kakao_mod

        p = KakaoProvider("CID", "", "http://localhost/cb")
        calls = {"n": 0}

        async def fake_post(self, url, *args, **kwargs):
            calls["n"] += 1
            raise httpx.ConnectError("conn")

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
        monkeypatch.setattr(
            kakao_mod,
            "_retry",
            retry(
                retry=retry_if_exception(kakao_mod._retryable_http_error),
                wait=wait_none(),
                stop=stop_after_attempt(3),
                reraise=True,
            ),
        )
        with pytest.raises(OAuthProviderUnavailable):
            await p.exchange_code("c")
        assert calls["n"] == 3

    @pytest.mark.asyncio
    async def test_exchange_code_token_json_decode_fail(self, monkeypatch):
        """token 응답이 JSON이 아니면 OAuthProviderInvalidResponse."""
        p = KakaoProvider("CID", "", "http://localhost/cb")

        async def fake_post(self, url, *args, **kwargs):
            return httpx.Response(200, content=b"not-json-body")

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
        with pytest.raises(OAuthProviderInvalidResponse):
            await p.exchange_code("c")

    @pytest.mark.asyncio
    async def test_exchange_code_no_access_token(self, monkeypatch):
        """200이지만 access_token 누락 → OAuthProviderInvalidResponse."""
        p = KakaoProvider("CID", "", "http://localhost/cb")

        async def fake_post(self, url, *args, **kwargs):
            return httpx.Response(200, json={"token_type": "bearer"})

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
        with pytest.raises(OAuthProviderInvalidResponse):
            await p.exchange_code("c")

    @pytest.mark.asyncio
    async def test_fetch_profile_unverified_email_rejected(self, monkeypatch):
        """is_email_verified=False — OAuthProviderInvalidResponse (계정 탈취 방지)."""
        p = KakaoProvider("CID", "", "http://localhost/cb")

        async def fake_get(self, url, *args, **kwargs):
            return httpx.Response(
                200,
                json={
                    "id": 1,
                    "kakao_account": {
                        "email": "e@k.com",
                        "is_email_verified": False,
                    },
                },
            )

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        with pytest.raises(OAuthProviderInvalidResponse):
            await p.fetch_profile("AT")

    @pytest.mark.asyncio
    async def test_fetch_profile_unverified_phone_becomes_none(self, monkeypatch):
        """is_phone_number_verified=False면 phone_number가 있어도 phone=None (SMS 보충 강제)."""
        p = KakaoProvider("CID", "", "http://localhost/cb")

        async def fake_get(self, url, *args, **kwargs):
            return httpx.Response(
                200,
                json={
                    "id": 1,
                    "kakao_account": {
                        "email": "e@k.com",
                        "phone_number": "+82 10-1234-5678",
                        "is_phone_number_verified": False,
                    },
                },
            )

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        profile = await p.fetch_profile("AT")
        assert profile["phone"] is None

    @pytest.mark.asyncio
    async def test_fetch_profile_missing_kakao_account(self, monkeypatch):
        """kakao_account 필드 자체가 없으면 email 누락 → OAuthProviderInvalidResponse."""
        p = KakaoProvider("CID", "", "http://localhost/cb")

        async def fake_get(self, url, *args, **kwargs):
            return httpx.Response(200, json={"id": 1})

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        with pytest.raises(OAuthProviderInvalidResponse):
            await p.fetch_profile("AT")

    @pytest.mark.asyncio
    async def test_fetch_profile_missing_email(self, monkeypatch):
        """kakao_account는 있지만 email 누락 → OAuthProviderInvalidResponse."""
        p = KakaoProvider("CID", "", "http://localhost/cb")

        async def fake_get(self, url, *args, **kwargs):
            return httpx.Response(200, json={"id": 1, "kakao_account": {}})

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        with pytest.raises(OAuthProviderInvalidResponse):
            await p.fetch_profile("AT")

    def test_authorization_url_includes_extra_scopes(self):
        """추가 동의 항목(name·gender·birthday 등) scope 노출 — 콘솔 승인 정합용."""
        p = KakaoProvider("CID", "", "http://localhost/cb")
        url = p.get_authorization_url("st")
        # 공백은 + 또는 %20 어느 쪽으로 인코딩돼도 통과
        for keyword in ("name", "gender", "birthday", "birthyear", "phone_number", "shipping_address"):
            assert keyword in url

    @pytest.mark.asyncio
    async def test_fetch_profile_full_extras(self, monkeypatch):
        """이름·성별·생년월일·기본 배송지(도로명)까지 모두 받아오는 정상 케이스."""
        from datetime import date as _date

        p = KakaoProvider("CID", "", "http://localhost/cb")

        async def fake_get(self, url, *args, **kwargs):
            return httpx.Response(
                200,
                json={
                    "id": 42,
                    "kakao_account": {
                        "email": "u@kakao.com",
                        "phone_number": "+82 10-1234-5678",
                        "name": "홍길동",
                        "gender": "male",
                        "birthyear": "1990",
                        "birthday": "0315",
                        "shipping_addresses": [
                            {
                                "id": 1,
                                "is_default": True,
                                "type": "NEW",
                                "base_address": "서울특별시 강남구 테헤란로 123",
                                "detail_address": "5층 501호",
                                "zone_number": "06234",
                            }
                        ],
                    },
                },
            )

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        profile = await p.fetch_profile("AT")
        assert profile["name"] == "홍길동"
        assert profile["gender"] == "male"
        assert profile["birthdate"] == _date(1990, 3, 15)
        assert profile["postcode"] == "06234"
        assert profile["address_road"] == "서울특별시 강남구 테헤란로 123"
        assert profile["address_detail"] == "5층 501호"

    @pytest.mark.asyncio
    async def test_fetch_profile_extras_needs_agreement(self, monkeypatch):
        """`*_needs_agreement=True` 항목은 None으로 폴백 — 비동의 사용자 보호."""
        p = KakaoProvider("CID", "", "http://localhost/cb")

        async def fake_get(self, url, *args, **kwargs):
            return httpx.Response(
                200,
                json={
                    "id": 1,
                    "kakao_account": {
                        "email": "u@kakao.com",
                        "name_needs_agreement": True,
                        "name": "should_be_ignored",
                        "gender_needs_agreement": True,
                        "gender": "male",
                        "birthyear_needs_agreement": True,
                        "birthyear": "1990",
                        "birthday": "0101",
                        "shipping_addresses_needs_agreement": True,
                        "shipping_addresses": [
                            {"is_default": True, "base_address": "ignored"}
                        ],
                    },
                },
            )

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        profile = await p.fetch_profile("AT")
        assert profile.get("name") is None
        assert profile.get("gender") is None
        assert profile.get("birthdate") is None
        assert profile.get("address_road") is None
        assert profile.get("postcode") is None

    @pytest.mark.asyncio
    async def test_fetch_profile_birthdate_invalid_silent_none(self, monkeypatch):
        """잘못된 생년월일(2월 30일 등)은 silent None — 가입 자체는 막지 않는다."""
        p = KakaoProvider("CID", "", "http://localhost/cb")

        async def fake_get(self, url, *args, **kwargs):
            return httpx.Response(
                200,
                json={
                    "id": 1,
                    "kakao_account": {
                        "email": "u@kakao.com",
                        "birthyear": "2024",
                        "birthday": "0230",
                    },
                },
            )

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        profile = await p.fetch_profile("AT")
        assert profile.get("birthdate") is None

    @pytest.mark.asyncio
    async def test_fetch_profile_shipping_default_picked(self, monkeypatch):
        """is_default=True 인 항목이 우선 선택된다."""
        p = KakaoProvider("CID", "", "http://localhost/cb")

        async def fake_get(self, url, *args, **kwargs):
            return httpx.Response(
                200,
                json={
                    "id": 1,
                    "kakao_account": {
                        "email": "u@kakao.com",
                        "shipping_addresses": [
                            {
                                "is_default": False,
                                "type": "NEW",
                                "base_address": "sub-road",
                                "detail_address": "B",
                                "zone_number": "11111",
                            },
                            {
                                "is_default": True,
                                "type": "NEW",
                                "base_address": "default-road",
                                "detail_address": "A",
                                "zone_number": "22222",
                            },
                        ],
                    },
                },
            )

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        profile = await p.fetch_profile("AT")
        assert profile["address_road"] == "default-road"
        assert profile["postcode"] == "22222"


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

    @pytest.mark.asyncio
    async def test_fetch_profile_unverified_email_rejected(self, monkeypatch):
        """email_verified=False — OAuthProviderInvalidResponse (계정 탈취 방지)."""
        p = GoogleProvider("GID", "GS", "http://localhost/cb")

        async def fake_get(self, url, *args, **kwargs):
            return httpx.Response(
                200,
                json={"sub": "x", "email": "e@g.com", "email_verified": False},
            )

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        with pytest.raises(OAuthProviderInvalidResponse):
            await p.fetch_profile("AT")

    @pytest.mark.asyncio
    async def test_fetch_profile_userinfo_json_decode_fail(self, monkeypatch):
        """userinfo 응답이 JSON 아니면 OAuthProviderInvalidResponse."""
        p = GoogleProvider("GID", "GS", "http://localhost/cb")

        async def fake_get(self, url, *args, **kwargs):
            return httpx.Response(200, content=b"not json")

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        with pytest.raises(OAuthProviderInvalidResponse):
            await p.fetch_profile("AT")

    @pytest.mark.asyncio
    async def test_exchange_code_retries_on_5xx(self, monkeypatch):
        """Google token endpoint 5xx 재시도 3회 후 OAuthProviderUnavailable."""
        from tenacity import retry, retry_if_exception, stop_after_attempt, wait_none
        from api.src.integrations.auth_providers import google as google_mod

        p = GoogleProvider("GID", "GS", "http://localhost/cb")
        calls = {"n": 0}

        async def fake_post(self, url, *args, **kwargs):
            calls["n"] += 1
            return httpx.Response(503, text="unavailable")

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
        monkeypatch.setattr(
            google_mod,
            "_retry",
            retry(
                retry=retry_if_exception(google_mod._retryable_http_error),
                wait=wait_none(),
                stop=stop_after_attempt(3),
                reraise=True,
            ),
        )
        with pytest.raises(OAuthProviderUnavailable):
            await p.exchange_code("c")
        assert calls["n"] == 3

    @pytest.mark.asyncio
    async def test_exchange_code_4xx_does_not_retry(self, monkeypatch):
        """Google token 4xx는 재시도 없이 OAuthProviderInvalidResponse."""
        p = GoogleProvider("GID", "GS", "http://localhost/cb")
        calls = {"n": 0}

        async def fake_post(self, url, *args, **kwargs):
            calls["n"] += 1
            return httpx.Response(400, json={"error": "invalid_grant"})

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
        with pytest.raises(OAuthProviderInvalidResponse):
            await p.exchange_code("c")
        assert calls["n"] == 1

    @pytest.mark.asyncio
    async def test_exchange_code_missing_id_token(self, monkeypatch):
        """token 응답에 id_token 누락 → OAuthProviderInvalidResponse (OIDC 계약 위반)."""
        p = GoogleProvider("GID", "GS", "http://localhost/cb")

        async def fake_post(self, url, *args, **kwargs):
            return httpx.Response(200, json={"access_token": "AT"})

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
        with pytest.raises(OAuthProviderInvalidResponse):
            await p.exchange_code("c")

    @pytest.mark.asyncio
    async def test_exchange_code_id_token_bad_iss(self, monkeypatch):
        """id_token의 iss가 Google이 아니면 OAuthProviderInvalidResponse."""
        from api.src.integrations.auth_providers import google as google_mod

        p = GoogleProvider("GID", "GS", "http://localhost/cb")

        async def fake_post(self, url, *args, **kwargs):
            return httpx.Response(200, json={"access_token": "AT", "id_token": "fake.jwt.here"})

        # _verify_id_token을 bad iss raise로 mock
        async def fake_verify(id_token, audience):
            raise OAuthProviderInvalidResponse("google", "id_token invalid: InvalidClaimError")

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
        monkeypatch.setattr(google_mod, "_verify_id_token", fake_verify)
        with pytest.raises(OAuthProviderInvalidResponse):
            await p.exchange_code("c")

    @pytest.mark.asyncio
    async def test_jwks_fetch_failure_raises_unavailable(self, monkeypatch):
        """JWKS 엔드포인트 네트워크 실패 시 OAuthProviderUnavailable."""
        from api.src.integrations.auth_providers import google as google_mod

        # JWKS 캐시 무효화 (다른 테스트에서 채워졌을 가능성)
        google_mod._jwks_cache["keys"] = None
        google_mod._jwks_cache["fetched_at"] = 0.0

        async def fake_get(self, url, *args, **kwargs):
            raise httpx.ConnectError("jwks unreachable")

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        with pytest.raises(OAuthProviderUnavailable):
            await google_mod._verify_id_token("fake.jwt.here", audience="GID")

    @pytest.mark.asyncio
    async def test_jwks_fetch_non_200_raises_invalid(self, monkeypatch):
        """JWKS 엔드포인트 비-200 응답 → OAuthProviderInvalidResponse."""
        from api.src.integrations.auth_providers import google as google_mod

        google_mod._jwks_cache["keys"] = None
        google_mod._jwks_cache["fetched_at"] = 0.0

        async def fake_get(self, url, *args, **kwargs):
            return httpx.Response(503, text="unavailable")

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        with pytest.raises(OAuthProviderInvalidResponse):
            await google_mod._verify_id_token("fake.jwt.here", audience="GID")


# ── Naver ─────────────────────────────────────────────────────────────────────

class TestNaverProvider:
    def test_authorization_url(self):
        p = NaverProvider("NID", "NS", "http://localhost/cb")
        url = p.get_authorization_url("st")
        assert url.startswith("https://nid.naver.com/oauth2.0/authorize?")
        assert "state=st" in url
        # 공유 기기 / provider-collision 무한 알림 방지: 매번 네이버 재인증 화면 강제.
        assert "auth_type=reauthenticate" in url

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

    @pytest.mark.asyncio
    async def test_fetch_profile_resultcode_not_success(self, monkeypatch):
        """resultcode != '00'면 성공이 아님 → OAuthProviderInvalidResponse."""
        p = NaverProvider("NID", "NS", "http://localhost/cb")

        async def fake_get(self, url, *args, **kwargs):
            return httpx.Response(
                200,
                json={"resultcode": "024", "message": "auth fail", "response": {}},
            )

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        with pytest.raises(OAuthProviderInvalidResponse):
            await p.fetch_profile("AT")

    @pytest.mark.asyncio
    async def test_fetch_profile_missing_id_raises(self, monkeypatch):
        """resultcode=00이지만 response.id 누락 → OAuthProviderInvalidResponse."""
        p = NaverProvider("NID", "NS", "http://localhost/cb")

        async def fake_get(self, url, *args, **kwargs):
            return httpx.Response(
                200,
                json={"resultcode": "00", "response": {"email": "e@n.com"}},
            )

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        with pytest.raises(OAuthProviderInvalidResponse):
            await p.fetch_profile("AT")

    @pytest.mark.asyncio
    async def test_exchange_code_passes_state(self, monkeypatch):
        """exchange_code가 authorize state와 동일 값을 token endpoint에 전달."""
        p = NaverProvider("NID", "NS", "http://localhost/cb")
        p.get_authorization_url("STATE_VALUE_123")  # _last_state에 저장

        captured: dict = {}

        async def fake_get(self, url, *args, **kwargs):
            captured["params"] = kwargs.get("params") or args
            return httpx.Response(200, json={"access_token": "AT"})

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        # state 인자 명시 전달
        await p.exchange_code("c", state="STATE_VALUE_123")
        assert captured["params"]["state"] == "STATE_VALUE_123"

    @pytest.mark.asyncio
    async def test_exchange_code_token_body_error(self, monkeypatch):
        """네이버 token 응답의 body.error 필드 존재 시 OAuthProviderInvalidResponse."""
        p = NaverProvider("NID", "NS", "http://localhost/cb")

        async def fake_get(self, url, *args, **kwargs):
            return httpx.Response(200, json={"error": "invalid_request", "error_description": "bad"})

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        with pytest.raises(OAuthProviderInvalidResponse):
            await p.exchange_code("c", state="S")

    @pytest.mark.asyncio
    async def test_exchange_code_5xx_retries(self, monkeypatch):
        """Naver token 5xx 재시도 3회 후 OAuthProviderUnavailable."""
        from tenacity import retry, retry_if_exception, stop_after_attempt, wait_none
        from api.src.integrations.auth_providers import naver as naver_mod

        p = NaverProvider("NID", "NS", "http://localhost/cb")
        calls = {"n": 0}

        async def fake_get(self, url, *args, **kwargs):
            calls["n"] += 1
            return httpx.Response(503, text="unavailable")

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        monkeypatch.setattr(
            naver_mod,
            "_retry",
            retry(
                retry=retry_if_exception(naver_mod._retryable_http_error),
                wait=wait_none(),
                stop=stop_after_attempt(3),
                reraise=True,
            ),
        )
        with pytest.raises(OAuthProviderUnavailable):
            await p.exchange_code("c", state="S")
        assert calls["n"] == 3

    @pytest.mark.asyncio
    async def test_exchange_code_4xx_does_not_retry(self, monkeypatch):
        """Naver token 4xx는 재시도 없이 OAuthProviderInvalidResponse."""
        p = NaverProvider("NID", "NS", "http://localhost/cb")
        calls = {"n": 0}

        async def fake_get(self, url, *args, **kwargs):
            calls["n"] += 1
            return httpx.Response(400, text="bad")

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        with pytest.raises(OAuthProviderInvalidResponse):
            await p.exchange_code("c", state="S")
        assert calls["n"] == 1

    def test_authorization_url_includes_extra_scopes(self):
        """추가 동의 항목(name·gender·birthday·birthyear·mobile) scope 노출."""
        p = NaverProvider("NID", "NS", "http://localhost/cb")
        url = p.get_authorization_url("st")
        for keyword in ("name", "mobile", "gender", "birthday", "birthyear"):
            assert keyword in url

    @pytest.mark.asyncio
    async def test_fetch_profile_full_extras(self, monkeypatch):
        """이름·성별(M→male)·생년월일까지 함께 받아오는 정상 케이스."""
        from datetime import date as _date

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
                        "name": "홍길동",
                        "gender": "M",
                        "birthyear": "1985",
                        "birthday": "07-22",
                    },
                },
            )

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        profile = await p.fetch_profile("AT")
        assert profile["name"] == "홍길동"
        assert profile["gender"] == "male"
        assert profile["birthdate"] == _date(1985, 7, 22)
        # 네이버는 주소 미제공 — 키 자체가 없거나 None
        assert profile.get("address_road") is None
        assert profile.get("postcode") is None

    @pytest.mark.asyncio
    async def test_fetch_profile_gender_female_and_unknown(self, monkeypatch):
        """gender 'F' → female. 그 외('U'/None)는 None."""
        p = NaverProvider("NID", "NS", "http://localhost/cb")

        async def fake_get_f(self, url, *args, **kwargs):
            return httpx.Response(
                200,
                json={
                    "resultcode": "00",
                    "response": {"id": "x", "email": "e@n.com", "gender": "F"},
                },
            )

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get_f)
        profile = await p.fetch_profile("AT")
        assert profile["gender"] == "female"

        async def fake_get_u(self, url, *args, **kwargs):
            return httpx.Response(
                200,
                json={
                    "resultcode": "00",
                    "response": {"id": "x", "email": "e@n.com", "gender": "U"},
                },
            )

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get_u)
        profile = await p.fetch_profile("AT")
        assert profile.get("gender") is None

    @pytest.mark.asyncio
    async def test_fetch_profile_partial_birthdate_yields_none(self, monkeypatch):
        """birthyear/birthday 중 하나만 있으면 birthdate=None."""
        p = NaverProvider("NID", "NS", "http://localhost/cb")

        async def fake_get(self, url, *args, **kwargs):
            return httpx.Response(
                200,
                json={
                    "resultcode": "00",
                    "response": {
                        "id": "x",
                        "email": "e@n.com",
                        "birthday": "01-01",  # birthyear 없음
                    },
                },
            )

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
        profile = await p.fetch_profile("AT")
        assert profile.get("birthdate") is None
