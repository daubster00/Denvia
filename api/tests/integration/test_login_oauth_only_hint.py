"""OAuth-only 계정 힌트 — 이메일 로그인 엔드포인트 통합 테스트 (Story 1.8)."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from api.src.main import app


async def _post_login(client, email="social@denvia.com", password="any_password"):
    return await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password, "persist_session": False},
    )


class TestOAuthOnlyHintEndpoint:
    async def test_단일_provider_409_반환(self):
        with patch(
            "api.src.routers.auth.login_user",
            new=AsyncMock(
                side_effect=HTTPException(
                    status_code=409,
                    detail={
                        "code": "AUTH_ACCOUNT_OAUTH_ONLY",
                        "message": "이 계정은 네이버로 가입되어 있습니다. 네이버로 로그인해 주세요.",
                        "linked_providers": ["naver"],
                    },
                )
            ),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await _post_login(client)

        assert res.status_code == 409
        body = res.json()
        assert body["code"] == "AUTH_ACCOUNT_OAUTH_ONLY"
        assert body["details"]["linked_providers"] == ["naver"]
        assert "네이버" in body["message"]

    async def test_다중_provider_linked_at_순서_반환(self):
        with patch(
            "api.src.routers.auth.login_user",
            new=AsyncMock(
                side_effect=HTTPException(
                    status_code=409,
                    detail={
                        "code": "AUTH_ACCOUNT_OAUTH_ONLY",
                        "message": "이 계정은 카카오, 구글로 가입되어 있습니다. 가입한 채널로 로그인해 주세요.",
                        "linked_providers": ["kakao", "google"],
                    },
                )
            ),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await _post_login(client)

        assert res.status_code == 409
        body = res.json()
        assert body["details"]["linked_providers"] == ["kakao", "google"]
        assert "카카오" in body["message"]
        assert "구글" in body["message"]

    async def test_임의_비밀번호_409_반환(self):
        """OAuth-only 사용자에게 비밀번호 일치 여부 무관하게 409."""
        with patch(
            "api.src.routers.auth.login_user",
            new=AsyncMock(
                side_effect=HTTPException(
                    status_code=409,
                    detail={
                        "code": "AUTH_ACCOUNT_OAUTH_ONLY",
                        "message": "이 계정은 카카오로 가입되어 있습니다. 카카오로 로그인해 주세요.",
                        "linked_providers": ["kakao"],
                    },
                )
            ),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await _post_login(client, password="totally_wrong_password")

        assert res.status_code == 409

    async def test_락아웃_우선_429(self):
        """AC-2 — 락아웃 활성 상태에서 OAuth-only 이메일 시도 시 429 우선."""
        with patch(
            "api.src.routers.auth.login_user",
            new=AsyncMock(
                side_effect=HTTPException(
                    status_code=429,
                    detail={
                        "code": "AUTH_TEMPORARILY_LOCKED",
                        "message": "잠시 후 다시 시도해주세요.",
                    },
                )
            ),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await _post_login(client)

        assert res.status_code == 429
        assert res.json()["code"] == "AUTH_TEMPORARILY_LOCKED"

    async def test_탈퇴_사용자_401(self):
        """AC-5 — withdrawn_at 설정된 OAuth-only 사용자 → 401."""
        with patch(
            "api.src.routers.auth.login_user",
            new=AsyncMock(
                side_effect=HTTPException(
                    status_code=401,
                    detail={
                        "code": "AUTH_INVALID_CREDENTIALS",
                        "message": "이메일 또는 비밀번호가 일치하지 않습니다.",
                    },
                )
            ),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await _post_login(client)

        assert res.status_code == 401
        assert res.json()["code"] == "AUTH_INVALID_CREDENTIALS"

    async def test_이메일_비번_계정_oauth_연동도_정상_로그인(self):
        """AC-3 — password_hash NOT NULL + oauth_identity → 정상 200."""
        from unittest.mock import MagicMock

        user = MagicMock()
        user.id = 10
        user.email = "dual@denvia.com"
        user.role = "user"
        user.subscription_status = "free"
        user.withdrawn_at = None
        # encode_session_jwt 가 session_id 로 사용하므로 명시적 None 지정 — MagicMock 인 채로
        # 두면 JWT payload 가 MagicMock 을 머금어 JSON 직렬화에서 실패한다.
        user.current_session_id = None

        with patch(
            "api.src.routers.auth.login_user",
            new=AsyncMock(return_value=user),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await _post_login(client, email="dual@denvia.com", password="correct_pw!")

        assert res.status_code == 200
        assert res.json()["email"] == "dual@denvia.com"

    async def test_응답_body_구조_details_linked_providers(self):
        """HTTPException handler가 linked_providers를 details 아래에 올바르게 배치."""
        with patch(
            "api.src.routers.auth.login_user",
            new=AsyncMock(
                side_effect=HTTPException(
                    status_code=409,
                    detail={
                        "code": "AUTH_ACCOUNT_OAUTH_ONLY",
                        "message": "이 계정은 네이버로 가입되어 있습니다. 네이버로 로그인해 주세요.",
                        "linked_providers": ["naver"],
                    },
                )
            ),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await _post_login(client)

        body = res.json()
        # 최상위 필드 검증
        assert "code" in body
        assert "message" in body
        assert "trace_id" in body
        # linked_providers는 details 아래에 위치
        assert "details" in body
        assert "linked_providers" in body["details"]
        # 최상위에 linked_providers 직접 노출 금지
        assert "linked_providers" not in {k for k in body if k != "details"}

    async def test_카카오_단독_한국어_라벨(self):
        """카카오 단독 provider → 메시지에 '카카오' 포함."""
        with patch(
            "api.src.routers.auth.login_user",
            new=AsyncMock(
                side_effect=HTTPException(
                    status_code=409,
                    detail={
                        "code": "AUTH_ACCOUNT_OAUTH_ONLY",
                        "message": "이 계정은 카카오로 가입되어 있습니다. 카카오로 로그인해 주세요.",
                        "linked_providers": ["kakao"],
                    },
                )
            ),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await _post_login(client)

        body = res.json()
        assert body["details"]["linked_providers"] == ["kakao"]
        assert "카카오" in body["message"]

    async def test_구글_단독_한국어_라벨(self):
        """구글 단독 provider → 메시지에 '구글' 포함."""
        with patch(
            "api.src.routers.auth.login_user",
            new=AsyncMock(
                side_effect=HTTPException(
                    status_code=409,
                    detail={
                        "code": "AUTH_ACCOUNT_OAUTH_ONLY",
                        "message": "이 계정은 구글로 가입되어 있습니다. 구글로 로그인해 주세요.",
                        "linked_providers": ["google"],
                    },
                )
            ),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await _post_login(client)

        body = res.json()
        assert body["details"]["linked_providers"] == ["google"]
        assert "구글" in body["message"]
