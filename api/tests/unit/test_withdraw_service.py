"""auth_service.withdraw 단위 테스트 — Story 1.7.

mock AsyncSession으로 PII 익명화 / oauth_identity DELETE / qa_logs UPDATE / AuditLog INSERT를
호출 인자 수준에서 검증한다. Pro 차단 분기도 함께 확인.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from api.src.middleware.audit_actions import AUDIT_USER_WITHDRAW
from api.src.models.audit_log import AuditLog
from api.src.services.auth_service import withdraw


def _user(user_id: int = 42, sub_status: str = "free") -> MagicMock:
    u = MagicMock()
    u.id = user_id
    u.email = "user@example.com"
    u.phone = "01011112222"
    u.phone_verified = True
    u.password_hash = "$argon2id$dummy"
    u.subscription_status = sub_status
    u.withdrawn_at = None
    u.updated_at = datetime.now(tz=timezone.utc)
    u.current_session_id = None
    u.admin_grade = "master"
    return u


class _StubSession:
    def __init__(self):
        self.executed = []
        self.added = []
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    async def execute(self, stmt):
        self.executed.append(stmt)
        return MagicMock()

    def add(self, obj):
        self.added.append(obj)


@pytest.mark.asyncio
async def test_withdraw_blocks_pro_user():
    """sub_status='pro' → 409 SUBSCRIPTION_ACTIVE_MUST_CANCEL_FIRST."""
    user = _user(sub_status="pro")
    session = _StubSession()

    with pytest.raises(HTTPException) as exc:
        await withdraw(user=user, ip="127.0.0.1", ua="ua", db=session)

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "SUBSCRIPTION_ACTIVE_MUST_CANCEL_FIRST"
    # 어떤 변경도 발생하지 않아야 함
    assert session.commit.call_count == 0
    assert len(session.executed) == 0
    assert len(session.added) == 0


@pytest.mark.asyncio
async def test_withdraw_anonymizes_pii_and_inserts_audit():
    """free 사용자 → PII 덮어쓰기 + DELETE/UPDATE 2회 + AuditLog INSERT + commit 1회."""
    user = _user(sub_status="free")
    original_id = user.id
    session = _StubSession()

    await withdraw(user=user, ip="1.2.3.4", ua="agent", db=session, trace_id=None)

    # PII 필드 익명화 검증
    assert user.email.startswith(f"withdrawn_{original_id}_")
    assert user.phone is None
    assert user.phone_verified is False  # 코드리뷰 P3 — 휴대폰 검증 플래그도 함께 클리어
    assert user.password_hash is None
    assert user.withdrawn_at is not None
    assert user.withdrawn_at.tzinfo is timezone.utc

    # SQL execute 2회 (oauth DELETE + qa_logs UPDATE)
    assert len(session.executed) == 2

    # AuditLog INSERT 검증
    assert len(session.added) == 1
    audit_obj = session.added[0]
    assert isinstance(audit_obj, AuditLog)
    assert audit_obj.actor_user_id == original_id
    assert audit_obj.action == AUDIT_USER_WITHDRAW
    assert audit_obj.target_type == "user"
    assert audit_obj.target_id == original_id
    assert audit_obj.diff_json["subscription_status_before"] == "free"
    assert "withdrawn_at" in audit_obj.diff_json
    assert audit_obj.ip == "1.2.3.4"
    assert audit_obj.ua == "agent"

    # 단일 commit
    assert session.commit.call_count == 1


@pytest.mark.asyncio
async def test_withdraw_blocked_status_proceeds():
    """blocked 사용자도 free와 동일하게 탈퇴 가능 (pro만 차단)."""
    user = _user(sub_status="blocked")
    session = _StubSession()

    await withdraw(user=user, ip=None, ua=None, db=session)

    assert user.password_hash is None
    assert user.withdrawn_at is not None
    assert session.commit.call_count == 1
    audit_obj = session.added[0]
    assert audit_obj.diff_json["subscription_status_before"] == "blocked"


# ── 코드리뷰 P2 — trace_id 안전 파싱 ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_withdraw_accepts_uuid_string_trace_id():
    """TraceMiddleware가 보내는 정상 UUID 문자열을 안전 파싱하여 audit에 보존."""
    user = _user()
    session = _StubSession()
    valid_uuid_str = "12345678-1234-5678-1234-567812345678"

    await withdraw(user=user, ip=None, ua=None, db=session, trace_id=valid_uuid_str)

    audit_obj = session.added[0]
    assert isinstance(audit_obj.trace_id, uuid.UUID)
    assert str(audit_obj.trace_id) == valid_uuid_str


@pytest.mark.asyncio
async def test_withdraw_drops_invalid_trace_id_without_failing_transaction():
    """비-UUID X-Trace-Id 헤더가 audit INSERT를 폭파시키지 않도록 None으로 강제."""
    user = _user()
    session = _StubSession()

    await withdraw(user=user, ip=None, ua=None, db=session, trace_id="not-a-uuid")

    # 트랜잭션은 정상 commit 되고, trace_id만 None으로 격리됨
    assert session.commit.call_count == 1
    audit_obj = session.added[0]
    assert audit_obj.trace_id is None
    # 그래도 PII 익명화는 정상 진행
    assert user.withdrawn_at is not None


@pytest.mark.asyncio
async def test_withdraw_passes_uuid_object_through_unchanged():
    """uuid.UUID 객체를 직접 받으면 그대로 audit에 보존."""
    user = _user()
    session = _StubSession()
    tid = uuid.uuid4()

    await withdraw(user=user, ip=None, ua=None, db=session, trace_id=tid)

    audit_obj = session.added[0]
    assert audit_obj.trace_id == tid
