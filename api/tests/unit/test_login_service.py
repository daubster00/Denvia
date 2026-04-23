"""login_user 단위 테스트 — fakeredis + DB mock으로 의존성 격리."""

import pytest
import fakeredis.aioredis as fakeredis
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.services.auth_service import (
    login_user,
    _LOGIN_BRUTE_THRESHOLD,
    _LOGIN_FAIL_KEY,
    _LOGIN_LOCKOUT_KEY,
)
from api.src.utils.argon2 import hash_password


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def fake_redis_rl(monkeypatch):
    """auth_service._make_redis_rl을 fakeredis로 교체 (Rate Limit DB)."""
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


def _make_user(email: str, password: str, sub_status: str = "free") -> MagicMock:
    user = MagicMock()
    user.id = 1
    user.email = email
    user.role = "user"
    user.subscription_status = sub_status
    user.password_hash = hash_password(password)
    user.withdrawn_at = None
    return user


def _mock_db_with_user(user):
    db = AsyncMock(spec=AsyncSession)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = user
    db.execute = AsyncMock(return_value=result_mock)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.rollback = AsyncMock()
    return db


def _mock_db_no_user():
    db = AsyncMock(spec=AsyncSession)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result_mock)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.rollback = AsyncMock()
    return db


# ── 로그인 성공 ───────────────────────────────────────────────────────────────

async def test_login_success_returns_user(fake_redis_rl):
    user = _make_user("doc@denvia.com", "correct_pw!")
    db = _mock_db_with_user(user)

    result = await login_user(
        email="doc@denvia.com",
        password="correct_pw!",
        persist_session=False,
        ip="1.2.3.4",
        ua="TestBrowser",
        redis_url="redis://fake",
        db=db,
    )
    assert result is user


async def test_login_success_clears_fail_counter(fake_redis_rl):
    """로그인 성공 시 실패 카운터가 삭제된다."""
    fail_key = _LOGIN_FAIL_KEY.format(email="doc@denvia.com")
    await fake_redis_rl.set(fail_key, "2", ex=300)

    user = _make_user("doc@denvia.com", "correct_pw!")
    db = _mock_db_with_user(user)

    await login_user(
        email="doc@denvia.com",
        password="correct_pw!",
        persist_session=True,
        ip="1.2.3.4",
        ua="TestBrowser",
        redis_url="redis://fake",
        db=db,
    )
    assert await fake_redis_rl.get(fail_key) is None


# ── 인증 실패 ─────────────────────────────────────────────────────────────────

async def test_login_wrong_password_401(fake_redis_rl):
    user = _make_user("doc@denvia.com", "correct_pw!")
    db = _mock_db_with_user(user)

    with pytest.raises(HTTPException) as exc:
        await login_user(
            email="doc@denvia.com",
            password="wrong_pw",
            persist_session=False,
            ip="1.2.3.4",
            ua="TestBrowser",
            redis_url="redis://fake",
            db=db,
        )
    assert exc.value.status_code == 401
    assert exc.value.detail["code"] == "AUTH_INVALID_CREDENTIALS"


async def test_login_email_not_exist_401(fake_redis_rl):
    """이메일 미존재 시에도 동일한 AUTH_INVALID_CREDENTIALS 응답 (이메일 열거 방지)."""
    db = _mock_db_no_user()

    with pytest.raises(HTTPException) as exc:
        await login_user(
            email="ghost@denvia.com",
            password="anything",
            persist_session=False,
            ip="1.2.3.4",
            ua="TestBrowser",
            redis_url="redis://fake",
            db=db,
        )
    assert exc.value.status_code == 401
    assert exc.value.detail["code"] == "AUTH_INVALID_CREDENTIALS"


async def test_login_wrong_password_increments_counter(fake_redis_rl):
    user = _make_user("doc@denvia.com", "correct_pw!")
    db = _mock_db_with_user(user)

    with pytest.raises(HTTPException):
        await login_user("doc@denvia.com", "wrong", False, "1.2.3.4", "ua", "redis://fake", db)

    fail_key = _LOGIN_FAIL_KEY.format(email="doc@denvia.com")
    count = await fake_redis_rl.get(fail_key)
    assert count == "1"


# ── 브루트포스 ────────────────────────────────────────────────────────────────

async def test_login_brute_force_anomaly_inserted_on_threshold(fake_redis_rl):
    """3회 연속 실패 시 anomaly_events INSERT가 호출된다."""
    user = _make_user("brute@denvia.com", "correct_pw!")
    db = _mock_db_with_user(user)

    fail_key = _LOGIN_FAIL_KEY.format(email="brute@denvia.com")
    # 이미 2회 실패 상태 주입
    await fake_redis_rl.set(fail_key, str(_LOGIN_BRUTE_THRESHOLD - 1), ex=300)

    with pytest.raises(HTTPException) as exc:
        await login_user("brute@denvia.com", "wrong", False, "1.2.3.4", "Mozilla", "redis://fake", db)

    assert exc.value.status_code == 401
    # AnomalyEvent가 db.add로 추가되었는지 확인
    db.add.assert_called_once()
    added = db.add.call_args[0][0]
    assert added.type == "login_brute_force"
    assert added.details["attempt_count"] == _LOGIN_BRUTE_THRESHOLD


async def test_login_lockout_after_threshold(fake_redis_rl):
    """3회 실패 후 lockout 키가 Redis에 저장된다."""
    user = _make_user("brute@denvia.com", "correct_pw!")
    db = _mock_db_with_user(user)

    fail_key = _LOGIN_FAIL_KEY.format(email="brute@denvia.com")
    lockout_key = _LOGIN_LOCKOUT_KEY.format(email="brute@denvia.com")
    await fake_redis_rl.set(fail_key, str(_LOGIN_BRUTE_THRESHOLD - 1), ex=300)

    with pytest.raises(HTTPException):
        await login_user("brute@denvia.com", "wrong", False, "1.2.3.4", "ua", "redis://fake", db)

    assert await fake_redis_rl.get(lockout_key) == "1"


async def test_login_lockout_returns_429(fake_redis_rl):
    """락아웃 중 요청 → 429 AUTH_TEMPORARILY_LOCKED."""
    lockout_key = _LOGIN_LOCKOUT_KEY.format(email="locked@denvia.com")
    await fake_redis_rl.set(lockout_key, "1", ex=300)

    db = _mock_db_no_user()

    with pytest.raises(HTTPException) as exc:
        await login_user("locked@denvia.com", "anything", False, "1.2.3.4", "ua", "redis://fake", db)

    assert exc.value.status_code == 429
    assert exc.value.detail["code"] == "AUTH_TEMPORARILY_LOCKED"


async def test_login_anomaly_target_user_id_null_when_email_not_exist(fake_redis_rl):
    """이메일 미존재 시 anomaly_events.target_user_id = NULL."""
    db = _mock_db_no_user()

    fail_key = _LOGIN_FAIL_KEY.format(email="ghost@denvia.com")
    await fake_redis_rl.set(fail_key, str(_LOGIN_BRUTE_THRESHOLD - 1), ex=300)

    with pytest.raises(HTTPException):
        await login_user("ghost@denvia.com", "wrong", False, "1.2.3.4", "ua", "redis://fake", db)

    db.add.assert_called_once()
    added = db.add.call_args[0][0]
    assert added.target_user_id is None
