"""OAuth 서비스 단위 테스트 — Story 1.6.

fakeredis + AsyncMock DB로 oauth_start/oauth_callback/oauth_complete_phone_supplement의
5가지 분기 + 에러 경로를 검증한다.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import fakeredis.aioredis as fakeredis
import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.services.auth_service import (
    _SIGNUP_PENDING_KEY,
    _OAUTH_STATE_KEY,
    _TOKEN_KEY,
    oauth_callback,
    oauth_complete_phone_supplement,
    oauth_start,
)


# ── Redis 페이크 픽스처 ──────────────────────────────────────────────────────


class _FakeCtx:
    def __init__(self, fake):
        self.fake = fake

    async def __aenter__(self):
        return self.fake

    async def __aexit__(self, *_):
        pass


@pytest.fixture
def fake_redis_pair(monkeypatch):
    """_make_redis(DB1) / _make_redis_rl(DB2) 모두 fakeredis로 교체."""
    server_otp = fakeredis.FakeServer()
    fake_otp = fakeredis.FakeRedis(server=server_otp, decode_responses=True)
    server_rl = fakeredis.FakeServer()
    fake_rl = fakeredis.FakeRedis(server=server_rl, decode_responses=True)

    monkeypatch.setattr(
        "api.src.services.auth_service._make_redis",
        lambda url: _FakeCtx(fake_otp),
    )
    monkeypatch.setattr(
        "api.src.services.auth_service._make_redis_rl",
        lambda url: _FakeCtx(fake_rl),
    )
    return fake_otp, fake_rl


# ── DB mock 헬퍼 ────────────────────────────────────────────────────────────


def _execute_returning(values: list):
    """db.execute가 호출될 때마다 values[i]를 순차 반환하는 mock."""
    call = {"i": 0}

    async def _exec(*args, **kwargs):
        i = call["i"]
        call["i"] += 1
        result_mock = MagicMock()
        val = values[i] if i < len(values) else None
        result_mock.scalar_one_or_none.return_value = val
        return result_mock

    return _exec


def _make_db(execute_values: list) -> AsyncMock:
    db = AsyncMock(spec=AsyncSession)
    db.execute = AsyncMock(side_effect=_execute_returning(execute_values))
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


def _user_mock(id=10, email="u@example.com", phone="01011112222", password_hash=None):
    u = MagicMock()
    u.id = id
    u.email = email
    u.phone = phone
    u.password_hash = password_hash
    u.withdrawn_at = None
    return u


# ── Fake Provider ────────────────────────────────────────────────────────────


class FakeProvider:
    def __init__(self, name="kakao", access_token="AT", profile=None):
        self.name = name
        self.access_token = access_token
        self._profile = profile or {
            "provider_sub": "sub-123",
            "email": "new@example.com",
            "phone": None,
        }

    def get_authorization_url(self, state: str) -> str:
        return f"https://fake/authz?state={state}"

    async def exchange_code(self, code: str) -> dict:
        return {"access_token": self.access_token}

    async def fetch_profile(self, access_token: str):
        return dict(self._profile)


# ── oauth_start ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_oauth_start_stores_state(fake_redis_pair):
    _, rl = fake_redis_pair
    provider = FakeProvider(name="kakao")
    url = await oauth_start("kakao", "login", provider, "redis://fake")

    assert url.startswith("https://fake/authz?state=")
    state = url.split("state=")[1]
    raw = await rl.get(_OAUTH_STATE_KEY.format(state=state))
    assert raw is not None
    payload = json.loads(raw)
    assert payload == {"provider": "kakao", "mode": "login"}


# ── oauth_callback 분기 ─────────────────────────────────────────────────────


async def _prime_state(rl, provider_name: str, state: str = "ST"):
    await rl.set(
        _OAUTH_STATE_KEY.format(state=state),
        json.dumps({"provider": provider_name, "mode": "signup"}),
        ex=600,
    )
    return state


@pytest.mark.asyncio
async def test_oauth_callback_login_completed_via_oauth_identity(fake_redis_pair):
    _, rl = fake_redis_pair
    state = await _prime_state(rl, "kakao")

    oi = MagicMock(user_id=42)
    matched_user = _user_mock(id=42)
    db = _make_db([oi, matched_user])

    provider = FakeProvider(name="kakao")
    result = await oauth_callback("kakao", "code", state, provider, "redis://fake", db)

    assert result["action"] == "login_completed"
    assert result["user_id"] == 42


@pytest.mark.asyncio
async def test_oauth_callback_email_collision_self_signup(fake_redis_pair):
    _, rl = fake_redis_pair
    state = await _prime_state(rl, "kakao")

    # 매칭된 oauth_identity 없음 + 같은 이메일의 자체 가입자 존재
    email_user = _user_mock(id=7, password_hash="argon2hash")
    db = _make_db([None, email_user])

    provider = FakeProvider(
        name="kakao",
        profile={"provider_sub": "new-sub", "email": "exists@e.com", "phone": None},
    )
    result = await oauth_callback("kakao", "c", state, provider, "redis://fake", db)
    assert result["action"] == "email_collision"


@pytest.mark.asyncio
async def test_oauth_callback_social_email_reuses_user(fake_redis_pair):
    """같은 이메일이 다른 소셜(e.g. google)로 이미 가입된 경우 → oauth_identity만 추가하고 로그인."""
    _, rl = fake_redis_pair
    state = await _prime_state(rl, "kakao")

    # 이메일 동일 + password_hash=None(소셜 전용)
    social_user = _user_mock(id=77, password_hash=None)
    db = _make_db([None, social_user])

    provider = FakeProvider(
        name="kakao",
        profile={"provider_sub": "new-sub", "email": "shared@e.com", "phone": None},
    )
    result = await oauth_callback("kakao", "c", state, provider, "redis://fake", db)
    assert result["action"] == "login_completed"
    assert result["user_id"] == 77
    # oauth_identity 레코드가 추가되어야 함
    db.add.assert_called()


@pytest.mark.asyncio
async def test_oauth_callback_phone_provided_new_signup(fake_redis_pair):
    _, rl = fake_redis_pair
    state = await _prime_state(rl, "naver")

    # oauth_identity 없음 + 이메일도 없음 + 휴대폰도 중복 없음
    db = _make_db([None, None, None])

    provider = FakeProvider(
        name="naver",
        profile={
            "provider_sub": "naver-xyz",
            "email": "new@e.com",
            "phone": "01099998888",
        },
    )
    result = await oauth_callback("naver", "c", state, provider, "redis://fake", db)
    assert result["action"] == "signup_completed_full"
    # users + oauth_identity 두 번 add
    assert db.add.call_count == 2


@pytest.mark.asyncio
async def test_oauth_callback_phone_collision(fake_redis_pair):
    _, rl = fake_redis_pair
    state = await _prime_state(rl, "naver")

    # 이메일 없음 + 휴대폰 중복
    phone_user = _user_mock(id=33)
    db = _make_db([None, None, phone_user])

    provider = FakeProvider(
        name="naver",
        profile={
            "provider_sub": "x",
            "email": "brand_new@e.com",
            "phone": "01033334444",
        },
    )
    result = await oauth_callback("naver", "c", state, provider, "redis://fake", db)
    assert result["action"] == "phone_collision"


@pytest.mark.asyncio
async def test_oauth_callback_signup_pending_phone(fake_redis_pair):
    otp, rl = fake_redis_pair
    state = await _prime_state(rl, "google")

    # 이메일 없음 + google은 phone=None
    db = _make_db([None, None])

    provider = FakeProvider(
        name="google",
        profile={"provider_sub": "google-sub", "email": "new@g.com", "phone": None},
    )
    result = await oauth_callback("google", "c", state, provider, "redis://fake", db)

    assert result["action"] == "signup_pending_phone"
    token = result["signup_pending_token"]
    raw = await otp.get(_SIGNUP_PENDING_KEY.format(token=token))
    assert raw is not None
    body = json.loads(raw)
    assert body == {
        "provider": "google",
        "provider_sub": "google-sub",
        "email": "new@g.com",
    }


@pytest.mark.asyncio
async def test_oauth_callback_state_reuse_blocked(fake_redis_pair):
    _, rl = fake_redis_pair
    state = await _prime_state(rl, "kakao")

    db = _make_db([None, None])
    provider = FakeProvider(
        name="kakao",
        profile={"provider_sub": "s", "email": "a@b.c", "phone": None},
    )
    # 첫 호출: 성공
    await oauth_callback("kakao", "c", state, provider, "redis://fake", db)
    # 두 번째 호출: state 소진되어 400
    db2 = _make_db([None, None])
    with pytest.raises(HTTPException) as exc:
        await oauth_callback("kakao", "c", state, provider, "redis://fake", db2)
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "OAUTH_STATE_INVALID"


@pytest.mark.asyncio
async def test_oauth_callback_state_provider_mismatch(fake_redis_pair):
    _, rl = fake_redis_pair
    await _prime_state(rl, "kakao", state="ST")

    db = _make_db([None, None])
    provider = FakeProvider(name="google")
    with pytest.raises(HTTPException) as exc:
        await oauth_callback("google", "c", "ST", provider, "redis://fake", db)
    assert exc.value.detail["code"] == "OAUTH_STATE_INVALID"


# ── oauth_complete_phone_supplement ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_oauth_complete_success(fake_redis_pair):
    otp, _ = fake_redis_pair
    # signup_pending 등록
    pending_token = "pt1"
    await otp.set(
        _SIGNUP_PENDING_KEY.format(token=pending_token),
        json.dumps(
            {"provider": "google", "provider_sub": "gsub", "email": "new@e.com"}
        ),
        ex=600,
    )
    # phone_verification_token 등록
    pvt = "pvt1"
    await otp.set(_TOKEN_KEY.format(token=pvt), "01011112222", ex=600)

    db = _make_db([None, None])  # 이메일 없음, 휴대폰 중복 없음

    user = await oauth_complete_phone_supplement(
        signup_pending_token=pending_token,
        phone="01011112222",
        phone_verification_token=pvt,
        redis_url="redis://fake",
        db=db,
    )
    assert db.add.call_count == 2
    # 토큰 소진 확인
    assert await otp.get(_SIGNUP_PENDING_KEY.format(token=pending_token)) is None
    assert await otp.get(_TOKEN_KEY.format(token=pvt)) is None


@pytest.mark.asyncio
async def test_oauth_complete_expired_pending(fake_redis_pair):
    db = _make_db([None, None])
    with pytest.raises(HTTPException) as exc:
        await oauth_complete_phone_supplement(
            signup_pending_token="missing",
            phone="01011112222",
            phone_verification_token="pvt",
            redis_url="redis://fake",
            db=db,
        )
    assert exc.value.detail["code"] == "OAUTH_PENDING_INVALID"


@pytest.mark.asyncio
async def test_oauth_complete_phone_mismatch(fake_redis_pair):
    otp, _ = fake_redis_pair
    await otp.set(
        _SIGNUP_PENDING_KEY.format(token="pt"),
        json.dumps({"provider": "google", "provider_sub": "s", "email": "e@x.com"}),
        ex=600,
    )
    await otp.set(_TOKEN_KEY.format(token="pvt"), "01011112222", ex=600)

    db = _make_db([])
    with pytest.raises(HTTPException) as exc:
        await oauth_complete_phone_supplement(
            signup_pending_token="pt",
            phone="01099998888",  # 불일치
            phone_verification_token="pvt",
            redis_url="redis://fake",
            db=db,
        )
    assert exc.value.detail["code"] == "SMS_TOKEN_INVALID"


@pytest.mark.asyncio
async def test_oauth_complete_phone_collision(fake_redis_pair):
    otp, _ = fake_redis_pair
    await otp.set(
        _SIGNUP_PENDING_KEY.format(token="pt"),
        json.dumps({"provider": "google", "provider_sub": "s", "email": "e@x.com"}),
        ex=600,
    )
    await otp.set(_TOKEN_KEY.format(token="pvt"), "01011112222", ex=600)

    # 이메일 없음, 휴대폰 중복 있음
    other_user = _user_mock(id=5)
    db = _make_db([None, other_user])

    with pytest.raises(HTTPException) as exc:
        await oauth_complete_phone_supplement(
            signup_pending_token="pt",
            phone="01011112222",
            phone_verification_token="pvt",
            redis_url="redis://fake",
            db=db,
        )
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "OAUTH_PHONE_COLLISION"


@pytest.mark.asyncio
async def test_oauth_complete_email_collision_self(fake_redis_pair):
    otp, _ = fake_redis_pair
    await otp.set(
        _SIGNUP_PENDING_KEY.format(token="pt"),
        json.dumps({"provider": "google", "provider_sub": "s", "email": "e@x.com"}),
        ex=600,
    )
    await otp.set(_TOKEN_KEY.format(token="pvt"), "01011112222", ex=600)

    # 이메일은 자체 가입자
    email_user = _user_mock(id=5, password_hash="arghash")
    db = _make_db([email_user])

    with pytest.raises(HTTPException) as exc:
        await oauth_complete_phone_supplement(
            signup_pending_token="pt",
            phone="01011112222",
            phone_verification_token="pvt",
            redis_url="redis://fake",
            db=db,
        )
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "OAUTH_EMAIL_COLLISION_WITH_EMAIL_SIGNUP"
