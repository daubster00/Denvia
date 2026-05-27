"""request_password_reset 단위 테스트 — fakeredis + DB mock."""

import pytest
import fakeredis.aioredis as fakeredis
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.services.auth_service import (
    request_password_reset,
    _RECOVERY_KEY,
    _RECOVERY_ABUSE_THRESHOLD,
)
from api.src.integrations.messaging.adapters.stub import StubMessagingAdapter
from api.src.utils.argon2 import hash_password, verify_password


# ── Fixtures ──────────────────────────────────────────────────────────────────

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


def _make_user(email: str, phone: str, password: str | None = "password123") -> MagicMock:
    user = MagicMock()
    user.id = 1
    user.email = email
    user.phone = phone
    user.password_hash = hash_password(password) if password else None
    user.must_reset_password = False
    user.withdrawn_at = None
    user.updated_at = None
    return user


def _mock_db_with_user(user, providers: list[str] | None = None) -> AsyncMock:
    """DB mock — 첫 execute는 User 조회, 두 번째는 OAuthIdentity.provider 목록.

    providers=None: 단일 User 조회만 일어나는 일반 가입자 케이스.
    providers=[...]: 소셜 전용 계정 케이스(서비스가 provider 목록을 추가 조회함).
    """
    db = AsyncMock(spec=AsyncSession)
    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user
    if providers is None:
        db.execute = AsyncMock(return_value=user_result)
    else:
        provider_result = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = providers
        provider_result.scalars.return_value = scalars_mock
        db.execute = AsyncMock(side_effect=[user_result, provider_result])
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


@pytest.fixture
def messaging():
    return StubMessagingAdapter()


# ── 매칭 — 이메일 가입자 ──────────────────────────────────────────────────────

async def test_매칭_이메일가입자_임시비밀번호_sms_발송(fake_redis_rl, messaging):
    user = _make_user("doc@denvia.com", "01012345678")
    db = _mock_db_with_user(user)

    await request_password_reset(
        email="doc@denvia.com",
        phone="01012345678",
        ip="1.2.3.4",
        ua="ua",
        redis_url="redis://fake",
        db=db,
        messaging=messaging,
    )

    # must_reset_password 플래그 설정 확인
    assert user.must_reset_password is True
    # password_hash가 변경됨 (새 해시가 설정됨)
    assert user.password_hash != hash_password("password123")


async def test_매칭_이메일가입자_임시비밀번호_검증가능(fake_redis_rl, messaging):
    """발급된 임시 비밀번호로 실제 verify_password가 통과해야 한다."""
    captured_sms: list[str] = []

    class CapturingMessaging:
        async def send_sms(self, phone: str, body: str) -> None:
            captured_sms.append(body)

        async def send_sms_otp(self, phone: str, otp: str) -> None:
            pass

    user = _make_user("doc@denvia.com", "01012345678")
    db = _mock_db_with_user(user)

    await request_password_reset(
        email="doc@denvia.com",
        phone="01012345678",
        ip=None,
        ua=None,
        redis_url="redis://fake",
        db=db,
        messaging=CapturingMessaging(),
    )

    assert len(captured_sms) == 1
    # SMS 본문에서 임시 비밀번호 추출 ("Denvia 임시 비밀번호: XXXXXXXX ...")
    sms_body = captured_sms[0]
    assert "Denvia 임시 비밀번호:" in sms_body
    temp_pw = sms_body.split("Denvia 임시 비밀번호: ")[1].split(" ")[0]
    assert len(temp_pw) == 8
    assert verify_password(temp_pw, user.password_hash) is True


# ── 매칭 — 소셜 전용 계정 ────────────────────────────────────────────────────

async def test_매칭_소셜전용_sms_미발송(fake_redis_rl, messaging):
    user = _make_user("social@denvia.com", "01099998888", password=None)
    db = _mock_db_with_user(user, providers=["kakao"])

    # SMS가 발송되지 않음 확인 (messaging.send_sms 호출 없음)
    sms_sent: list = []

    class TrackingMessaging:
        async def send_sms(self, phone: str, body: str) -> None:
            sms_sent.append(body)

        async def send_sms_otp(self, phone: str, otp: str) -> None:
            pass

    linked = await request_password_reset(
        email="social@denvia.com",
        phone="01099998888",
        ip=None,
        ua=None,
        redis_url="redis://fake",
        db=db,
        messaging=TrackingMessaging(),
    )
    assert len(sms_sent) == 0
    assert user.must_reset_password is False
    # 연결된 provider 목록이 응답에 담겨 반환됨 — 프론트가 안내 + 소셜 버튼 노출에 사용.
    assert linked == ["kakao"]


async def test_매칭_소셜전용_linked_providers_반환(fake_redis_rl, messaging):
    """OAuthIdentity 다중 연결 시 모든 provider가 응답에 포함된다."""
    user = _make_user("social@denvia.com", "01099998888", password=None)
    db = _mock_db_with_user(user, providers=["kakao", "naver"])

    linked = await request_password_reset(
        email="social@denvia.com",
        phone="01099998888",
        ip=None,
        ua=None,
        redis_url="redis://fake",
        db=db,
        messaging=messaging,
    )
    assert linked == ["kakao", "naver"]


# ── 불일치 ────────────────────────────────────────────────────────────────────

async def test_불일치_200_응답_sms_미발송(fake_redis_rl, messaging):
    db = _mock_db_no_user()

    # 예외 없이 반환되어야 함
    await request_password_reset(
        email="ghost@denvia.com",
        phone="01000000000",
        ip=None,
        ua=None,
        redis_url="redis://fake",
        db=db,
        messaging=messaging,
    )


# ── recovery_abuse 이상탐지 ──────────────────────────────────────────────────

async def test_recovery_abuse_4회째_anomaly_insert(fake_redis_rl, messaging):
    db = _mock_db_no_user()
    phone = "01012345678"
    recovery_key = _RECOVERY_KEY.format(phone=phone)

    # 3회 선 주입
    await fake_redis_rl.set(recovery_key, str(_RECOVERY_ABUSE_THRESHOLD - 1), ex=3600)

    await request_password_reset(
        email="ghost@denvia.com",
        phone=phone,
        ip="1.2.3.4",
        ua="ua",
        redis_url="redis://fake",
        db=db,
        messaging=messaging,
    )

    db.add.assert_called_once()
    added = db.add.call_args[0][0]
    assert added.type == "recovery_abuse"
    assert added.details["phone_tail"] == phone[-4:]
    assert added.details["attempt_count"] == _RECOVERY_ABUSE_THRESHOLD
    assert added.details["endpoint"] == "find-password"


async def test_recovery_abuse_임계미달_anomaly_없음(fake_redis_rl, messaging):
    db = _mock_db_no_user()

    await request_password_reset(
        email="ghost@denvia.com",
        phone="01012345678",
        ip=None,
        ua=None,
        redis_url="redis://fake",
        db=db,
        messaging=messaging,
    )

    db.add.assert_not_called()
