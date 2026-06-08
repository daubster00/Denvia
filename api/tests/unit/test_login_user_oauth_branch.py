"""login_user OAuth-only 분기 단위 테스트 — Story 1.8 (AC-1, 2, 5, 6, 7, 12)."""

import pytest
import fakeredis.aioredis as fakeredis
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.services.auth_service import (
    login_user,
    _LOGIN_BRUTE_THRESHOLD,
    _LOGIN_FAIL_KEY,
    _LOGIN_LOCKOUT_KEY,
    _PROVIDER_LABEL_KO,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def fake_redis_rl(monkeypatch):
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


def _make_oauth_only_user(email="social@denvia.com", providers=("naver",)):
    """password_hash=None인 OAuth-only 사용자 mock."""
    user = MagicMock()
    user.id = 42
    user.email = email
    user.role = "user"
    user.subscription_status = "free"
    user.password_hash = None
    user.withdrawn_at = None
    user.current_session_id = None
    user.admin_grade = "master"
    return user


def _mock_db_oauth_only(user, provider_list):
    """
    첫 execute: User 조회 결과
    두 번째 execute: OAuthIdentity.provider 조회 결과
    """
    db = AsyncMock(spec=AsyncSession)

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user

    oauth_result = MagicMock()
    oauth_result.scalars.return_value.all.return_value = list(provider_list)

    db.execute = AsyncMock(side_effect=[user_result, oauth_result])
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


# ── AC-1: OAuth-only 분기 기본 동작 ───────────────────────────────────────────

async def test_oauth_only_단일_provider_409(fake_redis_rl):
    """네이버 단독 OAuth-only → 409 AUTH_ACCOUNT_OAUTH_ONLY."""
    user = _make_oauth_only_user()
    db = _mock_db_oauth_only(user, ["naver"])

    with pytest.raises(HTTPException) as exc:
        await login_user("social@denvia.com", "anything", False, "1.2.3.4", "ua", "redis://fake", db)

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "AUTH_ACCOUNT_OAUTH_ONLY"
    assert exc.value.detail["linked_providers"] == ["naver"]


async def test_oauth_only_단일_provider_메시지(fake_redis_rl):
    """네이버 단독 → 메시지에 '네이버로 가입/로그인' 포함."""
    user = _make_oauth_only_user()
    db = _mock_db_oauth_only(user, ["naver"])

    with pytest.raises(HTTPException) as exc:
        await login_user("social@denvia.com", "anything", False, "1.2.3.4", "ua", "redis://fake", db)

    msg = exc.value.detail["message"]
    assert "네이버로 가입되어 있습니다" in msg
    assert "네이버로 로그인해 주세요" in msg


async def test_oauth_only_다중_provider_메시지(fake_redis_rl):
    """카카오+구글 → 복수형 메시지 '가입한 채널로 로그인해 주세요'."""
    user = _make_oauth_only_user()
    db = _mock_db_oauth_only(user, ["kakao", "google"])

    with pytest.raises(HTTPException) as exc:
        await login_user("social@denvia.com", "anything", False, "1.2.3.4", "ua", "redis://fake", db)

    assert exc.value.detail["linked_providers"] == ["kakao", "google"]
    msg = exc.value.detail["message"]
    assert "카카오, 구글로 가입되어 있습니다" in msg
    assert "가입한 채널로 로그인해 주세요" in msg


# ── AC-6: provider 정렬 및 중복 제거 ─────────────────────────────────────────

async def test_oauth_only_provider_순서_보존(fake_redis_rl):
    """linked_at 오름차순으로 조회된 순서가 그대로 응답에 반영된다."""
    user = _make_oauth_only_user()
    # DB에서 linked_at ASC 순으로 리턴됨 (naver 먼저 가입)
    db = _mock_db_oauth_only(user, ["naver", "kakao"])

    with pytest.raises(HTTPException) as exc:
        await login_user("social@denvia.com", "anything", False, "1.2.3.4", "ua", "redis://fake", db)

    assert exc.value.detail["linked_providers"] == ["naver", "kakao"]


async def test_oauth_only_provider_중복_제거(fake_redis_rl):
    """DB에 중복 provider 행이 있어도 한 번만 등장."""
    user = _make_oauth_only_user()
    db = _mock_db_oauth_only(user, ["kakao", "kakao", "naver"])

    with pytest.raises(HTTPException) as exc:
        await login_user("social@denvia.com", "anything", False, "1.2.3.4", "ua", "redis://fake", db)

    providers = exc.value.detail["linked_providers"]
    assert providers.count("kakao") == 1


async def test_oauth_only_화이트리스트_필터(fake_redis_rl):
    """허용되지 않은 provider 값('kakao_v2')은 무시된다."""
    user = _make_oauth_only_user()
    db = _mock_db_oauth_only(user, ["kakao_v2", "naver"])

    with pytest.raises(HTTPException) as exc:
        await login_user("social@denvia.com", "anything", False, "1.2.3.4", "ua", "redis://fake", db)

    assert exc.value.detail["linked_providers"] == ["naver"]


# ── AC-12: 실패 카운터 증가 및 락아웃 ──────────────────────────────────────────

async def test_oauth_only_fail_counter_증가(fake_redis_rl):
    """OAuth-only 분기도 이메일 로그인 실패 카운터를 증가시킨다."""
    user = _make_oauth_only_user()
    db = _mock_db_oauth_only(user, ["naver"])

    with pytest.raises(HTTPException):
        await login_user("social@denvia.com", "anything", False, "1.2.3.4", "ua", "redis://fake", db)

    fail_key = _LOGIN_FAIL_KEY.format(email="social@denvia.com")
    assert await fake_redis_rl.get(fail_key) == "1"


async def test_oauth_only_임계치_도달_시_lockout_설정(fake_redis_rl):
    """임계치 도달 후 lockout 키가 Redis에 설정된다."""
    user = _make_oauth_only_user()
    fail_key = _LOGIN_FAIL_KEY.format(email="social@denvia.com")
    lockout_key = _LOGIN_LOCKOUT_KEY.format(email="social@denvia.com")
    await fake_redis_rl.set(fail_key, str(_LOGIN_BRUTE_THRESHOLD - 1), ex=300)

    db = _mock_db_oauth_only(user, ["naver"])

    with pytest.raises(HTTPException) as exc:
        await login_user("social@denvia.com", "anything", False, "1.2.3.4", "ua", "redis://fake", db)

    # 현재 요청은 409 반환
    assert exc.value.status_code == 409
    # lockout 키가 설정됨
    assert await fake_redis_rl.get(lockout_key) == "1"


async def test_oauth_only_임계치_anomaly_이유_기록(fake_redis_rl):
    """임계치 도달 시 anomaly_events에 reason='oauth_only_hint' 기록 + commit으로 persist."""
    user = _make_oauth_only_user()
    fail_key = _LOGIN_FAIL_KEY.format(email="social@denvia.com")
    await fake_redis_rl.set(fail_key, str(_LOGIN_BRUTE_THRESHOLD - 1), ex=300)

    db = _mock_db_oauth_only(user, ["naver"])

    with pytest.raises(HTTPException):
        await login_user("social@denvia.com", "anything", False, "1.2.3.4", "ua", "redis://fake", db)

    db.add.assert_called_once()
    added = db.add.call_args[0][0]
    assert added.type == "login_brute_force"
    assert added.details["reason"] == "oauth_only_hint"
    assert added.target_user_id == user.id
    # commit이 호출되어야 실제 DB에 저장됨 (flush만으로는 HTTPException raise 후 rollback됨)
    db.commit.assert_called()


async def test_oauth_only_임계치_다음_요청_429(fake_redis_rl):
    """임계치 도달 후 다음 요청은 429 AUTH_TEMPORARILY_LOCKED."""
    lockout_key = _LOGIN_LOCKOUT_KEY.format(email="social@denvia.com")
    await fake_redis_rl.set(lockout_key, "1", ex=300)

    db = _mock_db_no_user()

    with pytest.raises(HTTPException) as exc:
        await login_user("social@denvia.com", "anything", False, "1.2.3.4", "ua", "redis://fake", db)

    assert exc.value.status_code == 429
    assert exc.value.detail["code"] == "AUTH_TEMPORARILY_LOCKED"


# ── AC-5: 탈퇴 사용자 / orphan 상태 fall-through ──────────────────────────────

async def test_oauth_only_orphan_oauth_0개_fall_through(fake_redis_rl):
    """password_hash=None + oauth_identity 0개 비정상 상태 → 기존 401 경로."""
    user = _make_oauth_only_user()
    db = _mock_db_oauth_only(user, [])  # oauth_identity 없음

    with pytest.raises(HTTPException) as exc:
        await login_user("social@denvia.com", "anything", False, "1.2.3.4", "ua", "redis://fake", db)

    assert exc.value.status_code == 401
    assert exc.value.detail["code"] == "AUTH_INVALID_CREDENTIALS"


# ── AC-3: 이메일+OAuth 동시 가입 사용자 정상 로그인 (password_hash NOT NULL) ─────

async def test_password_hash_not_null_oauth_identity_있어도_정상_로그인(fake_redis_rl):
    """password_hash NOT NULL이면 OAuth-only 분기에 진입하지 않는다."""
    from api.src.utils.argon2 import hash_password

    user = MagicMock()
    user.id = 99
    user.email = "dual@denvia.com"
    user.role = "user"
    user.subscription_status = "free"
    user.password_hash = hash_password("correct_pw!")
    user.withdrawn_at = None

    db = AsyncMock(spec=AsyncSession)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = user
    db.execute = AsyncMock(return_value=result_mock)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.rollback = AsyncMock()

    result = await login_user("dual@denvia.com", "correct_pw!", False, "1.2.3.4", "ua", "redis://fake", db)
    assert result is user


# ── AC-7: structlog 이벤트 검증 ───────────────────────────────────────────────

async def test_oauth_only_structlog_이벤트_emit(fake_redis_rl):
    """auth.login.oauth_only_hint 이벤트가 마스킹된 이메일로 기록된다."""
    import structlog.testing

    user = _make_oauth_only_user(email="social@denvia.com")
    db = _mock_db_oauth_only(user, ["kakao"])

    with structlog.testing.capture_logs() as cap_logs:
        with pytest.raises(HTTPException):
            await login_user("social@denvia.com", "anything", False, "10.0.0.1", "ua", "redis://fake", db)

    hint_logs = [l for l in cap_logs if l.get("event") == "auth.login.oauth_only_hint"]
    assert len(hint_logs) == 1
    log = hint_logs[0]
    assert log["user_id"] == user.id
    assert log["providers"] == ["kakao"]
    assert log["ip"] == "10.0.0.1"
    # 마스킹 확인 — raw 이메일 노출 금지
    assert "social@denvia.com" not in str(log.get("email", ""))


# ── _PROVIDER_LABEL_KO 상수 검증 ──────────────────────────────────────────────

def test_provider_label_ko_매핑_완전성():
    """3개 provider 모두 한국어 라벨 존재."""
    assert _PROVIDER_LABEL_KO["kakao"] == "카카오"
    assert _PROVIDER_LABEL_KO["google"] == "구글"
    assert _PROVIDER_LABEL_KO["naver"] == "네이버"
