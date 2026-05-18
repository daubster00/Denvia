"""Story 9.2 — billing.extend_active_subscriptions 통합 테스트.

manual_total 해제 시 자동 enqueue되는 Celery 태스크의 핵심 분기:
- killswitch row 미존재/잘못된 mode → skip
- 활성 구독 N건 + cancel_pending 1건 → 모두 연장 + audit_logs INSERT N+1건
- duration 정확성 (deactivated_at - activated_at)
- idempotency_key 형식

2026-05-18 — `subscription.extended_due_to_killswitch` 알림톡 발송 폐지에 따라
알림 발송 검증은 제거. 구독 기간 연장 자체와 audit_logs만 확인.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest


def _scalar_result(obj):
    r = MagicMock()
    r.scalar_one_or_none = MagicMock(return_value=obj)
    return r


def _scalars_result(objs):
    r = MagicMock()
    r.scalars.return_value.all.return_value = objs
    return r


def _make_killswitch_state(
    mode: str = "manual_total",
    activated_at: datetime | None = None,
    deactivated_at: datetime | None = None,
):
    ks = MagicMock()
    ks.id = 42
    ks.mode = mode
    now = datetime.now(UTC)
    ks.activated_at = activated_at or (now - timedelta(hours=2))
    ks.deactivated_at = deactivated_at or now
    return ks


def _make_subscription(sub_id: int, user_id: int, status: str = "active"):
    sub = MagicMock()
    sub.id = sub_id
    sub.user_id = user_id
    sub.status = status
    now = datetime.now(UTC)
    sub.current_period_end = now + timedelta(days=10)
    sub.next_charge_at = now + timedelta(days=10)
    return sub


@pytest.mark.asyncio
async def test_skip_when_killswitch_not_found():
    from api.src.services.billing_service import extend_active_subscriptions

    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalar_result(None))
    db.commit = AsyncMock()

    result = await extend_active_subscriptions(killswitch_state_id=999, db=db)
    assert result == {"status": "skip", "reason": "not_found"}


@pytest.mark.asyncio
async def test_skip_when_invalid_state_auto_mode():
    from api.src.services.billing_service import extend_active_subscriptions

    ks = _make_killswitch_state(mode="auto_free_only")
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalar_result(ks))
    db.commit = AsyncMock()

    result = await extend_active_subscriptions(killswitch_state_id=42, db=db)
    assert result["status"] == "skip"
    assert result["reason"] == "invalid_state"


@pytest.mark.asyncio
async def test_skip_when_not_yet_deactivated():
    from api.src.services.billing_service import extend_active_subscriptions

    ks = _make_killswitch_state(mode="manual_total", deactivated_at=None)
    ks.deactivated_at = None
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalar_result(ks))
    db.commit = AsyncMock()

    result = await extend_active_subscriptions(killswitch_state_id=42, db=db)
    assert result["status"] == "skip"


@pytest.mark.asyncio
async def test_extends_active_and_cancel_pending_with_audit_log():
    """활성 1건 + cancel_pending 1건 → 모두 연장 + audit_logs INSERT 2건."""
    from api.src.models.audit_log import AuditLog
    from api.src.services.billing_service import extend_active_subscriptions

    activated = datetime.now(UTC) - timedelta(hours=2)
    deactivated = datetime.now(UTC)
    ks = _make_killswitch_state(activated_at=activated, deactivated_at=deactivated)

    sub_active = _make_subscription(sub_id=101, user_id=7, status="active")
    sub_cancel = _make_subscription(sub_id=102, user_id=8, status="cancel_pending")

    db = AsyncMock()
    db.commit = AsyncMock()
    added: list = []
    db.add = MagicMock(side_effect=lambda o: added.append(o))

    # 2026-05-18 — 알림톡 발송 폐지로 user SELECT 단계 제거.
    # execute side_effects 순서:
    # 1. SELECT killswitch
    # 2. SELECT targets (active + cancel_pending 2건)
    # 3. SELECT FOR UPDATE sub_active
    # 4. SELECT AuditLog idempotency check for sub_active → None (미처리)
    # 5. SELECT FOR UPDATE sub_cancel
    # 6. SELECT AuditLog idempotency check for sub_cancel → None (미처리)
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result(ks),
            _scalars_result([sub_active, sub_cancel]),
            _scalar_result(sub_active),
            _scalar_result(None),       # idempotency check sub_active: 미처리
            _scalar_result(sub_cancel),
            _scalar_result(None),       # idempotency check sub_cancel: 미처리
        ]
    )

    result = await extend_active_subscriptions(killswitch_state_id=42, db=db)

    assert result["status"] == "ok"
    assert result["extended_count"] == 2
    assert result["killswitch_state_id"] == 42
    # 정지 기간(2시간 = 7200초)
    assert 7100 <= result["duration_seconds"] <= 7300

    # AuditLog가 2건 add됨
    audit_rows = [a for a in added if isinstance(a, AuditLog)]
    assert len(audit_rows) == 2
    actions = {a.action for a in audit_rows}
    assert actions == {"subscription.extended_killswitch"}
    # actor_user_id 시스템(NULL)
    for a in audit_rows:
        assert a.actor_user_id is None
        assert a.target_type == "subscription"
        assert a.diff_json["killswitch_state_id"] == 42
        assert "duration_seconds" in a.diff_json


@pytest.mark.asyncio
async def test_idempotent_skip_already_extended_subscription():
    """동일 killswitch_state_id로 재실행 시 이미 처리된 구독은 skip된다.

    audit_logs에 subscription.extended_killswitch 레코드가 있으면
    extended_count에 포함되지 않고 기간도 다시 늘지 않는다.
    """
    from api.src.models.audit_log import AuditLog
    from api.src.services.billing_service import extend_active_subscriptions

    activated = datetime.now(UTC) - timedelta(hours=1)
    deactivated = datetime.now(UTC)
    ks = _make_killswitch_state(activated_at=activated, deactivated_at=deactivated)

    sub = _make_subscription(sub_id=201, user_id=9, status="active")
    original_period_end = sub.current_period_end

    # 이미 처리된 것을 나타내는 AuditLog mock
    existing_audit = MagicMock(spec=AuditLog)

    db = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()

    # execute 순서:
    # 1. SELECT killswitch
    # 2. SELECT targets (1건)
    # 3. SELECT FOR UPDATE sub
    # 4. SELECT AuditLog idempotency check → 이미 존재 → skip
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result(ks),
            _scalars_result([sub]),
            _scalar_result(sub),
            _scalar_result(existing_audit),
        ]
    )

    result = await extend_active_subscriptions(killswitch_state_id=42, db=db)

    assert result["status"] == "ok"
    assert result["extended_count"] == 0  # 이미 처리됐으므로 0
    db.add.assert_not_called()  # AuditLog 추가 없음
    # 구독 기간이 변경되지 않음
    assert sub.current_period_end == original_period_end


@pytest.mark.asyncio
async def test_new_subscription_extended_but_old_skipped():
    """같은 killswitch에 구독 A(이미 처리)와 B(미처리)가 섞여 있을 때 B만 연장된다."""
    from api.src.models.audit_log import AuditLog
    from api.src.services.billing_service import extend_active_subscriptions

    activated = datetime.now(UTC) - timedelta(hours=1)
    deactivated = datetime.now(UTC)
    ks = _make_killswitch_state(activated_at=activated, deactivated_at=deactivated)

    sub_a = _make_subscription(sub_id=301, user_id=10, status="active")  # 이미 처리됨
    sub_b = _make_subscription(sub_id=302, user_id=11, status="active")  # 미처리

    existing_audit = MagicMock(spec=AuditLog)

    db = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()

    # 2026-05-18 — 알림톡 발송 폐지로 user SELECT 단계 제거.
    # execute 순서:
    # 1. SELECT killswitch
    # 2. SELECT targets (2건)
    # 3. SELECT FOR UPDATE sub_a → idempotency hit → skip
    # 4. SELECT AuditLog for sub_a → existing
    # 5. SELECT FOR UPDATE sub_b → pass
    # 6. SELECT AuditLog for sub_b → None (미처리)
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result(ks),
            _scalars_result([sub_a, sub_b]),
            _scalar_result(sub_a),
            _scalar_result(existing_audit),   # sub_a 이미 처리됨
            _scalar_result(sub_b),
            _scalar_result(None),             # sub_b 미처리
        ]
    )

    result = await extend_active_subscriptions(killswitch_state_id=42, db=db)

    assert result["status"] == "ok"
    assert result["extended_count"] == 1  # sub_b만 연장
    # AuditLog는 sub_b에 대해서만 1건 추가
    audit_rows = [a for a in db.add.call_args_list if isinstance(a[0][0], AuditLog)]
    assert len(audit_rows) == 1
