"""Story 9.2 — billing_service.retry_payment의 manual_total kill-switch 분기 회귀.

Story 3.4에서 이미 구현된 동작을 본 스토리에서 코드 변경 0줄로 회귀 검증한다:
1. manual_total 활성 → return deferred + payment_events.retry_scheduled INSERT + attempt_count 비증가
2. auto_free_only만 활성 → 결제 재시도 정상 진행 (kill-switch 분기 미트리거)
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet


@pytest.fixture(autouse=True)
def _set_enc_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("BILLING_KEY_ENC_KEY", key)


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _make_payment(payment_id: int = 200, attempt_count: int = 1) -> MagicMock:
    p = MagicMock()
    p.id = payment_id
    p.user_id = 10
    p.subscription_id = 60
    p.status = "failed"
    p.attempt_count = attempt_count
    p.retry_task_id = None
    p.failure_reason = "first failure"
    p.provider_order_id = "renewal-60-orig"
    p.current_session_id = None
    p.admin_grade = "master"
    return p


def _make_subscription(sub_id: int = 60) -> MagicMock:
    sub = MagicMock()
    sub.id = sub_id
    sub.user_id = 10
    sub.status = "active"
    now = _now_utc()
    sub.current_period_end = now - timedelta(days=1)
    sub.next_charge_at = now - timedelta(days=1)
    sub.canceled_at = None
    sub.cancel_reason = None
    sub.current_session_id = None
    sub.admin_grade = "master"
    return sub


def _make_billing_key():
    from api.src.utils.fernet import encrypt_billing_key

    bk = MagicMock()
    bk.id = 30
    bk.user_id = 10
    bk.customer_key = "cust_kill"
    bk.billing_key_encrypted = encrypt_billing_key("plain_kill")
    bk.is_active = True
    bk.current_session_id = None
    bk.admin_grade = "master"
    return bk


def _scalar_result(obj):
    r = MagicMock()
    r.scalar_one_or_none = MagicMock(return_value=obj)
    return r


@pytest.mark.asyncio
async def test_retry_payment_deferred_when_manual_total_active():
    """manual_total 활성 → deferred + retry_scheduled 이벤트 + attempt_count 비증가."""
    from api.src.models.payment_event import PaymentEvent
    from api.src.services.billing_service import retry_payment

    payment = _make_payment(attempt_count=1)
    active_killswitch = MagicMock()
    active_killswitch.id = 99
    active_killswitch.mode = "manual_total"

    db = AsyncMock()
    # 순서: SELECT payment, SELECT killswitch (active manual_total)
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result(payment),
            _scalar_result(active_killswitch),
        ]
    )
    db.commit = AsyncMock()
    added: list = []
    db.add = MagicMock(side_effect=lambda o: added.append(o))

    fake_task = MagicMock()
    fake_task.id = "killswitch-deferred-task-id"

    with patch("api.src.workers.celery_app.celery_app") as mock_celery_app:
        mock_celery_app.send_task = MagicMock(return_value=fake_task)
        result = await retry_payment(payment.id, 2, db)

    assert result["status"] == "deferred"
    assert result["reason"] == "kill_switch_active"
    assert result["task_id"] == "killswitch-deferred-task-id"
    # attempt_count 비증가
    assert payment.attempt_count == 1
    # PaymentEvent retry_scheduled INSERT
    events = [o for o in added if isinstance(o, PaymentEvent)]
    assert len(events) == 1
    assert events[0].event_type == "retry_scheduled"
    raw = events[0].raw_response_json
    assert raw["reason"] == "kill_switch_active"
    assert raw["task_id"] == "killswitch-deferred-task-id"
    assert raw["countdown_sec"] == 3600
    # PG 호출 안 함
    mock_celery_app.send_task.assert_called_once()
    args, kwargs = mock_celery_app.send_task.call_args
    assert args[0] == "billing.retry_payment"
    assert kwargs["countdown"] == 3600


@pytest.mark.asyncio
async def test_retry_payment_proceeds_when_only_auto_free_only_active():
    """auto_free_only만 활성 → kill-switch 분기 미트리거 (기존 PG 호출 진행)."""
    from api.src.services.billing_service import retry_payment

    payment = _make_payment(attempt_count=1)
    sub = _make_subscription()
    bk = _make_billing_key()

    db = AsyncMock()
    # 순서: SELECT payment, SELECT killswitch (None — manual_total 미활성),
    # SELECT subscription, SELECT billing_key
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result(payment),
            _scalar_result(None),  # manual_total 없음
            _scalar_result(sub),
            _scalar_result(bk),
        ]
    )
    db.commit = AsyncMock()
    db.add = MagicMock()

    mock_pg = AsyncMock()
    mock_pg.charge = AsyncMock(
        return_value={
            "success": True,
            "provider_order_id": "retry-200-2",
            "failure_reason": None,
            "raw_response": {"status": "DONE"},
        }
    )

    with patch(
        "api.src.services.billing_service.get_pg_provider", return_value=mock_pg
    ), patch("api.src.services.billing_service._notify_retry", new=AsyncMock()):
        result = await retry_payment(payment.id, 2, db)

    # PG 호출이 진행되어 success 결과
    assert result["status"] == "success"
    assert payment.attempt_count == 2
    mock_pg.charge.assert_awaited_once()
