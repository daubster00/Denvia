"""GET /api/v1/me 통합 테스트.

주의: 실제 DB 연결이 필요한 테스트 (withdrawn_at 체크 등)는
docker compose exec api pytest 환경에서만 실행됩니다.
이 파일의 기본 테스트들은 httpx TestClient + JWT fixture로만 동작합니다.
"""

import time
import pytest
import jwt as pyjwt
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch, MagicMock

from api.src.main import app
from api.src.settings import settings


def _make_jwt(user_id: int = 1, role: str = "user", sub_status: str = "free", expired: bool = False) -> str:
    """테스트용 JWT 생성. PyJWT 표준: sub는 문자열."""
    payload = {
        "sub": str(user_id),  # JWT 표준: sub는 문자열
        "role": role,
        "sub_status": sub_status,
        "exp": int(time.time()) + (-10 if expired else 3600),
    }
    return pyjwt.encode(payload, settings.denvia_jwt_secret, algorithm=settings.denvia_jwt_algorithm)


@pytest.fixture
def mock_user():
    """DB에서 반환될 User mock 객체."""
    user = MagicMock()
    user.id = 1
    user.email = "doc@denvia.com"
    user.role = "user"
    user.subscription_status = "free"
    user.segment = None
    user.years_of_experience = None
    user.withdrawn_at = None
    user.must_reset_password = False
    # Story 1.7: is_social 분기용. 자체 가입자(이메일 비밀번호) 기본.
    user.password_hash = "$argon2id$dummy"
    return user


@pytest.fixture
def mock_social_user():
    """소셜 전용 사용자 — password_hash IS NULL."""
    user = MagicMock()
    user.id = 2
    user.email = "social@denvia.com"
    user.role = "user"
    user.subscription_status = "free"
    user.segment = None
    user.years_of_experience = None
    user.withdrawn_at = None
    user.must_reset_password = False
    user.password_hash = None
    return user


class TestMeEndpoint:
    async def test_쿠키_없음_401_AUTH_NOT_AUTHENTICATED(self):
        """denvia_session 쿠키 없음 → 401 + code: AUTH_NOT_AUTHENTICATED."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/me")
        assert res.status_code == 401
        body = res.json()
        assert body["code"] == "AUTH_NOT_AUTHENTICATED"
        assert "trace_id" in body

    async def test_유효_JWT_200_snake_case_8필드(self, mock_user):
        """유효한 JWT 쿠키 → 200 + snake_case 8필드(Story 1.7 is_social 추가) 반환."""
        token = _make_jwt(user_id=1)

        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=mock_user)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get("/api/v1/me", cookies={"denvia_session": token})

        assert res.status_code == 200
        body = res.json()
        assert set(body.keys()) == {
            "user_id", "email", "role", "subscription_status",
            "segment", "years_of_experience", "must_reset_password", "is_social",
        }
        assert body["user_id"] == 1
        assert body["email"] == "doc@denvia.com"
        # 자체 가입자: password_hash 존재 → is_social = False
        assert body["is_social"] is False

    async def test_유효_JWT_200_소셜_사용자_is_social_True(self, mock_social_user):
        """소셜 전용 사용자(password_hash IS NULL)는 is_social=True (Story 1.7 AC-11)."""
        token = _make_jwt(user_id=2)

        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=mock_social_user)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get("/api/v1/me", cookies={"denvia_session": token})

        assert res.status_code == 200
        assert res.json()["is_social"] is True

    async def test_만료_JWT_401_AUTH_SESSION_EXPIRED(self):
        """만료된 JWT → 401 + code: AUTH_SESSION_EXPIRED."""
        token = _make_jwt(expired=True)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/me", cookies={"denvia_session": token})
        assert res.status_code == 401
        assert res.json()["code"] == "AUTH_SESSION_EXPIRED"

    async def test_탈퇴_유저_토큰_401(self, mock_user):
        """withdrawn_at이 있는 유저 토큰 → 401."""
        mock_user.withdrawn_at = "2026-01-01T00:00:00Z"
        token = _make_jwt(user_id=1)

        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=mock_user)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get("/api/v1/me", cookies={"denvia_session": token})

        assert res.status_code == 401
        assert res.json()["code"] == "AUTH_NOT_AUTHENTICATED"
