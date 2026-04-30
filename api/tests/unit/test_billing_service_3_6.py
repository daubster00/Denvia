"""BillingService 단위 테스트 — Story 3.6 환불 요청.

request_refund / _evaluate_auto_eligibility / _execute_auto_refund /
_enqueue_manual_review / _notify_refund 분기 검증.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _make_user(user_id: int = 10, phone: str = "010-1234-5678") -> MagicMock:
    u = MagicMock()
    u.id = user_id
    u.phone = phone
    u.subscription_status = "pro"
    u.withdrawn_at = None
    return u


def _make_payment(
    payment_id: int = 200,
    user_id: int = 10,
    subscription_id: int | None = 50,
    status: str = "success",
    days_ago: int = 1,
    amount_krw: int = 9900,
) -> MagicMock:
    p = MagicMock()
    p.id = payment_id
    p.user_id = user_id
    p.subscription_id = subscription_id
    p.status = status
    p.amount_krw = amount_krw
    p.charged_at = _now_utc() - timedelta(days=days_ago)
    p.provider_order_id = f"denvia-pro-test-{payment_id}"
    return p


def _make_subscription(
    sub_id: int = 50,
    user_id: int = 10,
    status: str = "active",
    period_end_offset_days: int = 25,
    period_start_offset_days: int = -5,
) -> MagicMock:
    sub = MagicMock()
    sub.id = sub_id
    sub.user_id = user_id
    sub.status = status
    now = _now_utc()
    sub.started_at = now + timedelta(days=period_start_offset_days)
    sub.current_period_end = now + timedelta(days=period_end_offset_days)
    sub.next_charge_at = now + timedelta(days=period_end_offset_days)
    sub.canceled_at = None
    sub.cancel_reason = None
    return sub


def _scalar_result(obj) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none = MagicMock(return_value=obj)
    r.scalar_one = MagicMock(return_value=obj)
    r.scalar = MagicMock(return_value=obj)
    return r


# ── _evaluate_auto_eligibility ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_eligibility_within_7d_zero_qa_returns_true():
    """7일 이내 + qa=0 → eligible."""
    from api.src.services.billing_service import _evaluate_auto_eligibility

    payment = _make_payment(days_ago=3)
    sub = _make_subscription()

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result(sub),    # subscription select
            _scalar_result(0),      # qa_logs count
        ]
    )

    eligible, qa, days, code = await _evaluate_auto_eligibility(payment, db)

    assert eligible is True
    assert qa == 0
    assert days == 3
    assert code is None


@pytest.mark.asyncio
async def test_eligibility_period_exceeded():
    """7일 초과 + qa=0 → False, period_exceeded."""
    from api.src.services.billing_service import _evaluate_auto_eligibility

    payment = _make_payment(days_ago=10)
    sub = _make_subscription()

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_scalar_result(sub), _scalar_result(0)])

    eligible, qa, days, code = await _evaluate_auto_eligibility(payment, db)

    assert eligible is False
    assert qa == 0
    assert days == 10
    assert code == "period_exceeded"


@pytest.mark.asyncio
async def test_eligibility_qa_count_exceeded():
    """7일 이내 + qa>0 → False, qa_count_exceeded."""
    from api.src.services.billing_service import _evaluate_auto_eligibility

    payment = _make_payment(days_ago=2)
    sub = _make_subscription()

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_scalar_result(sub), _scalar_result(5)])

    eligible, qa, days, code = await _evaluate_auto_eligibility(payment, db)

    assert eligible is False
    assert qa == 5
    assert code == "qa_count_exceeded"


@pytest.mark.asyncio
async def test_eligibility_both_exceeded():
    """7일 초과 + qa>0 → False, both."""
    from api.src.services.billing_service import _evaluate_auto_eligibility

    payment = _make_payment(days_ago=15)
    sub = _make_subscription()

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_scalar_result(sub), _scalar_result(2)])

    eligible, qa, days, code = await _evaluate_auto_eligibility(payment, db)

    assert eligible is False
    assert qa == 2
    assert days == 15
    assert code == "both"


@pytest.mark.asyncio
async def test_eligibility_no_subscription_id():
    """payment.subscription_id None → False, no_subscription. DB 미조회."""
    from api.src.services.billing_service import _evaluate_auto_eligibility

    payment = _make_payment(days_ago=2, subscription_id=None)

    db = AsyncMock()
    db.execute = AsyncMock()

    eligible, qa, days, code = await _evaluate_auto_eligibility(payment, db)

    assert eligible is False
    assert qa == 0
    assert code == "no_subscription"
    db.execute.assert_not_called()


# ── request_refund ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_request_refund_payment_not_found():
    """payment 미존재 → PaymentNotFound."""
    from api.src.services.billing_service import (
        PaymentNotFound,
        request_refund,
    )

    user = _make_user()
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalar_result(None))

    with pytest.raises(PaymentNotFound):
        await request_refund(user, 999, None, db)


@pytest.mark.asyncio
async def test_request_refund_other_user_payment_404():
    """타인 결제 → PaymentNotFound (403 enumeration 차단)."""
    from api.src.services.billing_service import (
        PaymentNotFound,
        request_refund,
    )

    user = _make_user(user_id=10)
    payment = _make_payment(user_id=99)  # 타인
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalar_result(payment))

    with pytest.raises(PaymentNotFound):
        await request_refund(user, payment.id, None, db)


@pytest.mark.asyncio
async def test_request_refund_already_refunded():
    """status='refunded' → RefundAlreadyProcessed."""
    from api.src.services.billing_service import (
        RefundAlreadyProcessed,
        request_refund,
    )

    user = _make_user()
    payment = _make_payment(status="refunded")
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalar_result(payment))

    with pytest.raises(RefundAlreadyProcessed):
        await request_refund(user, payment.id, None, db)


@pytest.mark.asyncio
async def test_request_refund_already_requested():
    """status='refund_pending' → RefundAlreadyRequested."""
    from api.src.services.billing_service import (
        RefundAlreadyRequested,
        request_refund,
    )

    user = _make_user()
    payment = _make_payment(status="refund_pending")
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalar_result(payment))

    with pytest.raises(RefundAlreadyRequested):
        await request_refund(user, payment.id, None, db)


@pytest.mark.asyncio
async def test_request_refund_failed_status():
    """status='failed' → PaymentNotRefundable."""
    from api.src.services.billing_service import (
        PaymentNotRefundable,
        request_refund,
    )

    user = _make_user()
    payment = _make_payment(status="failed")
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalar_result(payment))

    with pytest.raises(PaymentNotRefundable):
        await request_refund(user, payment.id, None, db)


@pytest.mark.asyncio
async def test_request_refund_pending_status():
    """status='pending' → PaymentNotRefundable."""
    from api.src.services.billing_service import (
        PaymentNotRefundable,
        request_refund,
    )

    user = _make_user()
    payment = _make_payment(status="pending")
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalar_result(payment))

    with pytest.raises(PaymentNotRefundable):
        await request_refund(user, payment.id, None, db)


# ── _execute_auto_refund ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_auto_refund_success():
    """PG 성공 → payment.status='refunded' + sub.status='canceled' + users.subscription_status='free'."""
    from api.src.services.billing_service import _execute_auto_refund

    payment = _make_payment(status="success", days_ago=3)
    sub = _make_subscription(status="active")

    db = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result(sub),  # subscription select for transition
            MagicMock(),          # User update
        ]
    )

    fake_pg = MagicMock()
    fake_pg.refund = AsyncMock(
        return_value={"success": True, "raw_response": {"transactionKey": "tx_001"}}
    )

    with patch(
        "api.src.services.billing_service.get_pg_provider",
        return_value=fake_pg,
    ), patch(
        "api.src.services.billing_service._notify_refund",
        new=AsyncMock(),
    ):
        result = await _execute_auto_refund(payment, "user_request", 0, 3, db)

    assert payment.status == "refunded"
    assert sub.status == "canceled"
    assert sub.next_charge_at is None
    assert sub.cancel_reason == "auto_refund"
    assert sub.canceled_at is not None
    assert result["status"] == "refunded"
    assert result["amount_krw"] == payment.amount_krw
    # commit 최소 2회 호출(refund_pending set, 최종 success 전이)
    assert db.commit.await_count >= 2


@pytest.mark.asyncio
async def test_execute_auto_refund_commit_failure_after_pg_success_logs_error():
    """PG refund 성공 후 최종 commit 실패 → logger.error('billing.refund.commit_failed_after_pg_success').

    PG는 이미 환불을 끝냈지만 DB 전이는 실패한 상태(payment.status='refund_pending'으로 남음).
    예외는 숨기지 않고, 운영자 reconcile에 필요한 식별자를 강하게 로그에 남긴다.
    """
    import structlog.testing

    from api.src.services.billing_service import _execute_auto_refund

    payment = _make_payment(status="success", days_ago=3)
    sub = _make_subscription(status="active")

    db = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result(sub),
            MagicMock(),
        ]
    )
    # 첫 commit(refund_pending 전환)은 성공, 두 번째(최종 전이) commit은 실패
    db.commit = AsyncMock(
        side_effect=[None, RuntimeError("connection lost mid-commit")]
    )

    fake_pg = MagicMock()
    fake_pg.refund = AsyncMock(
        return_value={
            "success": True,
            "raw_response": {"transactionKey": "tx_after_pg"},
        }
    )

    with structlog.testing.capture_logs() as captured:
        with patch(
            "api.src.services.billing_service.get_pg_provider",
            return_value=fake_pg,
        ), patch(
            "api.src.services.billing_service._notify_refund",
            new=AsyncMock(),
        ):
            with pytest.raises(RuntimeError):
                await _execute_auto_refund(payment, "user_request", 0, 3, db)

    err_logs = [
        log
        for log in captured
        if log.get("event") == "billing.refund.commit_failed_after_pg_success"
    ]
    assert len(err_logs) == 1
    log = err_logs[0]
    assert log["payment_id"] == payment.id
    assert log["user_id"] == payment.user_id
    assert log["subscription_id"] == payment.subscription_id
    assert log["provider_order_id"] == payment.provider_order_id
    assert log["amount_krw"] == payment.amount_krw
    assert log["error_type"] == "RuntimeError"
    assert log["log_level"] == "error"


@pytest.mark.asyncio
async def test_execute_auto_refund_force_transitions_cancel_pending():
    """cancel_pending 구독도 자동 환불 시 canceled로 강제 전이."""
    from api.src.services.billing_service import _execute_auto_refund

    payment = _make_payment(status="success", days_ago=2)
    sub = _make_subscription(status="cancel_pending")
    sub.cancel_reason = "user_cancel"  # 기존 사유 — auto_refund로 덮어씌워져야 함

    db = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result(sub),
            MagicMock(),
        ]
    )

    fake_pg = MagicMock()
    fake_pg.refund = AsyncMock(
        return_value={"success": True, "raw_response": {}}
    )

    with patch(
        "api.src.services.billing_service.get_pg_provider",
        return_value=fake_pg,
    ), patch(
        "api.src.services.billing_service._notify_refund",
        new=AsyncMock(),
    ):
        await _execute_auto_refund(payment, "user_request", 0, 2, db)

    assert sub.status == "canceled"
    assert sub.cancel_reason == "auto_refund"  # 덮어씌워짐


@pytest.mark.asyncio
async def test_execute_auto_refund_transport_error_reverts():
    """PG transport 예외 → status='success' 원복, payment_event 미생성."""
    import httpx

    from api.src.services.billing_service import (
        RefundProviderUnavailable,
        _execute_auto_refund,
    )

    payment = _make_payment(status="success", days_ago=2)
    db = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock()

    fake_pg = MagicMock()
    fake_pg.refund = AsyncMock(side_effect=httpx.ConnectError("network down"))

    with patch(
        "api.src.services.billing_service.get_pg_provider",
        return_value=fake_pg,
    ):
        with pytest.raises(RefundProviderUnavailable) as exc_info:
            await _execute_auto_refund(payment, "user_request", 0, 2, db)

    assert exc_info.value.failure_kind == "transport_failure"
    assert payment.status == "success"  # 원복됨
    # payment_event INSERT 없음
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_execute_auto_refund_4xx_inserts_refund_denied_and_reverts():
    """PG RefundResult(success=False) → refund_denied 이벤트 + 원복 + 502."""
    from api.src.services.billing_service import (
        RefundProviderUnavailable,
        _execute_auto_refund,
    )

    payment = _make_payment(status="success", days_ago=2)
    db = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock()

    fake_pg = MagicMock()
    fake_pg.refund = AsyncMock(
        return_value={
            "success": False,
            "raw_response": {"code": "ALREADY_CANCELED_PAYMENT", "message": "already"},
        }
    )

    with patch(
        "api.src.services.billing_service.get_pg_provider",
        return_value=fake_pg,
    ):
        with pytest.raises(RefundProviderUnavailable) as exc_info:
            await _execute_auto_refund(payment, "user_request", 0, 2, db)

    assert exc_info.value.failure_kind == "api_4xx"
    assert exc_info.value.pg_error_code == "ALREADY_CANCELED_PAYMENT"
    assert payment.status == "success"  # 원복
    # refund_denied 이벤트가 add됨
    assert db.add.call_count == 1


# ── _enqueue_manual_review ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_enqueue_manual_review_inserts_queue_and_payment_event():
    """수동 검토 큐 + payment_event(refund_requested) INSERT, payment.status=refund_pending."""
    from api.src.services.billing_service import _enqueue_manual_review

    payment = _make_payment(status="success", days_ago=15)
    db = AsyncMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()

    result = await _enqueue_manual_review(
        payment, "환불 사유 텍스트", 5, 15, "both", db
    )

    assert payment.status == "refund_pending"
    # queue + payment_event 두 번 add
    assert db.add.call_count == 2
    assert result["status"] == "queued_for_review"
    assert result["reason_code"] == "both"
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_enqueue_manual_review_does_not_change_subscription():
    """수동 검토 경로는 subscription/user 변경 없음."""
    from api.src.services.billing_service import _enqueue_manual_review

    payment = _make_payment(status="success", days_ago=10)
    db = AsyncMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock()

    await _enqueue_manual_review(payment, None, 0, 10, "period_exceeded", db)

    # User update / Subscription select 미호출
    db.execute.assert_not_called()


# ── _notify_refund ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notify_refund_calls_send():
    """정상 호출 → svc.send 호출 args 일치."""
    from api.src.services.billing_service import _notify_refund

    user = _make_user()

    fake_session = AsyncMock()
    fake_session.execute = AsyncMock(return_value=_scalar_result(user))

    fake_factory_cm = AsyncMock()
    fake_factory_cm.__aenter__ = AsyncMock(return_value=fake_session)
    fake_factory_cm.__aexit__ = AsyncMock(return_value=False)
    fake_factory = MagicMock(return_value=fake_factory_cm)

    svc_mock = MagicMock()
    svc_mock.send = AsyncMock()

    refunded_at = _now_utc()

    with patch("api.src.models.base.async_session_factory", fake_factory):
        with patch(
            "api.src.integrations.messaging.notification_service.get_notification_service",
            return_value=svc_mock,
        ):
            await _notify_refund(
                user_id=user.id,
                amount_krw=9900,
                refunded_at=refunded_at,
                payment_id=200,
            )

    svc_mock.send.assert_awaited_once()
    call_kwargs = svc_mock.send.await_args.kwargs
    assert call_kwargs["user_id"] == user.id
    assert call_kwargs["template_code"] == "billing.refund_success"
    assert call_kwargs["idempotency_key"] == "refund:200:auto_success"
    assert call_kwargs["variables"]["amount_krw"] == "9900"


@pytest.mark.asyncio
async def test_notify_refund_swallows_send_exception():
    """svc.send 예외 → warning만 남기고 상위 전파 0."""
    from api.src.services.billing_service import _notify_refund

    user = _make_user()
    fake_session = AsyncMock()
    fake_session.execute = AsyncMock(return_value=_scalar_result(user))

    fake_factory_cm = AsyncMock()
    fake_factory_cm.__aenter__ = AsyncMock(return_value=fake_session)
    fake_factory_cm.__aexit__ = AsyncMock(return_value=False)
    fake_factory = MagicMock(return_value=fake_factory_cm)

    svc_mock = MagicMock()
    svc_mock.send = AsyncMock(side_effect=RuntimeError("boom"))

    with patch("api.src.models.base.async_session_factory", fake_factory):
        with patch(
            "api.src.integrations.messaging.notification_service.get_notification_service",
            return_value=svc_mock,
        ):
            # 예외가 상위로 전파되면 안 됨
            await _notify_refund(
                user_id=user.id,
                amount_krw=9900,
                refunded_at=_now_utc(),
                payment_id=200,
            )


@pytest.mark.asyncio
async def test_notify_refund_skips_withdrawn_user():
    """withdrawn user → svc.send 미호출."""
    from api.src.services.billing_service import _notify_refund

    fake_session = AsyncMock()
    fake_session.execute = AsyncMock(return_value=_scalar_result(None))

    fake_factory_cm = AsyncMock()
    fake_factory_cm.__aenter__ = AsyncMock(return_value=fake_session)
    fake_factory_cm.__aexit__ = AsyncMock(return_value=False)
    fake_factory = MagicMock(return_value=fake_factory_cm)

    svc_mock = MagicMock()
    svc_mock.send = AsyncMock()

    with patch("api.src.models.base.async_session_factory", fake_factory):
        with patch(
            "api.src.integrations.messaging.notification_service.get_notification_service",
            return_value=svc_mock,
        ):
            await _notify_refund(
                user_id=10,
                amount_krw=9900,
                refunded_at=_now_utc(),
                payment_id=200,
            )

    svc_mock.send.assert_not_called()
