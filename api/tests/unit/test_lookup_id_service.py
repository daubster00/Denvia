"""lookup_id 단위 테스트 — fakeredis + DB mock."""

import pytest
import fakeredis.aioredis as fakeredis
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.services.auth_service import lookup_id, _TOKEN_KEY
from api.src.utils.argon2 import hash_password


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def fake_redis_otp(monkeypatch):
    """auth_service._make_redis를 fakeredis로 교체 (OTP DB 1)."""
    server = fakeredis.FakeServer()
    fake = fakeredis.FakeRedis(server=server, decode_responses=True)

    class FakeCtx:
        async def __aenter__(self):
            return fake
        async def __aexit__(self, *_):
            pass

    monkeypatch.setattr(
        "api.src.services.auth_service._make_redis",
        lambda url: FakeCtx(),
    )
    return fake


@pytest.fixture
def fake_redis_rl(monkeypatch):
    """auth_service._make_redis_rl을 fakeredis로 교체 (Rate Limit DB 2)."""
    server = fakeredis.FakeServer()
    fake = fakeredis.FakeRedis(server=server, decode_responses=True)

    class FakeCtx:
        async def __aenter__(self):
            return fake
        async def __aexit__(self, *_):
            pass

    monkeypatch.setattr(
        "api.src.services.auth_service._make_redis_rl",
        lambda url: FakeCtx(),
    )
    return fake


def _make_user(phone: str, password_hash: str | None = "somehash") -> MagicMock:
    user = MagicMock()
    user.id = 1
    user.email = "doc@denvia.com"
    user.phone = phone
    user.password_hash = password_hash
    user.withdrawn_at = None
    user.current_session_id = None
    user.admin_grade = "master"
    return user


def _mock_db_with_user(user) -> AsyncMock:
    db = AsyncMock(spec=AsyncSession)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = user
    db.execute = AsyncMock(return_value=result_mock)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.rollback = AsyncMock()
    return db


def _mock_db_no_user() -> AsyncMock:
    db = AsyncMock(spec=AsyncSession)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result_mock)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.rollback = AsyncMock()
    return db


# ── 유효 토큰 + 매칭 — 이메일 가입 ──────────────────────────────────────────

async def test_유효_토큰_매칭_이메일가입자(fake_redis_otp, fake_redis_rl):
    token = "valid_token_abc"
    token_key = _TOKEN_KEY.format(token=token)
    await fake_redis_otp.set(token_key, "01012345678", ex=600)

    user = _make_user("01012345678", password_hash=hash_password("pw12345"))
    db = _mock_db_with_user(user)

    result = await lookup_id(
        phone_verification_token=token,
        ip="1.2.3.4",
        ua="ua",
        redis_url="redis://fake",
        db=db,
    )

    assert result["email_masked"] == "d****@denvia.com"
    assert result["signup_method"] == "email"
    # 토큰 소진 확인
    assert await fake_redis_otp.get(token_key) is None


# ── 유효 토큰 + 매칭 — 소셜 가입 ────────────────────────────────────────────

async def test_유효_토큰_매칭_소셜가입자(fake_redis_otp, fake_redis_rl):
    token = "social_token"
    await fake_redis_otp.set(_TOKEN_KEY.format(token=token), "01099998888", ex=600)

    user = _make_user("01099998888", password_hash=None)
    db = _mock_db_with_user(user)

    result = await lookup_id(
        phone_verification_token=token,
        ip=None,
        ua=None,
        redis_url="redis://fake",
        db=db,
    )

    assert result["signup_method"] == "social"
    assert result["email_masked"] is not None


# ── 유효 토큰 + 불일치 ────────────────────────────────────────────────────────

async def test_유효_토큰_불일치(fake_redis_otp, fake_redis_rl):
    token = "no_match_token"
    await fake_redis_otp.set(_TOKEN_KEY.format(token=token), "01000000000", ex=600)

    db = _mock_db_no_user()

    result = await lookup_id(
        phone_verification_token=token,
        ip=None,
        ua=None,
        redis_url="redis://fake",
        db=db,
    )

    assert result["email_masked"] is None
    assert result["signup_method"] is None


# ── 토큰 재사용 방지 ─────────────────────────────────────────────────────────

async def test_토큰_재사용_400(fake_redis_otp, fake_redis_rl):
    token = "reuse_token"
    await fake_redis_otp.set(_TOKEN_KEY.format(token=token), "01012345678", ex=600)

    user = _make_user("01012345678")
    db = _mock_db_with_user(user)

    # 첫 번째 호출 성공
    await lookup_id(token, None, None, "redis://fake", db)

    # 두 번째 호출 → 토큰 없음 → 400
    with pytest.raises(HTTPException) as exc:
        await lookup_id(token, None, None, "redis://fake", db)

    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "SMS_TOKEN_INVALID"


# ── 만료된 토큰 ──────────────────────────────────────────────────────────────

async def test_만료_토큰_400(fake_redis_otp, fake_redis_rl):
    db = _mock_db_no_user()

    with pytest.raises(HTTPException) as exc:
        await lookup_id(
            phone_verification_token="expired_token",
            ip=None,
            ua=None,
            redis_url="redis://fake",
            db=db,
        )

    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "SMS_TOKEN_INVALID"


# ── Story 1.6: oauth_identity provider별 세분화 ─────────────────────────────

def _mock_db_social_with_provider(user, provider: str) -> AsyncMock:
    """첫 execute는 user, 두 번째 execute는 provider 문자열을 반환."""
    db = AsyncMock(spec=AsyncSession)

    first_result = MagicMock()
    first_result.scalar_one_or_none.return_value = user

    second_result = MagicMock()
    second_result.scalar_one_or_none.return_value = provider

    db.execute = AsyncMock(side_effect=[first_result, second_result])
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


@pytest.mark.parametrize("provider", ["kakao", "google", "naver"])
async def test_signup_method_provider별_분기(fake_redis_otp, fake_redis_rl, provider):
    token = f"tok_{provider}"
    await fake_redis_otp.set(_TOKEN_KEY.format(token=token), "01077778888", ex=600)

    user = _make_user("01077778888", password_hash=None)
    db = _mock_db_social_with_provider(user, provider)

    result = await lookup_id(
        phone_verification_token=token,
        ip=None,
        ua=None,
        redis_url="redis://fake",
        db=db,
    )
    assert result["signup_method"] == provider
