"""auth_service 단위 테스트 — fakeredis로 Redis 의존성 격리."""

import pytest
import fakeredis.aioredis as fakeredis

from api.src.integrations.messaging.adapters.stub import StubMessagingAdapter
from api.src.services.auth_service import (
    _OTP_KEY,
    _COOLDOWN_KEY,
    _RETRY_COUNT_KEY,
    _TOKEN_KEY,
    send_sms_otp_flow,
    verify_sms_otp_flow,
    _MAX_RETRIES,
    _MAX_WRONG,
)
from fastapi import HTTPException


# ── Fixtures ──────────────────────────────────────────��───────────────────────

class FakeRedisUrl:
    """fakeredis를 반환하는 context manager — _make_redis 패치용."""
    def __init__(self):
        self._store: dict[str, fakeredis.FakeRedis] = {}

    def get(self, url: str) -> fakeredis.FakeRedis:
        if url not in self._store:
            self._store[url] = fakeredis.FakeRedis(decode_responses=True)
        return self._store[url]


@pytest.fixture
def fake_redis(monkeypatch):
    """auth_service._make_redis를 fakeredis로 교체."""
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


@pytest.fixture
def messaging():
    return StubMessagingAdapter()


# ── send_sms_otp_flow ─────────────────────────────────────────────────────────

async def test_send_otp_returns_meta(fake_redis, messaging):
    result = await send_sms_otp_flow("01012345678", "signup", "redis://fake", messaging)
    assert result["cooldown_seconds"] == 60
    assert result["max_retries"] == 3
    assert "sent_at" in result


async def test_send_otp_stores_in_redis(fake_redis, messaging):
    await send_sms_otp_flow("01012345678", "signup", "redis://fake", messaging)
    otp = await fake_redis.get("otp:signup:01012345678")
    assert otp is not None
    assert len(otp) == 6
    assert otp.isdigit()


async def test_send_otp_cooldown_active(fake_redis, messaging):
    await fake_redis.set("otp_cooldown:signup:01012345678", "1", ex=60)
    with pytest.raises(HTTPException) as exc:
        await send_sms_otp_flow("01012345678", "signup", "redis://fake", messaging)
    assert exc.value.status_code == 429
    assert exc.value.detail["code"] == "SMS_COOLDOWN_ACTIVE"


async def test_send_otp_max_retries_exceeded(fake_redis, messaging):
    await fake_redis.set("otp_retry_count:signup:01012345678", str(_MAX_RETRIES), ex=3600)
    with pytest.raises(HTTPException) as exc:
        await send_sms_otp_flow("01012345678", "signup", "redis://fake", messaging)
    assert exc.value.status_code == 429
    assert exc.value.detail["code"] == "SMS_MAX_RETRIES_EXCEEDED"


# ── verify_sms_otp_flow ───────────────────────────────────────────────────────

async def test_verify_otp_success(fake_redis, messaging):
    await fake_redis.set("otp:signup:01012345678", "123456", ex=300)
    token = await verify_sms_otp_flow("01012345678", "123456", "signup", "redis://fake")
    assert isinstance(token, str)
    assert len(token) > 10
    # OTP 삭제됨
    assert await fake_redis.get("otp:signup:01012345678") is None
    # phone_verification_token 저장됨
    stored = await fake_redis.get(f"phone_token:{token}")
    assert stored == "01012345678"


async def test_verify_otp_wrong_code(fake_redis, messaging):
    await fake_redis.set("otp:signup:01012345678", "123456", ex=300)
    with pytest.raises(HTTPException) as exc:
        await verify_sms_otp_flow("01012345678", "000000", "signup", "redis://fake")
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "SMS_CODE_INVALID"


async def test_verify_otp_expired(fake_redis, messaging):
    with pytest.raises(HTTPException) as exc:
        await verify_sms_otp_flow("01012345678", "123456", "signup", "redis://fake")
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "SMS_SESSION_EXPIRED"


async def test_verify_otp_max_wrong_attempts(fake_redis, messaging):
    await fake_redis.set("otp:signup:01012345678", "123456", ex=300)
    # 2회 오답 선 주입
    await fake_redis.set("otp_wrong:signup:01012345678", str(_MAX_WRONG - 1), ex=300)
    with pytest.raises(HTTPException) as exc:
        await verify_sms_otp_flow("01012345678", "000000", "signup", "redis://fake")
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "SMS_MAX_WRONG_ATTEMPTS"
    # OTP 무효화됨
    assert await fake_redis.get("otp:signup:01012345678") is None
