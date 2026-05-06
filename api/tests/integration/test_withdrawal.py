"""DELETE /api/v1/me 통합 테스트 — Story 1.7 (회원 탈퇴).

ASGI 스택으로 라우터를 호출하고, DB session·redis·verify_password 등 외부 의존성은
fakeredis와 dependency_overrides + monkeypatch로 격리한다.
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
from api.src.services import auth_service


def _make_email_user(
    user_id: int = 1,
    *,
    email: str = "user@example.com",
    phone: str = "01012345678",
    password_hash: str = "$argon2id$dummy",
    sub_status: str = "free",
) -> MagicMock:
    u = MagicMock(spec=User)
    u.id = user_id
    u.email = email
    u.phone = phone
    u.password_hash = password_hash
    u.subscription_status = sub_status
    u.withdrawn_at = None
    u.updated_at = datetime.now(tz=timezone.utc)
    return u


def _make_social_user(
    user_id: int = 2,
    *,
    email: str = "social@example.com",
    phone: str = "01098765432",
    sub_status: str = "free",
) -> MagicMock:
    u = MagicMock(spec=User)
    u.id = user_id
    u.email = email
    u.phone = phone
    u.password_hash = None
    u.subscription_status = sub_status
    u.withdrawn_at = None
    u.updated_at = datetime.now(tz=timezone.utc)
    return u


def _stub_session():
    """auth_service.withdraw 내부 db.execute / db.add / db.commit을 noop으로 받아주는 세션."""
    session = MagicMock()
    session.execute = AsyncMock(return_value=MagicMock())
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    async def gen():
        yield session

    return gen, session


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def fake_redis_token(monkeypatch):
    """`_TOKEN_KEY` 검증용 fakeredis context manager 패치."""
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
class TestWithdrawalEmailUser:
    async def test_withdraw_free_user_email_success(self, monkeypatch):
        """자체 가입자 비밀번호 일치 → 204 + 쿠키 소거 + auth_service.withdraw 호출."""
        user = _make_email_user(sub_status="free")
        gen, session = _stub_session()

        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = gen

        # verify_password를 True로 패치 (라우터 import 경로 기준)
        monkeypatch.setattr("api.src.routers.me.verify_password", lambda p, h: True)

        called = {}

        async def fake_withdraw(*, user, ip, ua, db, trace_id):
            called["user_id"] = user.id
            called["ip"] = ip

        monkeypatch.setattr(auth_service, "withdraw", fake_withdraw)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.request(
                "DELETE",
                "/api/v1/me",
                json={"password": "MyPassword!"},
            )

        assert res.status_code == 204
        assert called["user_id"] == 1
        # 쿠키 소거 헤더 검증 (Set-Cookie 두 줄)
        cookie_headers = res.headers.get_list("set-cookie")
        joined = "\n".join(cookie_headers)
        assert "denvia_session=" in joined
        assert "denvia_csrf=" in joined
        assert "Max-Age=0" in joined or "max-age=0" in joined.lower()

    async def test_withdraw_wrong_password(self, monkeypatch):
        """비밀번호 불일치 → 401 AUTH_INVALID_CREDENTIALS, withdraw 호출 안 됨."""
        user = _make_email_user()
        gen, _session = _stub_session()
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = gen

        monkeypatch.setattr("api.src.routers.me.verify_password", lambda p, h: False)

        called = {"n": 0}

        async def fake_withdraw(**kwargs):
            called["n"] += 1

        monkeypatch.setattr(auth_service, "withdraw", fake_withdraw)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.request(
                "DELETE",
                "/api/v1/me",
                json={"password": "wrong"},
            )

        assert res.status_code == 401
        assert res.json()["code"] == "AUTH_INVALID_CREDENTIALS"
        assert called["n"] == 0

    async def test_withdraw_missing_password_400(self, monkeypatch):
        """자체 가입자가 password 누락 → 400 AUTH_INVALID_CREDENTIALS."""
        user = _make_email_user()
        gen, _session = _stub_session()
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = gen

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.request("DELETE", "/api/v1/me", json={})

        assert res.status_code == 400
        assert res.json()["code"] == "AUTH_INVALID_CREDENTIALS"

    async def test_withdraw_pro_user_blocked(self, monkeypatch):
        """활성 Pro 사용자 → 409 SUBSCRIPTION_ACTIVE_MUST_CANCEL_FIRST.

        라우터의 비밀번호 검증은 통과하지만 service.withdraw가 즉시 409를 던진다.
        """
        from fastapi import HTTPException

        user = _make_email_user(sub_status="pro")
        gen, _session = _stub_session()
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = gen

        monkeypatch.setattr("api.src.routers.me.verify_password", lambda p, h: True)

        async def fake_withdraw(**kwargs):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "SUBSCRIPTION_ACTIVE_MUST_CANCEL_FIRST",
                    "message": "구독을 먼저 해지해주세요. 다음 결제일 이후 탈퇴가 가능합니다",
                },
            )

        monkeypatch.setattr(auth_service, "withdraw", fake_withdraw)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.request(
                "DELETE",
                "/api/v1/me",
                json={"password": "ok"},
            )

        assert res.status_code == 409
        assert res.json()["code"] == "SUBSCRIPTION_ACTIVE_MUST_CANCEL_FIRST"


@pytest.mark.asyncio
class TestWithdrawalSocialUser:
    async def test_withdraw_social_user_otp_token_success(
        self, fake_redis_token, monkeypatch
    ):
        """소셜 가입자 — phone_verification_token 검증 통과 → 204."""
        user = _make_social_user()
        gen, _session = _stub_session()
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = gen

        # 토큰을 fakeredis에 미리 저장 (검증 통과 → 1회용 소진)
        token = "good-token"
        await fake_redis_token.set(f"phone_token:{token}", user.phone, ex=600)

        called = {}

        async def fake_withdraw(*, user, ip, ua, db, trace_id):
            called["user_id"] = user.id

        monkeypatch.setattr(auth_service, "withdraw", fake_withdraw)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.request(
                "DELETE",
                "/api/v1/me",
                json={"phone_verification_token": token},
            )

        assert res.status_code == 204
        assert called["user_id"] == user.id
        # 토큰 1회용 소진 확인
        assert await fake_redis_token.get(f"phone_token:{token}") is None

    async def test_withdraw_social_user_missing_token_400(self, monkeypatch):
        """소셜 가입자가 phone_verification_token 누락 → 400 SMS_TOKEN_INVALID."""
        user = _make_social_user()
        gen, _session = _stub_session()
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = gen

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.request("DELETE", "/api/v1/me", json={})

        assert res.status_code == 400
        assert res.json()["code"] == "SMS_TOKEN_INVALID"

    async def test_withdraw_social_user_invalid_token_400(
        self, fake_redis_token, monkeypatch
    ):
        """소셜 가입자 — phone_verification_token이 redis에 없음 → 400 SMS_TOKEN_INVALID."""
        user = _make_social_user()
        gen, _session = _stub_session()
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = gen

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.request(
                "DELETE",
                "/api/v1/me",
                json={"phone_verification_token": "ghost"},
            )

        assert res.status_code == 400
        assert res.json()["code"] == "SMS_TOKEN_INVALID"
