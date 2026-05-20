"""마이페이지 회원정보 엔드포인트 통합 테스트.

GET/PATCH /api/v1/me/profile, POST /api/v1/me/password/change, 및 기존
POST /api/v1/me/password 가드 회귀를 커버한다.

httpx ASGITransport + JWT 픽스처 + 의존성 patch 방식 — 실제 DB/Redis 없이 동작.
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest
from httpx import ASGITransport, AsyncClient

from api.src.main import app
from api.src.settings import settings


def _make_jwt(user_id: int = 1, role: str = "user", sub_status: str = "free") -> str:
    payload = {
        "sub": str(user_id),
        "role": role,
        "sub_status": sub_status,
        "exp": int(time.time()) + 3600,
    }
    return pyjwt.encode(
        payload,
        settings.denvia_jwt_secret,
        algorithm=settings.denvia_jwt_algorithm,
    )


def _make_user(
    user_id: int = 1,
    email: str = "doc@denvia.com",
    *,
    is_social: bool = False,
    must_reset: bool = False,
    phone: str | None = "01012345678",
    name: str | None = "홍길동",
    postcode: str | None = "12345",
    address_road: str | None = "서울시 강남구 테헤란로 1",
    address_detail: str | None = "501호",
    gender: str | None = None,
    birthdate=None,
    marketing_consent_at=None,
    marketing_withdrawn_at=None,
    segment: str | None = None,
    years_of_experience: int | None = None,
) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.email = email
    user.role = "user"
    user.subscription_status = "free"
    user.segment = segment
    user.years_of_experience = years_of_experience
    user.withdrawn_at = None
    user.must_reset_password = must_reset
    user.password_hash = None if is_social else "$argon2id$dummy"
    user.phone = phone
    user.phone_verified = phone is not None
    user.name = name
    user.postcode = postcode
    user.address_road = address_road
    user.address_detail = address_detail
    user.gender = gender
    user.birthdate = birthdate
    user.marketing_consent_at = marketing_consent_at
    user.marketing_withdrawn_at = marketing_withdrawn_at
    return user


# ── GET /me/profile ─────────────────────────────────────────────────────────


class TestGetMeProfile:
    async def test_쿠키_없음_401(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/me/profile")
        assert res.status_code == 401

    async def test_유효_JWT_8필드_반환(self):
        user = _make_user()
        token = _make_jwt(user_id=user.id)
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get(
                    "/api/v1/me/profile",
                    cookies={"denvia_session": token},
                )
        assert res.status_code == 200
        body = res.json()
        assert set(body.keys()) == {
            "email",
            "name",
            "phone",
            "phone_verified",
            "is_social",
            "postcode",
            "address_road",
            "address_detail",
            "gender",
            "birthdate",
            "marketing_consent",
            "marketing_consent_at",
            "segment",
            "years_of_experience",
        }
        assert body["email"] == "doc@denvia.com"
        assert body["name"] == "홍길동"
        assert body["phone"] == "01012345678"
        assert body["is_social"] is False
        assert body["postcode"] == "12345"
        # 신규 필드 기본값 — 미입력 시 모두 NULL/false
        assert body["gender"] is None
        assert body["birthdate"] is None
        assert body["marketing_consent"] is False
        assert body["marketing_consent_at"] is None
        assert body["segment"] is None
        assert body["years_of_experience"] is None

    async def test_소셜_사용자_is_social_True(self):
        user = _make_user(is_social=True)
        token = _make_jwt(user_id=user.id)
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get(
                    "/api/v1/me/profile",
                    cookies={"denvia_session": token},
                )
        assert res.status_code == 200
        assert res.json()["is_social"] is True


# ── PATCH /me/profile ───────────────────────────────────────────────────────


class TestPatchMeProfile:
    async def test_이름_주소만_변경_204(self):
        user = _make_user()
        token = _make_jwt(user_id=user.id)
        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)),
            patch("api.src.routers.me.get_session"),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.patch(
                    "/api/v1/me/profile",
                    cookies={"denvia_session": token},
                    json={
                        "name": "김신규",
                        "postcode": "06241",
                        "address_road": "서울시 강남구 강남대로 123",
                        "address_detail": "5층",
                    },
                )
        assert res.status_code == 204
        assert user.name == "김신규"
        assert user.postcode == "06241"
        assert user.address_road == "서울시 강남구 강남대로 123"
        assert user.address_detail == "5층"

    async def test_빈문자열_None으로_정규화(self):
        user = _make_user(name="기존이름")
        token = _make_jwt(user_id=user.id)
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.patch(
                    "/api/v1/me/profile",
                    cookies={"denvia_session": token},
                    json={"name": "   "},
                )
        assert res.status_code == 204
        assert user.name is None

    async def test_새_전화번호_토큰없음_400_SMS_TOKEN_INVALID(self):
        user = _make_user(phone="01011112222")
        token = _make_jwt(user_id=user.id)
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.patch(
                    "/api/v1/me/profile",
                    cookies={"denvia_session": token},
                    json={"phone": "01099998888"},
                )
        assert res.status_code == 400
        assert res.json()["code"] == "SMS_TOKEN_INVALID"

    async def test_새_전화번호_유효_토큰_204_phone_verified_True(self):
        user = _make_user(phone="01011112222")
        user.phone_verified = False
        token = _make_jwt(user_id=user.id)

        # collision 없음 → None 반환
        scalar_mock = MagicMock()
        scalar_mock.scalar_one_or_none.return_value = None
        exec_mock = AsyncMock(return_value=scalar_mock)

        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)),
            patch(
                "api.src.routers.me.verify_phone_change_token",
                new=AsyncMock(return_value=None),
            ),
            patch("sqlalchemy.ext.asyncio.AsyncSession.execute", new=exec_mock),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.patch(
                    "/api/v1/me/profile",
                    cookies={"denvia_session": token},
                    json={
                        "phone": "01099998888",
                        "phone_verification_token": "valid-token",
                    },
                )
        assert res.status_code == 204
        assert user.phone == "01099998888"
        assert user.phone_verified is True

    async def test_새_전화번호_다른계정과_충돌_409(self):
        user = _make_user(phone="01011112222")
        token = _make_jwt(user_id=user.id)

        other_user = MagicMock()
        other_user.id = 999
        scalar_mock = MagicMock()
        scalar_mock.scalar_one_or_none.return_value = other_user
        exec_mock = AsyncMock(return_value=scalar_mock)

        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)),
            patch("sqlalchemy.ext.asyncio.AsyncSession.execute", new=exec_mock),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.patch(
                    "/api/v1/me/profile",
                    cookies={"denvia_session": token},
                    json={
                        "phone": "01099998888",
                        "phone_verification_token": "valid-token",
                    },
                )
        assert res.status_code == 409
        assert res.json()["code"] == "ACCOUNT_PHONE_DUPLICATE"

    async def test_같은_phone_재전송_토큰없이_OK(self):
        """phone이 현재 값과 동일하면 토큰 없이도 통과(변경 없음)."""
        user = _make_user(phone="01011112222")
        token = _make_jwt(user_id=user.id)
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.patch(
                    "/api/v1/me/profile",
                    cookies={"denvia_session": token},
                    json={"phone": "01011112222"},
                )
        assert res.status_code == 204

    async def test_성별_생년월일_저장_204(self):
        from datetime import date

        user = _make_user()
        token = _make_jwt(user_id=user.id)
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.patch(
                    "/api/v1/me/profile",
                    cookies={"denvia_session": token},
                    json={"gender": "female", "birthdate": "1990-05-15"},
                )
        assert res.status_code == 204
        assert user.gender == "female"
        assert user.birthdate == date(1990, 5, 15)

    async def test_잘못된_성별값_422(self):
        user = _make_user()
        token = _make_jwt(user_id=user.id)
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.patch(
                    "/api/v1/me/profile",
                    cookies={"denvia_session": token},
                    json={"gender": "other"},
                )
        assert res.status_code == 422

    async def test_미래_생년월일_422(self):
        user = _make_user()
        token = _make_jwt(user_id=user.id)
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.patch(
                    "/api/v1/me/profile",
                    cookies={"denvia_session": token},
                    json={"birthdate": "2999-01-01"},
                )
        assert res.status_code == 422

    async def test_마케팅_동의_토글_True_consent_at_기록(self):
        user = _make_user()
        assert user.marketing_consent_at is None
        token = _make_jwt(user_id=user.id)
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.patch(
                    "/api/v1/me/profile",
                    cookies={"denvia_session": token},
                    json={"marketing_consent": True},
                )
        assert res.status_code == 204
        assert user.marketing_consent_at is not None
        assert user.marketing_withdrawn_at is None

    async def test_마케팅_동의_철회_consent_at_None_withdrawn_at_기록(self):
        from datetime import datetime, timezone

        user = _make_user(
            marketing_consent_at=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        token = _make_jwt(user_id=user.id)
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.patch(
                    "/api/v1/me/profile",
                    cookies={"denvia_session": token},
                    json={"marketing_consent": False},
                )
        assert res.status_code == 204
        assert user.marketing_consent_at is None
        assert user.marketing_withdrawn_at is not None

    async def test_segment_PATCH_무시(self):
        """ProfileUpdateRequest는 segment를 받지 않으므로 PATCH로 변경되지 않는다."""
        user = _make_user(segment=None)
        token = _make_jwt(user_id=user.id)
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.patch(
                    "/api/v1/me/profile",
                    cookies={"denvia_session": token},
                    # segment 키는 스키마에 없으므로 Pydantic이 조용히 무시한다(extra="ignore" 기본).
                    json={"segment": "doctor", "years_of_experience": 10},
                )
        assert res.status_code == 204
        assert user.segment is None
        assert user.years_of_experience is None

    async def test_잘못된_우편번호_422(self):
        user = _make_user()
        token = _make_jwt(user_id=user.id)
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.patch(
                    "/api/v1/me/profile",
                    cookies={"denvia_session": token},
                    json={"postcode": "abcde"},
                )
        assert res.status_code == 422


# ── POST /me/password/change ────────────────────────────────────────────────


class TestChangePasswordWithCurrent:
    async def test_소셜_사용자_403_NO_PASSWORD_SET(self):
        user = _make_user(is_social=True)
        token = _make_jwt(user_id=user.id)
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post(
                    "/api/v1/me/password/change",
                    cookies={"denvia_session": token},
                    json={"current_password": "anything", "new_password": "newpw1234"},
                )
        assert res.status_code == 403
        assert res.json()["code"] == "NO_PASSWORD_SET"

    async def test_잘못된_현재_PW_401(self):
        user = _make_user()
        token = _make_jwt(user_id=user.id)

        redis_mock = AsyncMock()
        redis_mock.exists = AsyncMock(return_value=False)
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.set = AsyncMock(return_value=True)
        redis_mock.__aenter__ = AsyncMock(return_value=redis_mock)
        redis_mock.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)),
            patch("api.src.routers.me._make_pw_rl_redis", return_value=redis_mock),
            patch("api.src.routers.me.verify_password", return_value=False),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post(
                    "/api/v1/me/password/change",
                    cookies={"denvia_session": token},
                    json={"current_password": "wrong", "new_password": "newpw1234"},
                )
        assert res.status_code == 401
        assert res.json()["code"] == "AUTH_INVALID_CREDENTIALS"

    async def test_락아웃_중_429(self):
        user = _make_user()
        token = _make_jwt(user_id=user.id)

        redis_mock = AsyncMock()
        redis_mock.exists = AsyncMock(return_value=True)  # 락아웃 키 존재
        redis_mock.__aenter__ = AsyncMock(return_value=redis_mock)
        redis_mock.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)),
            patch("api.src.routers.me._make_pw_rl_redis", return_value=redis_mock),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post(
                    "/api/v1/me/password/change",
                    cookies={"denvia_session": token},
                    json={"current_password": "any", "new_password": "newpw1234"},
                )
        assert res.status_code == 429
        assert res.json()["code"] == "AUTH_TEMPORARILY_LOCKED"

    async def test_새_PW_8자_미만_422(self):
        user = _make_user()
        token = _make_jwt(user_id=user.id)
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post(
                    "/api/v1/me/password/change",
                    cookies={"denvia_session": token},
                    json={"current_password": "anything", "new_password": "short"},
                )
        assert res.status_code == 422


# ── 기존 POST /me/password 회귀 — 가드가 평범한 이메일 회원을 차단해야 함 ──


class TestChangePasswordGuard:
    async def test_평범한_이메일회원_must_reset_False_403(self):
        """이메일 가입자(password 있음 + must_reset_password=False)는 차단."""
        user = _make_user(must_reset=False)
        token = _make_jwt(user_id=user.id)
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post(
                    "/api/v1/me/password",
                    cookies={"denvia_session": token},
                    json={"new_password": "newpw1234"},
                )
        assert res.status_code == 403
        assert res.json()["code"] == "PASSWORD_ALREADY_SET"

    async def test_소셜회원_허용_200(self):
        """소셜 가입자(password_hash IS NULL)는 최초 비밀번호 설정 허용."""
        user = _make_user(is_social=True)
        token = _make_jwt(user_id=user.id)
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post(
                    "/api/v1/me/password",
                    cookies={"denvia_session": token},
                    json={"new_password": "newpw1234"},
                )
        assert res.status_code == 200
        assert res.json()["ok"] is True

    async def test_임시PW_must_reset_True_허용_200(self):
        """임시 비밀번호 발급 직후(must_reset_password=True) 사용자는 통과."""
        user = _make_user(must_reset=True)
        token = _make_jwt(user_id=user.id)
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post(
                    "/api/v1/me/password",
                    cookies={"denvia_session": token},
                    json={"new_password": "newpw1234"},
                )
        assert res.status_code == 200
