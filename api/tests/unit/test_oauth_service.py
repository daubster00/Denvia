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
    """db.execute가 호출될 때마다 values[i]를 순차 반환하는 mock.

    값이 tuple이면 JOIN row로 해석 → `.first()`로 tuple 반환, `.scalar_one_or_none()`은 None.
    값이 tuple이 아니면 단일 객체 → `.scalar_one_or_none()` + `.first()` 모두 동일값 반환.
    """
    call = {"i": 0}

    async def _exec(*args, **kwargs):
        i = call["i"]
        call["i"] += 1
        result_mock = MagicMock()
        val = values[i] if i < len(values) else None
        if isinstance(val, tuple):
            result_mock.first.return_value = val
            result_mock.scalar_one_or_none.return_value = None
        else:
            result_mock.first.return_value = val
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

    async def exchange_code(self, code: str, state: str = "") -> dict:
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
    assert payload["provider"] == "kakao"
    assert payload["mode"] == "login"


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
    # 새 구현은 oauth_identity JOIN users 단일 쿼리로 반환 → (oi, user) tuple
    db = _make_db([(oi, matched_user)])

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
    assert body["provider"] == "google"
    assert body["provider_sub"] == "google-sub"
    assert body["email"] == "new@g.com"


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


# ── state 저장 계약 (AC-2) ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_oauth_start_ttl_600s(fake_redis_pair):
    """AC-2: state는 Redis DB 2에 TTL=600초로 저장되어야 한다."""
    _, rl = fake_redis_pair
    provider = FakeProvider(name="kakao")
    url = await oauth_start("kakao", "login", provider, "redis://fake")
    state = url.split("state=")[1]
    ttl = await rl.ttl(_OAUTH_STATE_KEY.format(state=state))
    # fakeredis ttl returns remaining seconds (should be ~600)
    assert 590 <= ttl <= 600


@pytest.mark.asyncio
async def test_oauth_start_stores_in_rl_db_not_otp_db(fake_redis_pair):
    """state는 DB 2(rate limit)에만 저장. DB 1(OTP)에는 저장되지 않음."""
    otp, rl = fake_redis_pair
    provider = FakeProvider(name="kakao")
    url = await oauth_start("kakao", "login", provider, "redis://fake")
    state = url.split("state=")[1]
    key = _OAUTH_STATE_KEY.format(state=state)
    assert await rl.get(key) is not None
    assert await otp.get(key) is None


@pytest.mark.asyncio
async def test_oauth_start_persists_next_path(fake_redis_pair):
    """oauth_start가 next_path를 state payload에 저장해 AC-3 리다이렉트 연결."""
    _, rl = fake_redis_pair
    provider = FakeProvider(name="kakao")
    url = await oauth_start(
        "kakao", "login", provider, "redis://fake", next_path="/dashboard"
    )
    state = url.split("state=")[1]
    payload = json.loads(await rl.get(_OAUTH_STATE_KEY.format(state=state)))
    assert payload.get("next") == "/dashboard"


@pytest.mark.asyncio
async def test_oauth_start_redis_error_raises_503(monkeypatch):
    """Redis 연결 실패 시 HTTPException 503 OAUTH_PROVIDER_UNAVAILABLE."""
    from redis.exceptions import RedisError

    class _FailCtx:
        async def __aenter__(self):
            raise RedisError("conn refused")

        async def __aexit__(self, *_):
            pass

    monkeypatch.setattr(
        "api.src.services.auth_service._make_redis_rl",
        lambda url: _FailCtx(),
    )
    provider = FakeProvider(name="kakao")
    with pytest.raises(HTTPException) as exc:
        await oauth_start("kakao", "login", provider, "redis://fake")
    assert exc.value.status_code == 503
    assert exc.value.detail["code"] == "OAUTH_PROVIDER_UNAVAILABLE"


# ── _consume_oauth_state 에러 경로 ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_callback_state_json_parse_error(fake_redis_pair):
    """state 값이 JSON이 아니면 OAUTH_STATE_INVALID 400."""
    _, rl = fake_redis_pair
    await rl.set(_OAUTH_STATE_KEY.format(state="ST"), "not-json", ex=600)
    provider = FakeProvider(name="kakao")
    db = _make_db([])
    with pytest.raises(HTTPException) as exc:
        await oauth_callback("kakao", "c", "ST", provider, "redis://fake", db)
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "OAUTH_STATE_INVALID"


@pytest.mark.asyncio
async def test_callback_redis_error_on_state_consume_raises_503(monkeypatch):
    """state 소진 중 RedisError → 503 OAUTH_PROVIDER_UNAVAILABLE."""
    from redis.exceptions import RedisError

    class _FailCtx:
        async def __aenter__(self):
            raise RedisError("redis down")

        async def __aexit__(self, *_):
            pass

    monkeypatch.setattr(
        "api.src.services.auth_service._make_redis_rl",
        lambda url: _FailCtx(),
    )
    provider = FakeProvider(name="kakao")
    db = _make_db([])
    with pytest.raises(HTTPException) as exc:
        await oauth_callback("kakao", "c", "ST", provider, "redis://fake", db)
    assert exc.value.status_code == 503
    assert exc.value.detail["code"] == "OAUTH_PROVIDER_UNAVAILABLE"


# ── AC-13 withdrawn user 제외 ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_callback_withdrawn_user_falls_through_to_signup(fake_redis_pair):
    """AC-13: oauth_identity는 있으나 user.withdrawn_at이 set → JOIN 필터에서 제외되어 재가입 분기.

    구현은 `oauth_identity JOIN users ON ... WHERE withdrawn_at IS NULL` — withdrawn user는
    .first()=None으로 나와 fall-through. 이메일·휴대폰 매칭도 없으면 pending_phone 분기로 진입.
    """
    otp, rl = fake_redis_pair
    state = await _prime_state(rl, "kakao")

    # 첫 쿼리(JOIN)=None, 이메일 매칭=None → provider phone=None이라 pending 분기
    db = _make_db([None, None])
    provider = FakeProvider(
        name="kakao",
        profile={"provider_sub": "dead-sub", "email": "dead@e.com", "phone": None},
    )
    result = await oauth_callback("kakao", "c", state, provider, "redis://fake", db)
    assert result["action"] == "signup_pending_phone"


# ── IntegrityError race recovery ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_callback_social_email_reuse_integrity_error_race_recovery(fake_redis_pair):
    """소셜 전용 유저 재매칭 시 oauth_identity INSERT가 IntegrityError → 재조회 후 login_completed."""
    from sqlalchemy.exc import IntegrityError

    _, rl = fake_redis_pair
    state = await _prime_state(rl, "kakao")

    social_user = _user_mock(id=9, password_hash=None)
    race_oi = MagicMock(user_id=9)

    db = AsyncMock(spec=AsyncSession)
    # 순차 execute 반환: 1) oauth_identity JOIN=None, 2) email 매칭=social_user, 3) 재조회 oi=race_oi
    calls = {"i": 0}

    async def exec_side(*args, **kwargs):
        i = calls["i"]
        calls["i"] += 1
        result = MagicMock()
        vals = [None, social_user, race_oi]
        v = vals[i] if i < len(vals) else None
        result.first.return_value = v if isinstance(v, tuple) else None
        result.scalar_one_or_none.return_value = v
        return result

    db.execute = AsyncMock(side_effect=exec_side)
    db.add = MagicMock()
    # 첫 flush에서 IntegrityError, 이후는 정상
    flush_calls = {"i": 0}

    async def flush_side():
        flush_calls["i"] += 1
        if flush_calls["i"] == 1:
            raise IntegrityError("stmt", {}, Exception("dup"))

    db.flush = AsyncMock(side_effect=flush_side)
    db.rollback = AsyncMock()

    provider = FakeProvider(
        name="kakao",
        profile={"provider_sub": "race-sub", "email": "social@e.com", "phone": None},
    )
    result = await oauth_callback("kakao", "c", state, provider, "redis://fake", db)
    assert result["action"] == "login_completed"
    assert result["user_id"] == 9
    db.rollback.assert_awaited()


@pytest.mark.asyncio
async def test_callback_phone_signup_integrity_error_becomes_phone_collision(fake_redis_pair):
    """Provider phone 제공 신규 가입 INSERT 시 IntegrityError → phone_collision 반환."""
    from sqlalchemy.exc import IntegrityError

    _, rl = fake_redis_pair
    state = await _prime_state(rl, "kakao")

    # JOIN=None, email_user=None, phone_dup=None (사전 검사는 통과) → INSERT에서만 race
    db = AsyncMock(spec=AsyncSession)
    calls = {"i": 0}

    async def exec_side(*args, **kwargs):
        i = calls["i"]
        calls["i"] += 1
        result = MagicMock()
        vals = [None, None, None]
        v = vals[i] if i < len(vals) else None
        result.first.return_value = None
        result.scalar_one_or_none.return_value = v
        return result

    db.execute = AsyncMock(side_effect=exec_side)
    db.add = MagicMock()
    db.flush = AsyncMock(side_effect=IntegrityError("stmt", {}, Exception("dup phone")))
    db.rollback = AsyncMock()

    provider = FakeProvider(
        name="kakao",
        profile={"provider_sub": "racesub", "email": "r@e.com", "phone": "01012345678"},
    )
    result = await oauth_callback("kakao", "c", state, provider, "redis://fake", db)
    assert result["action"] == "phone_collision"
    db.rollback.assert_awaited()


@pytest.mark.asyncio
async def test_callback_pending_set_redis_error_raises_503(fake_redis_pair, monkeypatch):
    """signup_pending_token 저장 시 RedisError → 503."""
    from redis.exceptions import RedisError

    _, rl = fake_redis_pair
    state = await _prime_state(rl, "kakao")

    class _FailSet:
        async def set(self, *a, **kw):
            raise RedisError("redis down")

        async def get(self, *a, **kw):
            return None

    class _FailCtx:
        async def __aenter__(self):
            return _FailSet()

        async def __aexit__(self, *_):
            pass

    monkeypatch.setattr(
        "api.src.services.auth_service._make_redis",
        lambda url: _FailCtx(),
    )

    db = _make_db([None, None])  # JOIN=None, email=None → phone=None이므로 pending 경로
    provider = FakeProvider(
        name="kakao",
        profile={"provider_sub": "x", "email": "new@e.com", "phone": None},
    )
    with pytest.raises(HTTPException) as exc:
        await oauth_callback("kakao", "c", state, provider, "redis://fake", db)
    assert exc.value.status_code == 503
    assert exc.value.detail["code"] == "OAUTH_PROVIDER_UNAVAILABLE"


# ── oauth_complete 에러 / 엣지 ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_complete_pending_json_parse_error_consumes_pending(fake_redis_pair):
    """pending JSON 파싱 실패 시 pending 소진(재시도 방지) + OAUTH_PENDING_INVALID."""
    otp, _ = fake_redis_pair
    await otp.set(_SIGNUP_PENDING_KEY.format(token="pt"), "not-json", ex=600)
    await otp.set(_TOKEN_KEY.format(token="pvt"), "01011112222", ex=600)

    db = _make_db([None])
    with pytest.raises(HTTPException) as exc:
        await oauth_complete_phone_supplement(
            signup_pending_token="pt",
            phone="01011112222",
            phone_verification_token="pvt",
            redis_url="redis://fake",
            db=db,
        )
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "OAUTH_PENDING_INVALID"
    # pending 소진 확인
    assert await otp.get(_SIGNUP_PENDING_KEY.format(token="pt")) is None


@pytest.mark.asyncio
async def test_complete_pending_missing_keys_rejected(fake_redis_pair):
    """pending payload에 provider/provider_sub/email 누락 시 OAUTH_PENDING_INVALID."""
    otp, _ = fake_redis_pair
    # provider_sub / email 누락
    await otp.set(
        _SIGNUP_PENDING_KEY.format(token="pt"),
        json.dumps({"provider": "kakao"}),
        ex=600,
    )
    await otp.set(_TOKEN_KEY.format(token="pvt"), "01011112222", ex=600)

    db = _make_db([None])
    with pytest.raises(HTTPException) as exc:
        await oauth_complete_phone_supplement(
            signup_pending_token="pt",
            phone="01011112222",
            phone_verification_token="pvt",
            redis_url="redis://fake",
            db=db,
        )
    assert exc.value.detail["code"] == "OAUTH_PENDING_INVALID"


@pytest.mark.asyncio
async def test_complete_pending_bad_provider_rejected(fake_redis_pair):
    """pending.provider가 {kakao,google,naver} 외면 거부."""
    otp, _ = fake_redis_pair
    await otp.set(
        _SIGNUP_PENDING_KEY.format(token="pt"),
        json.dumps({"provider": "facebook", "provider_sub": "s", "email": "e@x.com"}),
        ex=600,
    )
    await otp.set(_TOKEN_KEY.format(token="pvt"), "01011112222", ex=600)

    db = _make_db([None])
    with pytest.raises(HTTPException) as exc:
        await oauth_complete_phone_supplement(
            signup_pending_token="pt",
            phone="01011112222",
            phone_verification_token="pvt",
            redis_url="redis://fake",
            db=db,
        )
    assert exc.value.detail["code"] == "OAUTH_PENDING_INVALID"


@pytest.mark.asyncio
async def test_complete_phone_mismatch_preserves_pending(fake_redis_pair):
    """phone 토큰 불일치 시 pending은 소진되지 않아 재시도 가능 (UX)."""
    otp, _ = fake_redis_pair
    await otp.set(
        _SIGNUP_PENDING_KEY.format(token="pt"),
        json.dumps({"provider": "kakao", "provider_sub": "s", "email": "e@x.com"}),
        ex=600,
    )
    # 다른 phone으로 발급된 토큰
    await otp.set(_TOKEN_KEY.format(token="pvt"), "01099998888", ex=600)

    db = _make_db([])
    with pytest.raises(HTTPException) as exc:
        await oauth_complete_phone_supplement(
            signup_pending_token="pt",
            phone="01011112222",  # 토큰과 불일치
            phone_verification_token="pvt",
            redis_url="redis://fake",
            db=db,
        )
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "SMS_TOKEN_INVALID"
    # pending은 살아있어야 재시도 가능
    assert await otp.get(_SIGNUP_PENDING_KEY.format(token="pt")) is not None


@pytest.mark.asyncio
async def test_complete_social_user_phone_updated(fake_redis_pair):
    """이메일 매칭 소셜 전용 유저에 phone/phone_verified가 없으면 SMS 보충값으로 갱신."""
    otp, _ = fake_redis_pair
    await otp.set(
        _SIGNUP_PENDING_KEY.format(token="pt"),
        json.dumps({"provider": "kakao", "provider_sub": "newsub", "email": "social@e.com"}),
        ex=600,
    )
    await otp.set(_TOKEN_KEY.format(token="pvt"), "01011112222", ex=600)

    # 기존 소셜 유저 phone/phone_verified 미설정
    social_user = _user_mock(id=11, email="social@e.com", phone=None, password_hash=None)
    social_user.phone_verified = False
    db = _make_db([social_user, None])  # email match 후 phone 중복 체크 = None

    result = await oauth_complete_phone_supplement(
        signup_pending_token="pt",
        phone="01011112222",
        phone_verification_token="pvt",
        redis_url="redis://fake",
        db=db,
    )
    assert result.id == 11
    assert social_user.phone == "01011112222"
    assert social_user.phone_verified is True


@pytest.mark.asyncio
async def test_complete_redis_error_raises_503(monkeypatch):
    """oauth_complete_phone_supplement 중 RedisError → 503."""
    from redis.exceptions import RedisError

    class _FailCtx:
        async def __aenter__(self):
            raise RedisError("conn refused")

        async def __aexit__(self, *_):
            pass

    monkeypatch.setattr(
        "api.src.services.auth_service._make_redis",
        lambda url: _FailCtx(),
    )
    db = _make_db([])
    with pytest.raises(HTTPException) as exc:
        await oauth_complete_phone_supplement(
            signup_pending_token="pt",
            phone="01011112222",
            phone_verification_token="pvt",
            redis_url="redis://fake",
            db=db,
        )
    assert exc.value.status_code == 503
    assert exc.value.detail["code"] == "OAUTH_PROVIDER_UNAVAILABLE"


@pytest.mark.asyncio
async def test_complete_new_signup_integrity_error_becomes_phone_collision(fake_redis_pair):
    """신규 가입 INSERT에서 IntegrityError → 409 OAUTH_PHONE_COLLISION."""
    from sqlalchemy.exc import IntegrityError

    otp, _ = fake_redis_pair
    await otp.set(
        _SIGNUP_PENDING_KEY.format(token="pt"),
        json.dumps({"provider": "kakao", "provider_sub": "s", "email": "new@e.com"}),
        ex=600,
    )
    await otp.set(_TOKEN_KEY.format(token="pvt"), "01011112222", ex=600)

    db = AsyncMock(spec=AsyncSession)
    # email_user=None, phone_dup=None → 신규 가입 경로
    calls = {"i": 0}

    async def exec_side(*a, **kw):
        i = calls["i"]
        calls["i"] += 1
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        result.first.return_value = None
        return result

    db.execute = AsyncMock(side_effect=exec_side)
    db.add = MagicMock()
    db.flush = AsyncMock(side_effect=IntegrityError("stmt", {}, Exception("dup")))
    db.rollback = AsyncMock()

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
    db.rollback.assert_awaited()


# ── AC-10 PII 스크러빙 / 이벤트 카탈로그 ─────────────────────────────────────


def _assert_no_raw_pii(events: list, raw_email: str, raw_phone: str, raw_sub: str) -> None:
    """로그 이벤트 리스트를 검사하여 원본 email/phone/provider_sub가 노출되지 않았는지 확인."""
    for ev in events:
        # 모든 필드 값(문자열)을 하나로 합쳐 전수 검사
        text = json.dumps(ev, default=str, ensure_ascii=False)
        assert raw_email not in text, f"raw email leaked: {ev}"
        assert raw_phone not in text, f"raw phone leaked: {ev}"
        assert raw_sub not in text, f"raw provider_sub leaked: {ev}"


@pytest.mark.asyncio
async def test_login_completed_logs_masked_only(fake_redis_pair):
    """AC-10: login_completed 이벤트에 raw email/phone/provider_sub 원본이 없어야 함."""
    import structlog

    _, rl = fake_redis_pair
    state = await _prime_state(rl, "kakao")

    raw_email = "secret-leak@confidential.com"
    raw_phone = "01099990000"
    raw_sub = "kakao-sub-secret-xyz"

    oi = MagicMock(user_id=42)
    matched_user = _user_mock(id=42, email=raw_email, phone=raw_phone)
    db = _make_db([(oi, matched_user)])
    provider = FakeProvider(
        name="kakao",
        profile={"provider_sub": raw_sub, "email": raw_email, "phone": raw_phone},
    )

    with structlog.testing.capture_logs() as events:
        await oauth_callback("kakao", "c", state, provider, "redis://fake", db)

    # 이벤트명 검증
    assert any(ev["event"] == "auth.oauth.login_completed" for ev in events)
    # PII 원본 미노출
    _assert_no_raw_pii(events, raw_email, raw_phone, raw_sub)


@pytest.mark.asyncio
async def test_email_collision_logs_masked(fake_redis_pair):
    """AC-10: email_collision 이벤트에 마스킹된 email만, raw 값 없어야 함."""
    import structlog

    _, rl = fake_redis_pair
    state = await _prime_state(rl, "kakao")

    raw_email = "sensitive@targets.com"
    raw_sub = "collision-sub-abc"

    email_user = _user_mock(id=7, email=raw_email, password_hash="argon2hash")
    db = _make_db([None, email_user])
    provider = FakeProvider(
        name="kakao",
        profile={"provider_sub": raw_sub, "email": raw_email, "phone": None},
    )

    with structlog.testing.capture_logs() as events:
        await oauth_callback("kakao", "c", state, provider, "redis://fake", db)

    assert any(ev["event"] == "auth.oauth.email_collision" for ev in events)
    _assert_no_raw_pii(events, raw_email, "01099990000", raw_sub)


@pytest.mark.asyncio
async def test_phone_collision_logs_masked(fake_redis_pair):
    """AC-10: phone_collision 이벤트에 phone 원본 노출 없이 `****xxxx` 형식."""
    import structlog

    _, rl = fake_redis_pair
    state = await _prime_state(rl, "kakao")

    raw_phone = "01012347888"  # 뒷 4자리 = 7888
    raw_sub = "phonecoll-sub"

    phone_user = _user_mock(id=8, phone=raw_phone)
    db = _make_db([None, None, phone_user])
    provider = FakeProvider(
        name="kakao",
        profile={"provider_sub": raw_sub, "email": "new@e.com", "phone": raw_phone},
    )

    with structlog.testing.capture_logs() as events:
        await oauth_callback("kakao", "c", state, provider, "redis://fake", db)

    assert any(ev["event"] == "auth.oauth.phone_collision" for ev in events)
    # raw phone은 포함 X, masked 형식은 포함 O
    text = json.dumps(events, default=str, ensure_ascii=False)
    assert raw_phone not in text
    assert "****7888" in text  # phone 뒷자리 4자리 마스킹


@pytest.mark.asyncio
async def test_signup_pending_phone_logs_sub_hashed(fake_redis_pair):
    """AC-10: signup_pending_phone 이벤트에 provider_sub 원본 대신 sub_hash."""
    import structlog

    _, rl = fake_redis_pair
    state = await _prime_state(rl, "google")

    raw_sub = "google-sub-very-secret"
    db = _make_db([None, None])
    provider = FakeProvider(
        name="google",
        profile={"provider_sub": raw_sub, "email": "new@g.com", "phone": None},
    )

    with structlog.testing.capture_logs() as events:
        await oauth_callback("google", "c", state, provider, "redis://fake", db)

    assert any(ev["event"] == "auth.oauth.signup_pending_phone" for ev in events)
    text = json.dumps(events, default=str, ensure_ascii=False)
    assert raw_sub not in text


@pytest.mark.asyncio
async def test_state_invalid_event_emitted_on_missing_state(fake_redis_pair):
    """AC-10: state 미존재 시 auth.oauth.state_invalid 이벤트 emit."""
    import structlog

    # state를 prime하지 않음 → 직접 callback 호출하면 _consume_oauth_state에서 not_found
    provider = FakeProvider(name="kakao")
    db = _make_db([])

    with structlog.testing.capture_logs() as events:
        with pytest.raises(HTTPException):
            await oauth_callback("kakao", "c", "NON_EXISTENT_STATE", provider, "redis://fake", db)

    assert any(
        ev["event"] == "auth.oauth.state_invalid" and ev.get("reason") == "not_found"
        for ev in events
    ), f"expected state_invalid event with reason=not_found, got: {events}"
