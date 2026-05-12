"""BillingService 단위 테스트 — Story 3.6 v1.1 청약철회 (Cooling-off Refund).

v1.0 (자가 환불 요청 + 수동 검토 큐) 모델 폐기.
대상 함수: check_refund_eligibility / cancel_with_refund /
_evaluate_cooling_off_eligibility / _execute_cooling_off_refund / _notify_refund.
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


# ── _evaluate_cooling_off_eligibility ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_eligibility_within_7d_zero_qa_returns_true():
    """7일 이내 + qa=0 → eligible."""
    from api.src.services.billing_service import _evaluate_cooling_off_eligibility

    payment = _make_payment(days_ago=3)
    sub = _make_subscription()

    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalar_result(0))  # qa count = 0

    eligible, qa, days, code = await _evaluate_cooling_off_eligibility(payment, sub, db)

    assert eligible is True
    assert qa == 0
    assert days == 3
    assert code is None


@pytest.mark.asyncio
async def test_eligibility_period_exceeded():
    """8일 이상 + qa=0 → period_exceeded."""
    from api.src.services.billing_service import _evaluate_cooling_off_eligibility

    payment = _make_payment(days_ago=8)
    sub = _make_subscription()

    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalar_result(0))

    eligible, qa, days, code = await _evaluate_cooling_off_eligibility(payment, sub, db)

    assert eligible is False
    assert qa == 0
    assert code == "period_exceeded"


@pytest.mark.asyncio
async def test_eligibility_qa_count_exceeded():
    """7일 이내 + qa>=1 → qa_count_exceeded."""
    from api.src.services.billing_service import _evaluate_cooling_off_eligibility

    payment = _make_payment(days_ago=2)
    sub = _make_subscription()

    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalar_result(3))

    eligible, qa, days, code = await _evaluate_cooling_off_eligibility(payment, sub, db)

    assert eligible is False
    assert qa == 3
    assert code == "qa_count_exceeded"


@pytest.mark.asyncio
async def test_eligibility_both_exceeded():
    """8일 이상 + qa>=1 → both."""
    from api.src.services.billing_service import _evaluate_cooling_off_eligibility

    payment = _make_payment(days_ago=10)
    sub = _make_subscription()

    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalar_result(5))

    eligible, _qa, _days, code = await _evaluate_cooling_off_eligibility(payment, sub, db)

    assert eligible is False
    assert code == "both"


# ── check_refund_eligibility (AC1) ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_eligibility_no_active_subscription():
    """활성 구독이 없으면 reason_code=no_active_payment."""
    from api.src.services.billing_service import check_refund_eligibility

    user = _make_user()
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalar_result(None))  # no subscription

    result = await check_refund_eligibility(user, db)

    assert result["eligible"] is False
    assert result["reason_code"] == "no_active_payment"
    assert result["payment_id"] is None
    assert result["amount_krw"] is None
    assert result["charged_at"] is None


@pytest.mark.asyncio
async def test_check_eligibility_no_success_payment():
    """활성 구독은 있지만 success payment가 없으면 no_active_payment."""
    from api.src.services.billing_service import check_refund_eligibility

    user = _make_user()
    sub = _make_subscription()
    db = AsyncMock()
    # 1st execute = subscription, 2nd = latest success payment (None)
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result(sub),
            _scalar_result(None),
        ]
    )

    result = await check_refund_eligibility(user, db)

    assert result["eligible"] is False
    assert result["reason_code"] == "no_active_payment"


@pytest.mark.asyncio
async def test_check_eligibility_ok_returns_payment_metadata():
    """7일 이내 + qa=0 → eligible=True + ok + ISO charged_at."""
    from api.src.services.billing_service import check_refund_eligibility

    user = _make_user()
    sub = _make_subscription()
    payment = _make_payment(days_ago=3, amount_krw=19800)
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result(sub),       # subscription
            _scalar_result(payment),   # latest success payment
            _scalar_result(0),         # qa count
        ]
    )

    result = await check_refund_eligibility(user, db)

    assert result["eligible"] is True
    assert result["reason_code"] == "ok"
    assert result["payment_id"] == 200
    assert result["amount_krw"] == 19800
    assert result["days_since_charge"] == 3
    assert result["qa_count_during_period"] == 0
    assert isinstance(result["charged_at"], str)  # ISO 8601 string
    assert "T" in result["charged_at"]


@pytest.mark.asyncio
async def test_check_eligibility_period_exceeded():
    """8일 초과 → eligible=False + period_exceeded."""
    from api.src.services.billing_service import check_refund_eligibility

    user = _make_user()
    sub = _make_subscription()
    payment = _make_payment(days_ago=10)
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result(sub),
            _scalar_result(payment),
            _scalar_result(0),
        ]
    )

    result = await check_refund_eligibility(user, db)

    assert result["eligible"] is False
    assert result["reason_code"] == "period_exceeded"


@pytest.mark.asyncio
async def test_check_eligibility_qa_count_exceeded():
    """7일 이내지만 qa>=1 → qa_count_exceeded."""
    from api.src.services.billing_service import check_refund_eligibility

    user = _make_user()
    sub = _make_subscription()
    payment = _make_payment(days_ago=2)
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result(sub),
            _scalar_result(payment),
            _scalar_result(7),  # 7 questions answered
        ]
    )

    result = await check_refund_eligibility(user, db)

    assert result["eligible"] is False
    assert result["reason_code"] == "qa_count_exceeded"


# ── cancel_with_refund (AC2~AC4, AC7) ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_with_refund_no_active_subscription_raises():
    """활성 구독 없으면 NoActiveSubscription."""
    from api.src.services.billing_service import NoActiveSubscription, cancel_with_refund

    user = _make_user()
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalar_result(None))

    with pytest.raises(NoActiveSubscription):
        await cancel_with_refund(user, db)


@pytest.mark.asyncio
async def test_cancel_with_refund_no_success_payment_raises():
    """success payment 없으면 NoRefundablePayment."""
    from api.src.services.billing_service import NoRefundablePayment, cancel_with_refund

    user = _make_user()
    sub = _make_subscription()
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result(sub),
            _scalar_result(None),  # no latest payment
        ]
    )

    with pytest.raises(NoRefundablePayment):
        await cancel_with_refund(user, db)


@pytest.mark.asyncio
async def test_cancel_with_refund_already_refunded_raises():
    """payment.status='refunded' → RefundAlreadyProcessed."""
    from api.src.services.billing_service import (
        RefundAlreadyProcessed,
        cancel_with_refund,
    )

    user = _make_user()
    sub = _make_subscription()
    payment_candidate = _make_payment(status="success")  # 사전 조회 결과는 success
    payment_locked = _make_payment(status="refunded")    # lock 시점에는 이미 환불됨

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result(sub),
            _scalar_result(payment_candidate),
            _scalar_result(payment_locked),
        ]
    )

    with pytest.raises(RefundAlreadyProcessed):
        await cancel_with_refund(user, db)


@pytest.mark.asyncio
async def test_cancel_with_refund_pending_raises():
    """payment.status='refund_pending' → RefundAlreadyRequested."""
    from api.src.services.billing_service import (
        RefundAlreadyRequested,
        cancel_with_refund,
    )

    user = _make_user()
    sub = _make_subscription()
    payment_candidate = _make_payment(status="success")
    payment_locked = _make_payment(status="refund_pending")

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result(sub),
            _scalar_result(payment_candidate),
            _scalar_result(payment_locked),
        ]
    )

    with pytest.raises(RefundAlreadyRequested):
        await cancel_with_refund(user, db)


@pytest.mark.asyncio
async def test_cancel_with_refund_not_eligible_raises_with_reason():
    """조건 미충족 (qa>=1) → RefundNotEligible(reason_code='qa_count_exceeded')."""
    from api.src.services.billing_service import RefundNotEligible, cancel_with_refund

    user = _make_user()
    sub = _make_subscription()
    payment = _make_payment(days_ago=2, status="success")

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result(sub),       # subscription
            _scalar_result(payment),   # latest payment
            _scalar_result(payment),   # locked payment
            _scalar_result(3),         # qa count
        ]
    )

    with pytest.raises(RefundNotEligible) as exc_info:
        await cancel_with_refund(user, db)
    assert exc_info.value.reason_code == "qa_count_exceeded"


# ── _execute_cooling_off_refund (AC3 + AC5/AC6) ───────────────────────────────


@pytest.mark.asyncio
async def test_execute_refund_success_transitions_states_and_notifies():
    """성공: payment.status='refunded', subscription canceled, user free, 알림 발송."""
    from api.src.services.billing_service import _execute_cooling_off_refund

    payment = _make_payment(status="refund_pending", amount_krw=19800)
    sub = _make_subscription()

    db = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock(return_value=_scalar_result(sub))

    pg = MagicMock()
    pg.refund = AsyncMock(
        return_value={"success": True, "raw_response": {"status": "DONE"}}
    )

    notify_mock = AsyncMock()
    with (
        patch(
            "api.src.services.billing_service.get_pg_provider",
            return_value=pg,
        ),
        patch(
            "api.src.services.billing_service._notify_refund",
            new=notify_mock,
        ),
    ):
        result = await _execute_cooling_off_refund(payment, qa_count=0, days_since=3, db=db)

    assert result["status"] == "refunded"
    assert result["refund_kind"] == "cooling_off"
    assert result["amount_krw"] == 19800
    assert result["subscription_status"] == "canceled"
    assert payment.status == "refunded"
    assert sub.status == "canceled"
    assert sub.next_charge_at is None
    assert sub.cancel_reason == "cooling_off_refund"
    # PG는 cancel_amount=전액으로 호출되었어야 함
    pg.refund.assert_awaited_once()
    call_args = pg.refund.await_args
    assert call_args.args[1] == 19800
    # 알림 호출 — idempotency_key가 cooling_off namespace
    notify_mock.assert_awaited_once()
    kwargs = notify_mock.await_args.kwargs
    assert kwargs["idempotency_key"] == f"refund:{payment.id}:cooling_off"
    assert kwargs["refund_reason"] == "cooling_off"
    assert kwargs["refund_amount_krw"] == 19800


@pytest.mark.asyncio
async def test_execute_refund_transport_failure_rolls_back():
    """PG transport 장애 → status 원복 + RefundProviderUnavailable(transport_failure)."""
    from api.src.services.billing_service import (
        RefundProviderUnavailable,
        _execute_cooling_off_refund,
    )

    payment = _make_payment(status="refund_pending")
    db = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()

    pg = MagicMock()
    pg.refund = AsyncMock(side_effect=RuntimeError("transport"))

    with patch(
        "api.src.services.billing_service.get_pg_provider",
        return_value=pg,
    ):
        with pytest.raises(RefundProviderUnavailable) as exc_info:
            await _execute_cooling_off_refund(payment, qa_count=0, days_since=3, db=db)
    assert exc_info.value.failure_kind == "transport_failure"
    assert payment.status == "success"  # 원복 확인


@pytest.mark.asyncio
async def test_execute_refund_api_4xx_rolls_back_with_event_record():
    """PG 4xx → refund_denied 이벤트 INSERT + status 원복 + 502."""
    from api.src.services.billing_service import (
        RefundProviderUnavailable,
        _execute_cooling_off_refund,
    )

    payment = _make_payment(status="refund_pending")
    db = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()

    pg = MagicMock()
    pg.refund = AsyncMock(
        return_value={
            "success": False,
            "raw_response": {"code": "ALREADY_CANCELED_PAYMENT", "message": "이미 취소"},
        }
    )

    with patch(
        "api.src.services.billing_service.get_pg_provider",
        return_value=pg,
    ):
        with pytest.raises(RefundProviderUnavailable) as exc_info:
            await _execute_cooling_off_refund(payment, qa_count=0, days_since=3, db=db)
    assert exc_info.value.failure_kind == "api_4xx"
    assert exc_info.value.pg_error_code == "ALREADY_CANCELED_PAYMENT"
    assert payment.status == "success"
    # refund_denied 이벤트가 한 번 add 되었어야 함
    add_calls = [c for c in db.add.call_args_list if c.args]
    assert any(getattr(c.args[0], "event_type", None) == "refund_denied" for c in add_calls)


# ── _notify_refund (AC3 ⑥ + AC10) ─────────────────────────────────────────────


class _AsyncSessionCtx:
    """`async with async_session_factory() as db:` 패턴 mock 컨텍스트 매니저."""

    def __init__(self, session: AsyncMock) -> None:
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_notify_refund_passes_all_template_variables():
    """알림 호출 시 amount_krw + refund_amount_krw + refund_reason + effective_at 전부 전달."""
    from api.src.services.billing_service import _notify_refund

    user = MagicMock()
    user.phone = "01012345678"
    user.withdrawn_at = None

    user_select_result = MagicMock()
    user_select_result.scalar_one_or_none = MagicMock(return_value=user)

    session_mock = AsyncMock()
    session_mock.execute = AsyncMock(return_value=user_select_result)

    factory_mock = MagicMock(return_value=_AsyncSessionCtx(session_mock))

    svc = MagicMock()
    svc.send = AsyncMock()

    with (
        patch(
            "api.src.models.base.async_session_factory",
            new=factory_mock,
        ),
        patch(
            "api.src.integrations.messaging.notification_service.get_notification_service",
            return_value=svc,
        ),
    ):
        await _notify_refund(
            user_id=10,
            amount_krw=19800,
            refund_amount_krw=19800,
            refunded_at=_now_utc(),
            payment_id=200,
            refund_reason="cooling_off",
            idempotency_key="refund:200:cooling_off",
        )

    svc.send.assert_awaited_once()
    kwargs = svc.send.await_args.kwargs
    variables = kwargs["variables"]
    # refund_reason 코드값 → 한국어 라벨로 매핑 (docs/ALIMTALK_TEMPLATES.md §7)
    assert variables["refund_reason_label"] == "즉시 해지 및 전액 환불"
    # 금액은 콤마 포맷 (`19,800`)
    assert variables["amount_krw"] == "19,800"
    assert variables["refund_amount_krw"] == "19,800"
    assert "effective_at" in variables
    assert kwargs["idempotency_key"] == "refund:200:cooling_off"
    assert kwargs["template_code"] == "billing.refund_success"
