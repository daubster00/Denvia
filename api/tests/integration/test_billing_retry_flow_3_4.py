"""빌링 재시도 통합 테스트 — Story 3.4.

retry_payment end-to-end + 최종 실패 cancel_pending 전환 + revoke-on-card-change.
모든 외부 의존성(TossAdapter, Redis, Celery)은 mock으로 대체.
"""

import os
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet


@pytest.fixture(autouse=True)
def _set_enc_key(monkeypatch):
    """Fernet 키 주입."""
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("BILLING_KEY_ENC_KEY", key)


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _make_payment(
    payment_id: int = 100,
    user_id: int = 10,
    subscription_id: int | None = 50,
    status: str = "failed",
    attempt_count: int = 1,
) -> MagicMock:
    p = MagicMock()
    p.id = payment_id
    p.user_id = user_id
    p.subscription_id = subscription_id
    p.status = status
    p.attempt_count = attempt_count
    p.retry_task_id = None
    p.failure_reason = "first failure"
    p.provider_order_id = "renewal-50-orig"
    return p


def _make_subscription(sub_id: int = 50, user_id: int = 10) -> MagicMock:
    sub = MagicMock()
    sub.id = sub_id
    sub.user_id = user_id
    sub.status = "active"
    now = _now_utc()
    sub.current_period_end = now - timedelta(days=1)
    sub.next_charge_at = now - timedelta(days=1)
    sub.canceled_at = None
    sub.cancel_reason = None
    sub.current_session_id = None
    sub.admin_grade = "master"
    return sub


def _make_billing_key(user_id: int = 10) -> MagicMock:
    from api.src.utils.fernet import encrypt_billing_key

    bk = MagicMock()
    bk.id = 20
    bk.user_id = user_id
    bk.customer_key = "cust_3_4_e2e"
    bk.billing_key_encrypted = encrypt_billing_key("plain_3_4")
    bk.is_active = True
    bk.current_session_id = None
    bk.admin_grade = "master"
    return bk


def _scalar_result(obj) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none = MagicMock(return_value=obj)
    return r


def _scalars_result(objs: list) -> MagicMock:
    r = MagicMock()
    r.scalars.return_value.all.return_value = objs
    return r


# ── retry_payment end-to-end ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retry_payment_e2e_success_db_state():
    """attempt=2 성공: payment + subscriptions 30일 연장 + 알림 호출 검증."""
    from api.src.models.payment_event import PaymentEvent
    from api.src.services.billing_service import retry_payment

    payment = _make_payment()
    sub = _make_subscription()
    original_period_end = sub.current_period_end
    bk = _make_billing_key()

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result(payment),
            _scalar_result(None),  # killswitch
            _scalar_result(sub),
            _scalar_result(bk),
        ]
    )
    db.commit = AsyncMock()
    added: list = []
    db.add = MagicMock(side_effect=lambda o: added.append(o))

    mock_pg = AsyncMock()
    mock_pg.charge = AsyncMock(
        return_value={
            "success": True,
            "provider_order_id": "retry-100-2",
            "failure_reason": None,
            "raw_response": {"status": "DONE"},
        }
    )

    with patch("api.src.services.billing_service.get_pg_provider", return_value=mock_pg):
        with patch("api.src.services.billing_service._notify_retry", new=AsyncMock()):
            result = await retry_payment(payment.id, 2, db)

    assert result["status"] == "success"
    assert payment.status == "success"
    assert payment.attempt_count == 2
    assert payment.provider_order_id == "retry-100-2"
    assert sub.current_period_end == original_period_end + timedelta(days=30)
    events = [o for o in added if isinstance(o, PaymentEvent)]
    assert any(e.event_type == "charge_success" for e in events)


@pytest.mark.asyncio
async def test_retry_payment_e2e_final_failure_cancel_pending():
    """attempt=4 최종 실패 → subscriptions.status='cancel_pending' 전환."""
    from api.src.services.billing_service import retry_payment

    payment = _make_payment(attempt_count=3)
    sub = _make_subscription()
    bk = _make_billing_key()

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result(payment),
            _scalar_result(None),
            _scalar_result(sub),
            _scalar_result(bk),
        ]
    )
    db.commit = AsyncMock()
    db.add = MagicMock()

    mock_pg = AsyncMock()
    mock_pg.charge = AsyncMock(
        return_value={
            "success": False,
            "provider_order_id": "retry-100-4",
            "failure_reason": "카드 한도 초과",
            "raw_response": {"code": "EXCEED_MAX_AMOUNT"},
        }
    )

    with patch("api.src.workers.celery_app.celery_app") as mock_celery_app:
        with patch(
            "api.src.services.billing_service.get_pg_provider", return_value=mock_pg
        ):
            with patch("api.src.services.billing_service._notify_retry", new=AsyncMock()):
                with patch("sentry_sdk.add_breadcrumb"):
                    result = await retry_payment(payment.id, 4, db)

    assert result["status"] == "failed"
    assert sub.status == "cancel_pending"
    assert sub.cancel_reason == "payment_retry_exhausted"
    assert sub.canceled_at is not None
    # 더 이상 재예약 안 함
    mock_celery_app.send_task.assert_not_called()


@pytest.mark.asyncio
async def test_retry_payment_e2e_intermediate_failure_schedules_next():
    """attempt=2 실패 → send_task(args=[payment_id, 3], countdown=259200) 호출."""
    from api.src.services.billing_service import retry_payment

    payment = _make_payment()
    sub = _make_subscription()
    bk = _make_billing_key()

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result(payment),
            _scalar_result(None),
            _scalar_result(sub),
            _scalar_result(bk),
        ]
    )
    db.commit = AsyncMock()
    db.add = MagicMock()

    mock_pg = AsyncMock()
    mock_pg.charge = AsyncMock(
        return_value={
            "success": False,
            "provider_order_id": "retry-100-2",
            "failure_reason": "카드 거절",
            "raw_response": {"code": "DECLINE"},
        }
    )

    fake_task = MagicMock()
    fake_task.id = "next-attempt-task"

    with patch("api.src.workers.celery_app.celery_app") as mock_celery_app:
        mock_celery_app.send_task = MagicMock(return_value=fake_task)
        with patch(
            "api.src.services.billing_service.get_pg_provider", return_value=mock_pg
        ):
            with patch("api.src.services.billing_service._notify_retry", new=AsyncMock()):
                with patch("sentry_sdk.add_breadcrumb"):
                    await retry_payment(payment.id, 2, db)

    mock_celery_app.send_task.assert_called_once_with(
        "billing.retry_payment",
        args=[payment.id, 3],
        countdown=259200,
    )
    assert payment.retry_task_id == "next-attempt-task"


# ── issue_billing_key revoke-on-card-change ─────────────────────────────────


@pytest.mark.asyncio
async def test_issue_billing_key_revoke_clears_retry_task_ids():
    """카드 변경 시 retry_task_id가 있는 failed payments에 revoke 호출 + retry_task_id=None."""
    from api.src.models.payment import Payment
    from api.src.services.billing_service import issue_billing_key

    user = MagicMock()
    user.id = 1
    user.phone = "01012345678"

    fp = MagicMock(spec=Payment)
    fp.id = 11
    fp.user_id = 1
    fp.status = "failed"
    fp.retry_task_id = "scheduled-task-zzz"

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(
        side_effect=[
            _scalars_result([]),  # 기존 활성 빌링키 없음
            _scalars_result([fp]),  # pending retries
        ]
    )

    async def fake_refresh(obj):
        obj.id = 99
        obj.card_last4 = "5678"
        obj.card_company = "현대"

    mock_db.refresh = fake_refresh

    mock_pg = AsyncMock()
    mock_pg.issue_billing_key = AsyncMock(
        return_value={
            "billing_key": "new_bk",
            "card_last4": "5678",
            "card_company": "현대",
        }
    )

    with patch("api.src.workers.celery_app.celery_app") as mock_celery_app:
        with patch(
            "api.src.services.billing_service.get_pg_provider", return_value=mock_pg
        ):
            await issue_billing_key(
                user=user,
                pg_token="t",
                customer_key="c",
                db=mock_db,
            )

    mock_celery_app.control.revoke.assert_called_once_with(
        "scheduled-task-zzz", terminate=True
    )
    assert fp.retry_task_id is None


# ── Migration 0015 ───────────────────────────────────────────────────────────


DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://denvia:password@localhost:5432/denvia",
)
DB_SYNC_URL = os.environ.get(
    "DATABASE_SYNC_URL",
    "postgresql+psycopg://denvia:password@localhost:5432/denvia",
)


@pytest.fixture(scope="module")
def run_migrations():
    """alembic upgrade head를 실행한다."""
    from alembic.config import Config

    from alembic import command

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", DB_SYNC_URL)
    command.upgrade(alembic_cfg, "head")
    yield
    command.downgrade(alembic_cfg, "base")


@pytest.mark.asyncio
async def test_payments_retry_task_id_column_exists(run_migrations):
    """payments.retry_task_id 컬럼이 존재해야 한다."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT column_name, is_nullable, data_type "
                "FROM information_schema.columns "
                "WHERE table_name='payments' AND column_name='retry_task_id'"
            )
        )
        row = result.fetchone()
    await engine.dispose()
    assert row is not None, "payments.retry_task_id 컬럼이 존재해야 함"
    assert row[1] == "YES", "retry_task_id는 nullable이어야 함"
