"""POST /api/v1/me/withdraw/{send-otp,verify-otp} 통합 테스트 — Story 1.7 (AC-9).

`auth_service._make_redis`를 fakeredis로 패치해 OTP 발송·검증 플로우를 격리한다.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import fakeredis.aioredis as fakeredis
import pytest
from httpx import ASGITransport, AsyncClient

from api.src.deps.auth import get_current_user
from api.src.main import app
from api.src.models.base import get_session
from api.src.models.user import User


def _social_user(phone: str | None = "01012345678") -> MagicMock:
    u = MagicMock(spec=User)
    u.id = 7
    u.email = "social@example.com"
    u.phone = phone
    u.password_hash = None
    u.subscription_status = "free"
    u.withdrawn_at = None
    u.updated_at = datetime.now(tz=timezone.utc)
    u.current_session_id = None
    u.admin_grade = "master"
    return u


def _email_user() -> MagicMock:
    u = MagicMock(spec=User)
    u.id = 8
    u.email = "doc@example.com"
    u.phone = "01099998888"
    u.password_hash = "$argon2id$dummy"
    u.subscription_status = "free"
    u.withdrawn_at = None
    u.updated_at = datetime.now(tz=timezone.utc)
    u.current_session_id = None
    u.admin_grade = "master"
    return u


def _stub_session():
    session = MagicMock()
    session.execute = AsyncMock(return_value=MagicMock())
    session.add = MagicMock()
    session.commit = AsyncMock()

    async def gen():
        yield session

    return gen


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def fake_otp_redis(monkeypatch):
    server = fakeredis.FakeServer()
    fake = fakeredis.FakeRedis(server=server, decode_responses=True)

    class FakeRedisCtx:
        async def __aenter__(self):
            return fake

        async def __aexit__(self, *_):
            pass

    monkeypatch.setattr(
        "api.src.services.auth_service._make_redis",
        lambda url: FakeRedisCtx(),
    )
    return fake


@pytest.mark.asyncio
class TestWithdrawSendOtp:
    async def test_send_otp_social_user_success(self, fake_otp_redis):
        """소셜 사용자 → OTP 발송 + 마스킹된 휴대폰 반환."""
        app.dependency_overrides[get_current_user] = lambda: _social_user()
        app.dependency_overrides[get_session] = _stub_session()

        # 외부 Aligo 호출 차단 — 실제 SMS 발송은 mock 으로 대체.
        from unittest.mock import AsyncMock, MagicMock, patch

        fake_messaging = MagicMock()
        fake_messaging.send_sms_otp = AsyncMock(return_value=None)

        with patch(
            "api.src.routers.me._get_messaging", return_value=fake_messaging
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                res = await client.post("/api/v1/me/withdraw/send-otp")

        assert res.status_code == 200
        body = res.json()
        # 010-****-5678 형태
        assert body["masked_phone"].startswith("010-****-")
        assert body["masked_phone"].endswith("5678")
        # OTP가 redis에 저장됨
        otp = await fake_otp_redis.get("otp:withdraw:01012345678")
        assert otp is not None and len(otp) == 6

    async def test_send_otp_email_user_forbidden(self, fake_otp_redis):
        """자체 가입자 → 403 NOT_SOCIAL_ACCOUNT."""
        app.dependency_overrides[get_current_user] = lambda: _email_user()
        app.dependency_overrides[get_session] = _stub_session()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.post("/api/v1/me/withdraw/send-otp")

        assert res.status_code == 403
        assert res.json()["code"] == "NOT_SOCIAL_ACCOUNT"
        # OTP가 redis에 저장되지 않아야 함
        assert await fake_otp_redis.get("otp:withdraw:01099998888") is None

    async def test_send_otp_no_phone_422(self, fake_otp_redis):
        """phone=None인 소셜 사용자 → 422 PHONE_NOT_REGISTERED."""
        app.dependency_overrides[get_current_user] = lambda: _social_user(phone=None)
        app.dependency_overrides[get_session] = _stub_session()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.post("/api/v1/me/withdraw/send-otp")

        assert res.status_code == 422
        assert res.json()["code"] == "PHONE_NOT_REGISTERED"


@pytest.mark.asyncio
class TestWithdrawVerifyOtp:
    async def test_verify_otp_success(self, fake_otp_redis):
        """올바른 OTP → phone_verification_token 반환."""
        app.dependency_overrides[get_current_user] = lambda: _social_user()
        app.dependency_overrides[get_session] = _stub_session()

        # OTP를 미리 redis에 심음
        await fake_otp_redis.set("otp:withdraw:01012345678", "123456", ex=300)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.post(
                "/api/v1/me/withdraw/verify-otp",
                json={"code": "123456"},
            )

        assert res.status_code == 200
        token = res.json()["phone_verification_token"]
        assert isinstance(token, str) and len(token) > 10
        # phone_token이 redis에 저장됨
        assert await fake_otp_redis.get(f"phone_token:{token}") == "01012345678"

    async def test_verify_otp_wrong_code(self, fake_otp_redis):
        """OTP 불일치 → 400 SMS_CODE_INVALID."""
        app.dependency_overrides[get_current_user] = lambda: _social_user()
        app.dependency_overrides[get_session] = _stub_session()

        await fake_otp_redis.set("otp:withdraw:01012345678", "111111", ex=300)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.post(
                "/api/v1/me/withdraw/verify-otp",
                json={"code": "999999"},
            )

        assert res.status_code == 400
        assert res.json()["code"] == "SMS_CODE_INVALID"
