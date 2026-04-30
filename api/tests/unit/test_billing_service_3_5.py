"""BillingService 단위 테스트 — Story 3.5 구독 해지/철회.

cancel_subscription / resume_subscription / finalize_cancellations /
get_current_subscription / _notify_subscription_event 분기 검증.
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


def _make_subscription(
    sub_id: int = 50,
    user_id: int = 10,
    status: str = "active",
    period_end_offset_days: int = 10,
) -> MagicMock:
    sub = MagicMock()
    sub.id = sub_id
    sub.user_id = user_id
    sub.status = status
    now = _now_utc()
    sub.started_at = now - timedelta(days=20)
    sub.current_period_end = now + timedelta(days=period_end_offset_days)
    sub.next_charge_at = now + timedelta(days=period_end_offset_days)
    sub.canceled_at = None
    sub.cancel_reason = None
    return sub


def _scalar_result(obj) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none = MagicMock(return_value=obj)
    return r


def _scalars_result(objs: list) -> MagicMock:
    r = MagicMock()
    r.scalars.return_value.all.return_value = objs
    return r


# ── cancel_subscription ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_active_to_cancel_pending():
    """active → cancel_pending 전이 + canceled_at/cancel_reason 저장."""
    from api.src.services.billing_service import cancel_subscription

    user = _make_user()
    sub = _make_subscription(status="active")
    expected_effective_at = sub.current_period_end.isoformat()

    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalar_result(sub))
    db.commit = AsyncMock()

    with patch(
        "api.src.services.billing_service._notify_subscription_event",
        new=AsyncMock(),
    ):
        result = await cancel_subscription(user, "사용 빈도 감소", db)

    assert sub.status == "cancel_pending"
    assert sub.cancel_reason == "사용 빈도 감소"
    assert sub.canceled_at is not None
    assert result == {
        "status": "cancel_pending",
        "effective_at": expected_effective_at,
    }
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_cancel_already_cancel_pending_idempotent():
    """이미 cancel_pending → 멱등 200, fields 보존, 알림 미호출."""
    from api.src.services.billing_service import cancel_subscription

    user = _make_user()
    sub = _make_subscription(status="cancel_pending")
    sub.canceled_at = _now_utc() - timedelta(days=1)
    sub.cancel_reason = "기존 사유"

    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalar_result(sub))
    db.commit = AsyncMock()

    notify_mock = AsyncMock()
    with patch(
        "api.src.services.billing_service._notify_subscription_event",
        notify_mock,
    ):
        result = await cancel_subscription(user, "새 사유", db)

    assert sub.status == "cancel_pending"
    assert sub.cancel_reason == "기존 사유"  # 보존
    assert result["status"] == "cancel_pending"
    notify_mock.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_cancel_already_canceled_raises():
    """canceled 1건 + active 0건 → SubscriptionAlreadyCanceled."""
    from api.src.services.billing_service import (
        SubscriptionAlreadyCanceled,
        cancel_subscription,
    )

    user = _make_user()
    canceled = _make_subscription(status="canceled")
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result(None),       # active/cancel_pending 없음
            _scalar_result(canceled),   # canceled 있음
        ]
    )

    with pytest.raises(SubscriptionAlreadyCanceled):
        await cancel_subscription(user, "사유", db)


@pytest.mark.asyncio
async def test_cancel_no_subscription_raises():
    """모든 상태 0건 → SubscriptionNotFound."""
    from api.src.services.billing_service import (
        SubscriptionNotFound,
        cancel_subscription,
    )

    user = _make_user()
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result(None),
            _scalar_result(None),
        ]
    )

    with pytest.raises(SubscriptionNotFound):
        await cancel_subscription(user, "사유", db)


@pytest.mark.asyncio
async def test_cancel_notify_failure_does_not_block():
    """알림 실패해도 상태 전이는 commit됨."""
    from api.src.services.billing_service import cancel_subscription

    user = _make_user()
    sub = _make_subscription(status="active")
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalar_result(sub))
    db.commit = AsyncMock()

    notify_mock = AsyncMock(side_effect=RuntimeError("notify boom"))
    with patch(
        "api.src.services.billing_service._notify_subscription_event",
        notify_mock,
    ):
        result = await cancel_subscription(user, "사유", db)

    assert sub.status == "cancel_pending"
    assert result["status"] == "cancel_pending"
    db.commit.assert_awaited()


# ── resume_subscription ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resume_cancel_pending_to_active():
    """cancel_pending → active 복원, canceled_at/cancel_reason NULL."""
    from api.src.services.billing_service import resume_subscription

    user = _make_user()
    sub = _make_subscription(status="cancel_pending")
    sub.canceled_at = _now_utc() - timedelta(days=1)
    sub.cancel_reason = "기존 사유"
    expected_next_charge = sub.next_charge_at.isoformat()

    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalar_result(sub))
    db.commit = AsyncMock()

    with patch(
        "api.src.services.billing_service._notify_subscription_event",
        new=AsyncMock(),
    ):
        result = await resume_subscription(user, db)

    assert sub.status == "active"
    assert sub.canceled_at is None
    assert sub.cancel_reason is None
    assert result == {"status": "active", "next_charge_at": expected_next_charge}


@pytest.mark.asyncio
async def test_resume_cancel_pending_expired_raises():
    """cancel_pending && current_period_end < now → SubscriptionAlreadyCanceled."""
    from api.src.services.billing_service import (
        SubscriptionAlreadyCanceled,
        resume_subscription,
    )

    user = _make_user()
    sub = _make_subscription(status="cancel_pending", period_end_offset_days=-1)

    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalar_result(sub))

    with pytest.raises(SubscriptionAlreadyCanceled):
        await resume_subscription(user, db)


@pytest.mark.asyncio
async def test_resume_already_canceled_raises():
    """active/cancel_pending 0건 + canceled 1건 → SubscriptionAlreadyCanceled."""
    from api.src.services.billing_service import (
        SubscriptionAlreadyCanceled,
        resume_subscription,
    )

    user = _make_user()
    canceled = _make_subscription(status="canceled")
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result(None),
            _scalar_result(canceled),
        ]
    )

    with pytest.raises(SubscriptionAlreadyCanceled):
        await resume_subscription(user, db)


@pytest.mark.asyncio
async def test_resume_active_idempotent_noop():
    """active 입력 → 멱등 200, no-op, 알림 미호출."""
    from api.src.services.billing_service import resume_subscription

    user = _make_user()
    sub = _make_subscription(status="active")
    expected_next = sub.next_charge_at.isoformat()

    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalar_result(sub))
    db.commit = AsyncMock()

    notify_mock = AsyncMock()
    with patch(
        "api.src.services.billing_service._notify_subscription_event",
        notify_mock,
    ):
        result = await resume_subscription(user, db)

    assert result == {"status": "active", "next_charge_at": expected_next}
    notify_mock.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_resume_no_subscription_raises():
    """0건 → ResumeNotApplicable."""
    from api.src.services.billing_service import (
        ResumeNotApplicable,
        resume_subscription,
    )

    user = _make_user()
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result(None),
            _scalar_result(None),
        ]
    )

    with pytest.raises(ResumeNotApplicable):
        await resume_subscription(user, db)


# ── finalize_cancellations ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_finalize_expired_cancel_pending_to_canceled():
    """cancel_pending && expired 1건 → canceled + users.subscription_status='free' + next_charge_at NULL."""
    from api.src.services.billing_service import finalize_cancellations

    sub = _make_subscription(status="cancel_pending", period_end_offset_days=-1)

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalars_result([sub]),  # 스캔
            _scalar_result(sub),     # row-level lock
            MagicMock(),             # User update
        ]
    )
    db.commit = AsyncMock()

    with patch(
        "api.src.services.billing_service._notify_subscription_event",
        new=AsyncMock(),
    ):
        result = await finalize_cancellations(db)

    assert sub.status == "canceled"
    assert sub.next_charge_at is None
    assert result["scanned"] == 1
    assert result["finalized"] == 1
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_finalize_no_targets():
    """0건 → finalized=0, scanned=0."""
    from api.src.services.billing_service import finalize_cancellations

    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalars_result([]))

    result = await finalize_cancellations(db)

    assert result["scanned"] == 0
    assert result["finalized"] == 0


@pytest.mark.asyncio
async def test_finalize_skips_if_status_changed_during_relock():
    """relock 시점에 status 가 cancel_pending이 아니면 스킵."""
    from api.src.services.billing_service import finalize_cancellations

    sub = _make_subscription(status="cancel_pending", period_end_offset_days=-1)
    relocked = _make_subscription(status="active")  # 어디선가 active로 복원됨

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalars_result([sub]),
            _scalar_result(relocked),
        ]
    )
    db.commit = AsyncMock()

    result = await finalize_cancellations(db)

    assert result["scanned"] == 1
    assert result["finalized"] == 0


@pytest.mark.asyncio
async def test_finalize_notify_failure_does_not_block_other_records():
    """알림 실패해도 상태 전이는 commit됨(개별 트랜잭션)."""
    from api.src.services.billing_service import finalize_cancellations

    sub = _make_subscription(status="cancel_pending", period_end_offset_days=-1)

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalars_result([sub]),
            _scalar_result(sub),
            MagicMock(),
        ]
    )
    db.commit = AsyncMock()

    notify_mock = AsyncMock(side_effect=RuntimeError("boom"))
    with patch(
        "api.src.services.billing_service._notify_subscription_event",
        notify_mock,
    ):
        result = await finalize_cancellations(db)

    assert sub.status == "canceled"
    assert result["finalized"] == 1


# ── get_current_subscription ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_current_active():
    """active 1건 → status='active' 응답."""
    from api.src.services.billing_service import get_current_subscription

    user = _make_user()
    sub = _make_subscription(status="active")

    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalar_result(sub))

    result = await get_current_subscription(user, db)

    assert result["status"] == "active"
    assert result["started_at"] == sub.started_at.isoformat()
    assert result["current_period_end"] == sub.current_period_end.isoformat()
    assert result["next_charge_at"] == sub.next_charge_at.isoformat()
    assert result["canceled_at"] is None
    assert result["cancel_reason"] is None


@pytest.mark.asyncio
async def test_get_current_cancel_pending():
    """cancel_pending → status='cancel_pending' + canceled_at/cancel_reason."""
    from api.src.services.billing_service import get_current_subscription

    user = _make_user()
    sub = _make_subscription(status="cancel_pending")
    sub.canceled_at = _now_utc() - timedelta(days=1)
    sub.cancel_reason = "테스트"

    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalar_result(sub))

    result = await get_current_subscription(user, db)

    assert result["status"] == "cancel_pending"
    assert result["canceled_at"] == sub.canceled_at.isoformat()
    assert result["cancel_reason"] == "테스트"


@pytest.mark.asyncio
async def test_get_current_none_when_no_active():
    """0건 → status='none' + 모든 필드 None."""
    from api.src.services.billing_service import get_current_subscription

    user = _make_user()
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalar_result(None))

    result = await get_current_subscription(user, db)

    assert result == {
        "status": "none",
        "started_at": None,
        "current_period_end": None,
        "next_charge_at": None,
        "canceled_at": None,
        "cancel_reason": None,
    }


# ── _notify_subscription_event ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notify_subscription_event_calls_send():
    """정상 호출 → svc.send 호출 args 일치."""
    from api.src.services.billing_service import _notify_subscription_event

    user = _make_user()

    fake_session = AsyncMock()
    fake_session.execute = AsyncMock(return_value=_scalar_result(user))

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
            await _notify_subscription_event(
                user_id=user.id,
                template_code="subscription.cancel_requested",
                variables={"effective_at": "2026년 06월 30일"},
                idempotency_key="cancel_requested:50:1234",
            )

    svc_mock.send.assert_awaited_once()
    call_kwargs = svc_mock.send.await_args.kwargs
    assert call_kwargs["user_id"] == user.id
    assert call_kwargs["template_code"] == "subscription.cancel_requested"
    assert call_kwargs["idempotency_key"] == "cancel_requested:50:1234"


@pytest.mark.asyncio
async def test_notify_subscription_event_skips_withdrawn_user():
    """withdrawn user → svc.send 미호출(조용히 종료)."""
    from api.src.services.billing_service import _notify_subscription_event

    fake_session = AsyncMock()
    # withdrawn 조건 필터링으로 None 반환
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
            await _notify_subscription_event(
                user_id=10,
                template_code="subscription.cancel_requested",
                variables={"effective_at": "2026년 06월 30일"},
                idempotency_key="cancel_requested:50:1234",
            )

    svc_mock.send.assert_not_called()


@pytest.mark.asyncio
async def test_notify_subscription_event_swallows_send_exception():
    """svc.send 예외 → warning만 남기고 상위 전파 0."""
    from api.src.services.billing_service import _notify_subscription_event

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
            await _notify_subscription_event(
                user_id=user.id,
                template_code="subscription.cancel_requested",
                variables={"effective_at": "2026년 06월 30일"},
                idempotency_key="cancel_requested:50:1234",
            )
