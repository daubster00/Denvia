"""빌링 자동 갱신 통합 테스트 — Story 3.3.

scan_renewals end-to-end + charge_renewal DB 상태 + Beat 스케줄 등록 확인.
모든 외부 의존성(TossAdapter, Redis, Celery)은 mock으로 대체.
"""

import os
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from cryptography.fernet import Fernet


@pytest.fixture(autouse=True)
def _set_enc_key(monkeypatch):
    """Fernet 키 주입."""
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("BILLING_KEY_ENC_KEY", key)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _make_subscription(sub_id: int = 1, user_id: int = 10, status: str = "active") -> MagicMock:
    sub = MagicMock()
    sub.id = sub_id
    sub.user_id = user_id
    sub.status = status
    now = _now_utc()
    sub.current_period_end = now - timedelta(days=1)
    sub.next_charge_at = now - timedelta(days=1)
    sub.current_session_id = None
    sub.admin_grade = "master"
    return sub


def _make_billing_key(user_id: int = 10) -> MagicMock:
    from api.src.utils.fernet import encrypt_billing_key

    bk = MagicMock()
    bk.id = 20
    bk.user_id = user_id
    bk.customer_key = "denvia_cust_test_uuid"
    bk.billing_key_encrypted = encrypt_billing_key("bk_plain_test")
    bk.is_active = True
    bk.current_session_id = None
    bk.admin_grade = "master"
    return bk


def _scalars_result(objs: list) -> MagicMock:
    r = MagicMock()
    r.scalars.return_value.all.return_value = objs
    return r


def _scalar_result(obj) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none = MagicMock(return_value=obj)
    return r


# ── scan_renewals end-to-end ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scan_renewals_e2e_enqueues_active_only():
    """active 구독 있을 때 charge_renewal send_task 호출 확인."""
    from api.src.services.billing_service import scan_renewals

    sub = _make_subscription()
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalars_result([sub]))

    # 함수 내부 from import 이므로 모듈 네임스페이스 patch
    with patch("api.src.workers.celery_app.celery_app") as mock_celery_app:
        result = await scan_renewals(db)

    assert result["enqueued"] == 1
    mock_celery_app.send_task.assert_called_once_with(
        "billing.charge_renewal", args=[sub.id]
    )


# ── charge_renewal end-to-end (성공) ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_charge_renewal_e2e_success_db_state():
    """성공 경로: Payment INSERT(status='success') + subscriptions 30일 연장 검증."""
    from api.src.services.billing_service import charge_renewal
    from api.src.models.payment import Payment
    from api.src.models.payment_event import PaymentEvent

    sub = _make_subscription()
    original_period_end = sub.current_period_end
    bk = _make_billing_key()

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_scalar_result(sub), _scalar_result(bk)])

    added: list = []
    db.add = MagicMock(side_effect=lambda o: added.append(o))

    mock_pg = AsyncMock()
    mock_pg.charge = AsyncMock(return_value={
        "success": True,
        "provider_order_id": "renewal-1-abcdef123456",
        "failure_reason": None,
        "raw_response": {"status": "DONE"},
    })

    with patch("api.src.services.billing_service.get_pg_provider", return_value=mock_pg):
        with patch("api.src.services.billing_service._notify_renewal", new=AsyncMock()):
            result = await charge_renewal(sub.id, db)

    assert result["status"] == "success"

    payments = [o for o in added if isinstance(o, Payment)]
    assert len(payments) == 1
    assert payments[0].status == "success"

    # 구독 30일 연장
    assert sub.current_period_end == original_period_end + timedelta(days=30)
    assert sub.next_charge_at == sub.current_period_end


# ── charge_renewal end-to-end (실패) ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_charge_renewal_e2e_failure_db_state():
    """실패 경로: payments.status='failed' + retry_scheduled event + send_task 확인."""
    from api.src.services.billing_service import charge_renewal
    from api.src.models.payment import Payment
    from api.src.models.payment_event import PaymentEvent

    sub = _make_subscription()
    bk = _make_billing_key()

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_scalar_result(sub), _scalar_result(bk)])

    added: list = []

    def _cap_add(o):
        from api.src.models.payment import Payment as P
        if isinstance(o, P):
            o.id = 777
        added.append(o)

    db.add = MagicMock(side_effect=_cap_add)

    mock_pg = AsyncMock()
    mock_pg.charge = AsyncMock(return_value={
        "success": False,
        "provider_order_id": "renewal-1-fail123",
        "failure_reason": "카드 정지",
        "raw_response": {"code": "CARD_SUSPENDED"},
    })

    with patch("api.src.services.billing_service.get_pg_provider", return_value=mock_pg):
        with patch("api.src.workers.celery_app.celery_app") as mock_celery_app:
            with patch("sentry_sdk.add_breadcrumb"):
                result = await charge_renewal(sub.id, db)

    assert result["status"] == "failed"

    payments = [o for o in added if isinstance(o, Payment)]
    assert len(payments) == 1
    assert payments[0].status == "failed"

    events = [o for o in added if isinstance(o, PaymentEvent)]
    event_types = {e.event_type for e in events}
    assert "charge_failed" in event_types
    assert "retry_scheduled" in event_types

    mock_celery_app.send_task.assert_called_once_with(
        "billing.retry_payment",
        args=[result["payment_id"]],
        countdown=86400,
    )


# ── Beat schedule 등록 확인 ───────────────────────────────────────────────────


def test_beat_schedule_has_auto_renew_scan():
    """celery_app.conf.beat_schedule에 'auto-renew-scan-daily-0400' 항목 존재 확인."""
    from api.src.workers.celery_app import celery_app

    schedule = celery_app.conf.beat_schedule
    assert "auto-renew-scan-daily-0400" in schedule, (
        "beat_schedule에 'auto-renew-scan-daily-0400'가 없습니다."
    )
    entry = schedule["auto-renew-scan-daily-0400"]
    assert entry["task"] == "billing.auto_renew_scan"


def test_beat_schedule_auto_renew_crontab_hour():
    """auto-renew-scan-daily-0400 스케줄이 hour=4 crontab인지 확인."""
    from api.src.workers.celery_app import celery_app
    from celery.schedules import crontab

    entry = celery_app.conf.beat_schedule["auto-renew-scan-daily-0400"]
    schedule = entry["schedule"]
    assert isinstance(schedule, crontab), "schedule은 crontab 인스턴스여야 합니다."
    # crontab(hour=4, minute=0) 검증
    assert schedule.hour == {4}, f"hour이 4여야 하는데 {schedule.hour}입니다."
    assert schedule.minute == {0}, f"minute이 0이어야 하는데 {schedule.minute}입니다."


# ── billing_tasks include 등록 확인 ─────────────────────────────────────────


def test_billing_tasks_in_celery_include():
    """celery_app include 목록에 billing_tasks 모듈이 등록되어 있는지 확인."""
    from api.src.workers.celery_app import celery_app

    assert "api.src.workers.billing_tasks" in celery_app.conf.include, (
        "billing_tasks 모듈이 celery_app include에 없습니다."
    )
