"""BillingService 단위 테스트 — Story 3.4 결제 실패 재시도.

retry_payment 분기 + 멱등성 + kill-switch + revoke-on-card-change 검증.
"""

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
    retry_task_id: str | None = None,
) -> MagicMock:
    p = MagicMock()
    p.id = payment_id
    p.user_id = user_id
    p.subscription_id = subscription_id
    p.status = status
    p.attempt_count = attempt_count
    p.retry_task_id = retry_task_id
    p.failure_reason = "이전 실패 사유"
    p.provider_order_id = "renewal-50-orig"
    p.charged_at = _now_utc() - timedelta(days=1)
    return p


def _make_subscription(
    sub_id: int = 50,
    user_id: int = 10,
    status: str = "active",
) -> MagicMock:
    sub = MagicMock()
    sub.id = sub_id
    sub.user_id = user_id
    sub.status = status
    now = _now_utc()
    sub.current_period_end = now - timedelta(days=1)
    sub.next_charge_at = now - timedelta(days=1)
    sub.canceled_at = None
    sub.cancel_reason = None
    return sub


def _make_billing_key(user_id: int = 10) -> MagicMock:
    from api.src.utils.fernet import encrypt_billing_key

    bk = MagicMock()
    bk.id = 20
    bk.user_id = user_id
    bk.customer_key = "denvia_cust_uuid_3_4"
    bk.billing_key_encrypted = encrypt_billing_key("test_billing_key_plain")
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


def _make_charge_result(success: bool) -> dict:
    if success:
        return {
            "success": True,
            "provider_order_id": "retry-100-2",
            "failure_reason": None,
            "raw_response": {"status": "DONE"},
        }
    return {
        "success": False,
        "provider_order_id": "retry-100-2",
        "failure_reason": "카드 잔액 부족",
        "raw_response": {"code": "INSUFFICIENT_FUNDS"},
    }


def _retry_db_executes(payment, killswitch=None, sub=None, bk=None) -> AsyncMock:
    """retry_payment 4단계 execute(payment / killswitch / subscription / billing_key) mock."""
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result(payment),
            _scalar_result(killswitch),
            _scalar_result(sub),
            _scalar_result(bk),
        ]
    )
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


# ── 멱등성 / 가드 케이스 ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retry_payment_payment_not_found_returns_error():
    """payment 없음 → status='error', reason='payment_not_found'."""
    from api.src.services.billing_service import retry_payment

    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalar_result(None))

    result = await retry_payment(999, 2, db)

    assert result == {"status": "error", "reason": "payment_not_found"}


@pytest.mark.asyncio
async def test_retry_payment_already_success_no_op():
    """payment.status='success' → no-op (멱등성, kill-switch보다 먼저 체크)."""
    from api.src.services.billing_service import retry_payment

    payment = _make_payment(status="success")
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalar_result(payment))

    mock_pg = AsyncMock()
    with patch("api.src.services.billing_service.get_pg_provider", return_value=mock_pg):
        result = await retry_payment(payment.id, 2, db)

    assert result == {"status": "no-op", "reason": "already_success"}
    mock_pg.charge.assert_not_called()


@pytest.mark.asyncio
async def test_retry_payment_duplicate_attempt_no_op():
    """payment.attempt_count >= attempt → PG 미호출 + no-op (중복 attempt 방어)."""
    from api.src.services.billing_service import retry_payment

    payment = _make_payment(status="failed", attempt_count=2)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalar_result(payment))

    mock_pg = AsyncMock()
    with patch("api.src.services.billing_service.get_pg_provider", return_value=mock_pg):
        result = await retry_payment(payment.id, 2, db)

    assert result == {"status": "no-op", "reason": "duplicate_attempt"}
    mock_pg.charge.assert_not_called()


@pytest.mark.asyncio
async def test_retry_payment_invalid_attempt_returns_error():
    """attempt < 2 또는 > 4 → invalid_attempt 반환, DB 조회 미수행."""
    from api.src.services.billing_service import retry_payment

    db = AsyncMock()
    result_low = await retry_payment(100, 1, db)
    result_high = await retry_payment(100, 5, db)

    assert result_low == {"status": "error", "reason": "invalid_attempt"}
    assert result_high == {"status": "error", "reason": "invalid_attempt"}
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_retry_payment_kill_switch_manual_total_reschedules():
    """kill-switch manual_total 활성 → PG 미호출 + 동일 attempt 재예약 + retry_task_id 갱신.

    attempt_count는 증가시키지 않고, retry_scheduled 이벤트에 reason='kill_switch_active'를 남긴다.
    """
    from api.src.models.killswitch_state import KillswitchState
    from api.src.models.payment_event import PaymentEvent
    from api.src.services.billing_service import retry_payment

    payment = _make_payment(attempt_count=1, retry_task_id="prev-task")
    ks = MagicMock(spec=KillswitchState)
    ks.mode = "manual_total"
    ks.deactivated_at = None

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[_scalar_result(payment), _scalar_result(ks)]
    )
    db.commit = AsyncMock()
    added: list = []
    db.add = MagicMock(side_effect=lambda o: added.append(o))

    fake_task = MagicMock()
    fake_task.id = "ks-rescheduled-task"

    mock_pg = AsyncMock()
    with patch("api.src.workers.celery_app.celery_app") as mock_celery_app:
        mock_celery_app.send_task = MagicMock(return_value=fake_task)
        with patch(
            "api.src.services.billing_service.get_pg_provider", return_value=mock_pg
        ):
            result = await retry_payment(payment.id, 2, db)

    # PG는 호출되지 않는다
    mock_pg.charge.assert_not_called()

    # 동일 attempt(=2)로 재예약
    mock_celery_app.send_task.assert_called_once_with(
        "billing.retry_payment",
        args=[payment.id, 2],
        countdown=3600,
    )

    # retry_task_id 갱신
    assert payment.retry_task_id == "ks-rescheduled-task"

    # attempt_count는 증가하지 않음(실제 PG 시도가 아님)
    assert payment.attempt_count == 1

    # retry_scheduled + reason=kill_switch_active 이벤트 기록
    events = [o for o in added if isinstance(o, PaymentEvent)]
    assert len(events) == 1
    assert events[0].event_type == "retry_scheduled"
    assert events[0].raw_response_json["reason"] == "kill_switch_active"
    assert events[0].raw_response_json["attempt"] == 2
    assert events[0].raw_response_json["countdown_sec"] == 3600
    assert events[0].raw_response_json["task_id"] == "ks-rescheduled-task"

    # 응답 페이로드
    assert result == {
        "status": "deferred",
        "reason": "kill_switch_active",
        "task_id": "ks-rescheduled-task",
    }
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_retry_payment_kill_switch_auto_free_only_proceeds():
    """auto_free_only 모드는 결제 재시도에 영향 없음 — 정상 진행 (manual_total 쿼리 None)."""
    from api.src.services.billing_service import retry_payment

    payment = _make_payment()
    sub = _make_subscription()
    bk = _make_billing_key()
    db = _retry_db_executes(payment=payment, killswitch=None, sub=sub, bk=bk)

    mock_pg = AsyncMock()
    mock_pg.charge = AsyncMock(return_value=_make_charge_result(True))

    with patch("api.src.services.billing_service.get_pg_provider", return_value=mock_pg):
        with patch("api.src.services.billing_service._notify_retry", new=AsyncMock()):
            result = await retry_payment(payment.id, 2, db)

    assert result["status"] == "success"
    mock_pg.charge.assert_called_once()


@pytest.mark.asyncio
async def test_retry_payment_no_active_billing_key_returns_error():
    """활성 빌링키 없음 → status='error', reason='no_active_billing_key'."""
    from api.src.services.billing_service import retry_payment

    payment = _make_payment()
    sub = _make_subscription()
    db = _retry_db_executes(payment=payment, killswitch=None, sub=sub, bk=None)

    result = await retry_payment(payment.id, 2, db)
    assert result == {"status": "error", "reason": "no_active_billing_key"}


@pytest.mark.asyncio
async def test_retry_payment_no_subscription_id_returns_error():
    """payment.subscription_id가 None이면 → no_subscription_id 에러."""
    from api.src.services.billing_service import retry_payment

    payment = _make_payment(subscription_id=None)
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[_scalar_result(payment), _scalar_result(None)]
    )

    result = await retry_payment(payment.id, 2, db)
    assert result == {"status": "error", "reason": "no_subscription_id"}


# ── 성공 경로 ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retry_payment_attempt2_success():
    """attempt=2 성공: payment 갱신 + 30일 연장 (재시도 성공 알림은 v4 검수에서 폐지)."""
    from api.src.models.payment_event import PaymentEvent
    from api.src.services.billing_service import retry_payment

    payment = _make_payment()
    sub = _make_subscription()
    original_period_end = sub.current_period_end
    bk = _make_billing_key()

    db = _retry_db_executes(payment=payment, killswitch=None, sub=sub, bk=bk)
    added_objects: list = []
    db.add = MagicMock(side_effect=lambda o: added_objects.append(o))

    mock_pg = AsyncMock()
    mock_pg.charge = AsyncMock(return_value=_make_charge_result(True))

    # 2026-05-18 v4 — 재시도 성공 알림(billing.retry_success, 1-3) 폐지.
    # 알림 호출은 더 이상 일어나지 않지만 mock을 걸어 회귀 가드.
    mock_notify = AsyncMock()
    with patch("api.src.services.billing_service.get_pg_provider", return_value=mock_pg):
        with patch("api.src.services.billing_service._notify_retry", mock_notify):
            result = await retry_payment(payment.id, 2, db)

    assert result["status"] == "success"
    assert result["payment_id"] == payment.id
    assert result["attempt"] == 2

    # Payment 상태 갱신 확인
    assert payment.status == "success"
    assert payment.attempt_count == 2
    assert payment.provider_order_id == f"retry-{payment.id}-2"
    assert payment.failure_reason is None
    assert payment.retry_task_id is None  # 성공했으므로 revoke 불필요

    # 구독 30일 연장
    assert sub.current_period_end == original_period_end + timedelta(days=30)
    assert sub.next_charge_at == sub.current_period_end

    # charge_success 이벤트 추가 확인
    events = [o for o in added_objects if isinstance(o, PaymentEvent)]
    assert any(e.event_type == "charge_success" for e in events)

    # retry_success 알림 — v4 검수에서 폐기 → 호출되지 않아야 함
    mock_notify.assert_not_called()


@pytest.mark.asyncio
async def test_retry_payment_uses_deterministic_order_id():
    """order_id가 결정적 키 `retry-{payment_id}-{attempt}` 형식인지 확인 (토스 허용 문자)."""
    from api.src.services.billing_service import retry_payment

    payment = _make_payment(payment_id=777)
    sub = _make_subscription()
    bk = _make_billing_key()
    db = _retry_db_executes(payment=payment, killswitch=None, sub=sub, bk=bk)

    mock_pg = AsyncMock()
    mock_pg.charge = AsyncMock(return_value=_make_charge_result(True))

    with patch("api.src.services.billing_service.get_pg_provider", return_value=mock_pg):
        with patch("api.src.services.billing_service._notify_retry", new=AsyncMock()):
            await retry_payment(777, 3, db)

    call_args = mock_pg.charge.call_args
    # charge(billing_key_plain, customer_key, amount, order_id)
    order_id_arg = call_args.args[3]
    assert order_id_arg == "retry-777-3"


# ── 실패 경로 ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retry_payment_attempt2_failure_schedules_attempt3():
    """attempt=2 실패: charge_failed + retry_scheduled + send_task(countdown=259200, attempt=3)."""
    from api.src.models.payment_event import PaymentEvent
    from api.src.services.billing_service import retry_payment

    payment = _make_payment()
    sub = _make_subscription()
    bk = _make_billing_key()
    db = _retry_db_executes(payment=payment, killswitch=None, sub=sub, bk=bk)
    added_objects: list = []
    db.add = MagicMock(side_effect=lambda o: added_objects.append(o))

    mock_pg = AsyncMock()
    mock_pg.charge = AsyncMock(return_value=_make_charge_result(False))

    fake_task = MagicMock()
    fake_task.id = "task-id-xyz-3"

    mock_notify = AsyncMock()
    with patch("api.src.workers.celery_app.celery_app") as mock_celery_app:
        mock_celery_app.send_task = MagicMock(return_value=fake_task)
        with patch(
            "api.src.services.billing_service.get_pg_provider", return_value=mock_pg
        ):
            with patch("api.src.services.billing_service._notify_retry", mock_notify):
                with patch("sentry_sdk.add_breadcrumb"):
                    result = await retry_payment(payment.id, 2, db)

    assert result["status"] == "failed"
    assert payment.attempt_count == 2
    assert payment.provider_order_id == f"retry-{payment.id}-2"
    assert payment.retry_task_id == "task-id-xyz-3"

    # 이벤트 확인
    events = [o for o in added_objects if isinstance(o, PaymentEvent)]
    types = {e.event_type for e in events}
    assert "charge_failed" in types
    assert "retry_scheduled" in types

    # send_task 호출 — countdown=259200, attempt=3
    mock_celery_app.send_task.assert_called_once_with(
        "billing.retry_payment",
        args=[payment.id, 3],
        countdown=259200,
    )

    # 알림 retry_failed_1
    assert mock_notify.call_args.kwargs["template_code"] == "billing.retry_failed_1"


@pytest.mark.asyncio
async def test_retry_payment_attempt3_failure_schedules_attempt4():
    """attempt=3 실패: send_task(countdown=259200, attempt=4) + retry_failed_2 알림."""
    from api.src.services.billing_service import retry_payment

    payment = _make_payment(attempt_count=2)
    sub = _make_subscription()
    bk = _make_billing_key()
    db = _retry_db_executes(payment=payment, killswitch=None, sub=sub, bk=bk)

    mock_pg = AsyncMock()
    mock_pg.charge = AsyncMock(return_value=_make_charge_result(False))

    fake_task = MagicMock()
    fake_task.id = "task-id-attempt-4"

    mock_notify = AsyncMock()
    with patch("api.src.workers.celery_app.celery_app") as mock_celery_app:
        mock_celery_app.send_task = MagicMock(return_value=fake_task)
        with patch(
            "api.src.services.billing_service.get_pg_provider", return_value=mock_pg
        ):
            with patch("api.src.services.billing_service._notify_retry", mock_notify):
                with patch("sentry_sdk.add_breadcrumb"):
                    result = await retry_payment(payment.id, 3, db)

    assert result["status"] == "failed"
    assert payment.attempt_count == 3
    assert payment.retry_task_id == "task-id-attempt-4"

    mock_celery_app.send_task.assert_called_once_with(
        "billing.retry_payment",
        args=[payment.id, 4],
        countdown=259200,
    )
    assert mock_notify.call_args.kwargs["template_code"] == "billing.retry_failed_2"


@pytest.mark.asyncio
async def test_retry_payment_attempt4_final_failure_cancel_pending():
    """attempt=4 최종 실패: send_task 미호출 + cancel_pending 전환 + retry_failed_3 알림."""
    from api.src.services.billing_service import retry_payment

    payment = _make_payment(attempt_count=3, retry_task_id="prev-task-id")
    sub = _make_subscription()
    bk = _make_billing_key()
    db = _retry_db_executes(payment=payment, killswitch=None, sub=sub, bk=bk)

    mock_pg = AsyncMock()
    mock_pg.charge = AsyncMock(return_value=_make_charge_result(False))

    mock_notify = AsyncMock()
    with patch("api.src.workers.celery_app.celery_app") as mock_celery_app:
        mock_celery_app.send_task = MagicMock()
        with patch(
            "api.src.services.billing_service.get_pg_provider", return_value=mock_pg
        ):
            with patch("api.src.services.billing_service._notify_retry", mock_notify):
                with patch("sentry_sdk.add_breadcrumb"):
                    result = await retry_payment(payment.id, 4, db)

    assert result["status"] == "failed"

    # 더 이상 재예약하지 않음
    mock_celery_app.send_task.assert_not_called()

    # cancel_pending 전환
    assert sub.status == "cancel_pending"
    assert sub.cancel_reason == "payment_retry_exhausted"
    assert sub.canceled_at is not None

    # payment 상태
    assert payment.attempt_count == 4
    assert payment.retry_task_id is None  # 최종 실패 시 None

    # users.subscription_status는 변경되지 않음 — Story 3.5 책임 (retry_payment는 User update 호출 안 함)

    assert mock_notify.call_args.kwargs["template_code"] == "billing.retry_failed_3"


@pytest.mark.asyncio
async def test_retry_payment_billing_key_plain_not_logged():
    """billing_key_plain이 로그에 노출되지 않는다."""
    import structlog.testing

    from api.src.services.billing_service import retry_payment

    payment = _make_payment()
    sub = _make_subscription()
    bk = _make_billing_key()
    db = _retry_db_executes(payment=payment, killswitch=None, sub=sub, bk=bk)

    mock_pg = AsyncMock()
    mock_pg.charge = AsyncMock(return_value=_make_charge_result(True))

    with structlog.testing.capture_logs() as captured:
        with patch(
            "api.src.services.billing_service.get_pg_provider", return_value=mock_pg
        ):
            with patch("api.src.services.billing_service._notify_retry", new=AsyncMock()):
                await retry_payment(payment.id, 2, db)

    for log in captured:
        assert "test_billing_key_plain" not in str(log)


# ── charge_renewal: retry_task_id 저장 ────────────────────────────────────────


@pytest.mark.asyncio
async def test_charge_renewal_failure_persists_retry_task_id():
    """3.3 실패 enqueue 시 send_task 반환 task id를 payment.retry_task_id에 저장."""
    from api.src.models.payment import Payment
    from api.src.services.billing_service import charge_renewal

    sub = _make_subscription()
    bk = _make_billing_key()
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_scalar_result(sub), _scalar_result(bk)])

    captured_payment = {}

    def _cap_add(o):
        if isinstance(o, Payment):
            o.id = 555
            captured_payment["payment"] = o

    db.add = MagicMock(side_effect=_cap_add)

    mock_pg = AsyncMock()
    mock_pg.charge = AsyncMock(
        return_value={
            "success": False,
            "provider_order_id": "renewal-50-fail",
            "failure_reason": "카드 정지",
            "raw_response": {"code": "CARD_SUSPENDED"},
        }
    )

    fake_task = MagicMock()
    fake_task.id = "renewal-retry-task-id"

    with patch("api.src.workers.celery_app.celery_app") as mock_celery_app:
        mock_celery_app.send_task = MagicMock(return_value=fake_task)
        with patch(
            "api.src.services.billing_service.get_pg_provider", return_value=mock_pg
        ):
            with patch("sentry_sdk.add_breadcrumb"):
                await charge_renewal(sub.id, db)

    payment = captured_payment["payment"]
    assert payment.retry_task_id == "renewal-retry-task-id"


@pytest.mark.asyncio
async def test_charge_renewal_pg_exception_persists_retry_task_id():
    """3.3 PG 예외 경로에서도 retry_task_id 저장."""
    from api.src.models.payment import Payment
    from api.src.services.billing_service import charge_renewal

    sub = _make_subscription()
    bk = _make_billing_key()
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_scalar_result(sub), _scalar_result(bk)])

    captured_payment = {}

    def _cap_add(o):
        if isinstance(o, Payment):
            o.id = 666
            captured_payment["payment"] = o

    db.add = MagicMock(side_effect=_cap_add)

    mock_pg = AsyncMock()
    mock_pg.charge = AsyncMock(side_effect=ConnectionError("network down"))

    fake_task = MagicMock()
    fake_task.id = "exc-retry-task-id"

    with patch("api.src.workers.celery_app.celery_app") as mock_celery_app:
        mock_celery_app.send_task = MagicMock(return_value=fake_task)
        with patch(
            "api.src.services.billing_service.get_pg_provider", return_value=mock_pg
        ):
            with patch("sentry_sdk.add_breadcrumb"):
                await charge_renewal(sub.id, db)

    payment = captured_payment["payment"]
    assert payment.retry_task_id == "exc-retry-task-id"


# ── issue_billing_key: revoke-on-card-change ─────────────────────────────────


@pytest.mark.asyncio
async def test_issue_billing_key_revokes_pending_retry_tasks():
    """카드 변경 시 retry_task_id가 있는 failed payments에 revoke 호출."""
    from api.src.models.payment import Payment
    from api.src.services.billing_service import issue_billing_key

    user = MagicMock()
    user.id = 1
    user.phone = "01012345678"

    failed_payment_1 = MagicMock(spec=Payment)
    failed_payment_1.id = 11
    failed_payment_1.user_id = 1
    failed_payment_1.status = "failed"
    failed_payment_1.retry_task_id = "task-aaa"

    failed_payment_2 = MagicMock(spec=Payment)
    failed_payment_2.id = 12
    failed_payment_2.user_id = 1
    failed_payment_2.status = "failed"
    failed_payment_2.retry_task_id = "task-bbb"

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(
        side_effect=[
            _scalars_result([]),  # 기존 활성 빌링키 없음
            _scalars_result([failed_payment_1, failed_payment_2]),  # pending retries
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
            "billing_key": "new_key",
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
                pg_token="token",
                customer_key="denvia_new",
                db=mock_db,
            )

    # revoke 호출 2회
    assert mock_celery_app.control.revoke.call_count == 2
    revoke_calls = [c.args[0] for c in mock_celery_app.control.revoke.call_args_list]
    assert "task-aaa" in revoke_calls
    assert "task-bbb" in revoke_calls

    # retry_task_id 초기화 확인
    assert failed_payment_1.retry_task_id is None
    assert failed_payment_2.retry_task_id is None


@pytest.mark.asyncio
async def test_issue_billing_key_no_revoke_when_no_pending_retries():
    """retry_task_id 있는 failed payment 없으면 revoke 미호출."""
    from api.src.services.billing_service import issue_billing_key

    user = MagicMock()
    user.id = 2
    user.phone = "01099998888"

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(
        side_effect=[
            _scalars_result([]),  # 기존 활성 빌링키 없음
            _scalars_result([]),  # pending retries 없음
        ]
    )

    async def fake_refresh(obj):
        obj.id = 100
        obj.card_last4 = "0000"
        obj.card_company = None

    mock_db.refresh = fake_refresh

    mock_pg = AsyncMock()
    mock_pg.issue_billing_key = AsyncMock(
        return_value={
            "billing_key": "new_key",
            "card_last4": "0000",
            "card_company": None,
        }
    )

    with patch("api.src.workers.celery_app.celery_app") as mock_celery_app:
        with patch(
            "api.src.services.billing_service.get_pg_provider", return_value=mock_pg
        ):
            await issue_billing_key(
                user=user,
                pg_token="token",
                customer_key="denvia_x",
                db=mock_db,
            )

    mock_celery_app.control.revoke.assert_not_called()


@pytest.mark.asyncio
async def test_issue_billing_key_revoke_exception_does_not_block_card_change():
    """revoke 호출 시 예외 발생해도 카드 등록 결과를 되돌리지 않는다 (warning만)."""
    from api.src.models.payment import Payment
    from api.src.services.billing_service import issue_billing_key

    user = MagicMock()
    user.id = 3
    user.phone = "01011112222"

    failed_payment = MagicMock(spec=Payment)
    failed_payment.id = 30
    failed_payment.user_id = 3
    failed_payment.status = "failed"
    failed_payment.retry_task_id = "task-error"

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(
        side_effect=[
            _scalars_result([]),
            _scalars_result([failed_payment]),
        ]
    )

    async def fake_refresh(obj):
        obj.id = 200
        obj.card_last4 = "1111"
        obj.card_company = "삼성"

    mock_db.refresh = fake_refresh

    mock_pg = AsyncMock()
    mock_pg.issue_billing_key = AsyncMock(
        return_value={
            "billing_key": "new",
            "card_last4": "1111",
            "card_company": "삼성",
        }
    )

    with patch("api.src.workers.celery_app.celery_app") as mock_celery_app:
        mock_celery_app.control.revoke = MagicMock(side_effect=RuntimeError("broker down"))
        with patch(
            "api.src.services.billing_service.get_pg_provider", return_value=mock_pg
        ):
            # 예외 전파되지 않아야 함
            result = await issue_billing_key(
                user=user,
                pg_token="token",
                customer_key="denvia_q",
                db=mock_db,
            )

    assert result["card_last4"] == "1111"
    # retry_task_id는 그래도 초기화
    assert failed_payment.retry_task_id is None


# ── 관측 로그 ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retry_payment_emits_billing_retry_attempted_log_on_success():
    """성공 시 structlog 'billing.retry.attempted' result='success' 기록."""
    import structlog.testing

    from api.src.services.billing_service import retry_payment

    payment = _make_payment()
    sub = _make_subscription()
    bk = _make_billing_key()
    db = _retry_db_executes(payment=payment, killswitch=None, sub=sub, bk=bk)

    mock_pg = AsyncMock()
    mock_pg.charge = AsyncMock(return_value=_make_charge_result(True))

    with structlog.testing.capture_logs() as captured:
        with patch(
            "api.src.services.billing_service.get_pg_provider", return_value=mock_pg
        ):
            with patch("api.src.services.billing_service._notify_retry", new=AsyncMock()):
                await retry_payment(payment.id, 2, db)

    attempted_logs = [
        log for log in captured if log.get("event") == "billing.retry.attempted"
    ]
    assert len(attempted_logs) == 1
    log = attempted_logs[0]
    assert log["payment_id"] == payment.id
    assert log["attempt"] == 2
    assert log["result"] == "success"
    assert "latency_ms" in log


@pytest.mark.asyncio
async def test_retry_payment_emits_billing_retry_attempted_log_on_failure():
    """실패 시 structlog 'billing.retry.attempted' result='failed' + failure_reason 기록."""
    import structlog.testing

    from api.src.services.billing_service import retry_payment

    payment = _make_payment()
    sub = _make_subscription()
    bk = _make_billing_key()
    db = _retry_db_executes(payment=payment, killswitch=None, sub=sub, bk=bk)

    mock_pg = AsyncMock()
    mock_pg.charge = AsyncMock(return_value=_make_charge_result(False))

    fake_task = MagicMock()
    fake_task.id = "log-task-id"

    with structlog.testing.capture_logs() as captured:
        with patch("api.src.workers.celery_app.celery_app") as mock_celery_app:
            mock_celery_app.send_task = MagicMock(return_value=fake_task)
            with patch(
                "api.src.services.billing_service.get_pg_provider", return_value=mock_pg
            ):
                with patch("api.src.services.billing_service._notify_retry", new=AsyncMock()):
                    with patch("sentry_sdk.add_breadcrumb"):
                        await retry_payment(payment.id, 2, db)

    attempted_logs = [
        log for log in captured if log.get("event") == "billing.retry.attempted"
    ]
    assert len(attempted_logs) == 1
    log = attempted_logs[0]
    assert log["result"] == "failed"
    assert log["failure_reason"] == "카드 잔액 부족"


# ── PG 예외 → 실패 attempt로 처리 ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retry_payment_pg_exception_intermediate_schedules_next_attempt():
    """attempt=2 PG 예외 → charge_failed + attempt_count=2 + attempt=3 재예약 (예외 비전파)."""
    from api.src.models.payment_event import PaymentEvent
    from api.src.services.billing_service import retry_payment

    payment = _make_payment(attempt_count=1)
    sub = _make_subscription()
    bk = _make_billing_key()
    db = _retry_db_executes(payment=payment, killswitch=None, sub=sub, bk=bk)
    added: list = []
    db.add = MagicMock(side_effect=lambda o: added.append(o))

    mock_pg = AsyncMock()
    mock_pg.charge = AsyncMock(side_effect=ConnectionError("network down"))

    fake_task = MagicMock()
    fake_task.id = "exc-attempt-3-task"

    mock_notify = AsyncMock()
    with patch("api.src.workers.celery_app.celery_app") as mock_celery_app:
        mock_celery_app.send_task = MagicMock(return_value=fake_task)
        with patch(
            "api.src.services.billing_service.get_pg_provider", return_value=mock_pg
        ):
            with patch("api.src.services.billing_service._notify_retry", mock_notify):
                with patch("sentry_sdk.add_breadcrumb"):
                    # 예외가 Celery 밖으로 raise되면 안 됨
                    result = await retry_payment(payment.id, 2, db)

    assert result["status"] == "failed"
    assert result["payment_id"] == payment.id
    assert result["attempt"] == 2

    # attempt 소비됨 + 다음 attempt(3) 예약
    assert payment.attempt_count == 2
    assert payment.retry_task_id == "exc-attempt-3-task"
    mock_celery_app.send_task.assert_called_once_with(
        "billing.retry_payment",
        args=[payment.id, 3],
        countdown=259200,
    )

    # charge_failed 이벤트가 남는다
    events = [o for o in added if isinstance(o, PaymentEvent)]
    types = {e.event_type for e in events}
    assert "charge_failed" in types
    assert "retry_scheduled" in types


@pytest.mark.asyncio
async def test_retry_payment_pg_exception_final_attempt_cancels_pending():
    """attempt=4 PG 예외 → 재예약 없음 + cancel_pending + cancel_reason='payment_retry_exhausted'."""
    from api.src.services.billing_service import retry_payment

    payment = _make_payment(attempt_count=3, retry_task_id="prev-task")
    sub = _make_subscription()
    bk = _make_billing_key()
    db = _retry_db_executes(payment=payment, killswitch=None, sub=sub, bk=bk)

    mock_pg = AsyncMock()
    mock_pg.charge = AsyncMock(side_effect=TimeoutError("PG timeout after retries"))

    mock_notify = AsyncMock()
    with patch("api.src.workers.celery_app.celery_app") as mock_celery_app:
        mock_celery_app.send_task = MagicMock()
        with patch(
            "api.src.services.billing_service.get_pg_provider", return_value=mock_pg
        ):
            with patch("api.src.services.billing_service._notify_retry", mock_notify):
                with patch("sentry_sdk.add_breadcrumb"):
                    result = await retry_payment(payment.id, 4, db)

    assert result["status"] == "failed"
    # 더 이상 재예약 없음
    mock_celery_app.send_task.assert_not_called()
    assert payment.retry_task_id is None
    assert payment.attempt_count == 4
    assert sub.status == "cancel_pending"
    assert sub.cancel_reason == "payment_retry_exhausted"
