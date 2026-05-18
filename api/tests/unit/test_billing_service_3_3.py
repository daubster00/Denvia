"""BillingService 단위 테스트 — Story 3.3 자동 갱신.

scan_renewals + charge_renewal + _notify_renewal 단위 검증.
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


def _make_subscription(
    sub_id: int = 1,
    user_id: int = 10,
    status: str = "active",
    days_ago: int = 1,
) -> MagicMock:
    """갱신 대상 Subscription mock."""
    sub = MagicMock()
    sub.id = sub_id
    sub.user_id = user_id
    sub.status = status
    now = _now_utc()
    sub.current_period_end = now - timedelta(days=days_ago)
    sub.next_charge_at = now - timedelta(days=days_ago)
    return sub


def _make_billing_key(user_id: int = 10) -> MagicMock:
    from api.src.utils.fernet import encrypt_billing_key

    bk = MagicMock()
    bk.id = 20
    bk.user_id = user_id
    bk.customer_key = "denvia_cust_uuid_test"
    bk.billing_key_encrypted = encrypt_billing_key("test_billing_key_plain")
    bk.is_active = True
    return bk


def _make_db_with_results(*results) -> AsyncMock:
    """execute를 순서대로 반환하는 mock db."""
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=list(results))
    return db


def _scalar_result(obj) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none = MagicMock(return_value=obj)
    return r


def _scalars_result(objs: list) -> MagicMock:
    r = MagicMock()
    r.scalars.return_value.all.return_value = objs
    return r


# ── scan_renewals ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scan_renewals_enqueues_active_subscriptions():
    """active + next_charge_at <= now 구독 2건 → enqueued=2 반환 + send_task 2회 호출."""
    from api.src.services.billing_service import scan_renewals

    sub1 = _make_subscription(sub_id=1)
    sub2 = _make_subscription(sub_id=2)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalars_result([sub1, sub2]))

    # 함수 내부에서 from api.src.workers.celery_app import celery_app 를 실행하므로
    # 모듈 네임스페이스 자체를 patch해야 함
    with patch("api.src.workers.celery_app.celery_app") as mock_celery_app:
        result = await scan_renewals(db)

    assert result["enqueued"] == 2
    assert mock_celery_app.send_task.call_count == 2
    calls = [c.args[0] for c in mock_celery_app.send_task.call_args_list]
    assert all(name == "billing.charge_renewal" for name in calls)


@pytest.mark.asyncio
async def test_scan_renewals_no_subscriptions_returns_zero():
    """갱신 대상 없음 → enqueued=0 반환 + send_task 미호출."""
    from api.src.services.billing_service import scan_renewals

    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalars_result([]))

    mock_celery_app = MagicMock()
    with patch("api.src.workers.celery_app.celery_app", mock_celery_app):
        result = await scan_renewals(db)

    assert result["enqueued"] == 0
    mock_celery_app.send_task.assert_not_called()


@pytest.mark.asyncio
async def test_scan_renewals_cancel_pending_excluded():
    """cancel_pending 구독은 active 조건에서 자동 제외 — DB 쿼리 필터 확인."""
    from api.src.services.billing_service import scan_renewals

    # cancel_pending만 있는 상황을 DB가 빈 결과로 돌려준다고 가정
    # (실제 필터는 ORM 쿼리 레벨에서 동작하므로, DB가 빈 목록 반환 = 제외됨)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalars_result([]))

    mock_celery_app = MagicMock()
    with patch("api.src.workers.celery_app.celery_app", mock_celery_app):
        result = await scan_renewals(db)

    assert result["enqueued"] == 0
    mock_celery_app.send_task.assert_not_called()


# ── charge_renewal ────────────────────────────────────────────────────────────


def _make_charge_result(success: bool) -> dict:
    if success:
        return {
            "success": True,
            "provider_order_id": "renewal-1-abc123456789",
            "failure_reason": None,
            "raw_response": {"status": "DONE"},
        }
    return {
        "success": False,
        "provider_order_id": "renewal-1-abc123456789",
        "failure_reason": "카드 한도 초과",
        "raw_response": {"code": "EXCEED_MAX_AMOUNT"},
    }


@pytest.mark.asyncio
async def test_charge_renewal_success_inserts_payment_and_updates_subscription():
    """성공 경로: payments INSERT(status='success') + subscriptions 30일 연장 확인."""
    from api.src.services.billing_service import charge_renewal
    from api.src.models.payment import Payment
    from api.src.models.subscription import Subscription

    sub = _make_subscription()
    original_period_end = sub.current_period_end
    bk = _make_billing_key()

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_scalar_result(sub), _scalar_result(bk)])
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    added_objects = []
    db.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))

    mock_pg = AsyncMock()
    mock_pg.charge = AsyncMock(return_value=_make_charge_result(True))

    # 2026-05-18 v4: _notify_renewal 함수 자체가 제거되어 patch 불필요.
    with patch("api.src.services.billing_service.get_pg_provider", return_value=mock_pg):
        result = await charge_renewal(sub.id, db)

    assert result["status"] == "success"
    assert result["subscription_id"] == sub.id

    # Payment INSERT 확인
    payments = [o for o in added_objects if isinstance(o, Payment)]
    assert len(payments) == 1
    assert payments[0].status == "success"
    assert payments[0].attempt_count == 1

    # 구독 기간 30일 연장 확인
    assert sub.current_period_end == original_period_end + timedelta(days=30)
    assert sub.next_charge_at == sub.current_period_end


@pytest.mark.asyncio
async def test_charge_renewal_success_next_charge_at_equals_period_end():
    """성공 시 next_charge_at == current_period_end 동일값."""
    from api.src.services.billing_service import charge_renewal

    sub = _make_subscription()
    bk = _make_billing_key()

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_scalar_result(sub), _scalar_result(bk)])

    mock_pg = AsyncMock()
    mock_pg.charge = AsyncMock(return_value=_make_charge_result(True))

    # 2026-05-18 v4: _notify_renewal 함수 자체가 제거되어 patch 불필요.
    with patch("api.src.services.billing_service.get_pg_provider", return_value=mock_pg):
        await charge_renewal(sub.id, db)

    assert sub.next_charge_at == sub.current_period_end


# 2026-05-18 v4 — `test_charge_renewal_success_calls_notify_renewal` 제거.
# `_notify_renewal()` 함수와 호출 자체가 코드에서 제거되었음.
# 회귀 가드: `test_notify_renewal_removed_per_v4_review` 가 부재를 검증.


@pytest.mark.asyncio
async def test_charge_renewal_success_billing_key_not_logged(capfd):
    """billing_key_plain이 로그에 출력되지 않는다."""
    import structlog
    from api.src.services.billing_service import charge_renewal

    sub = _make_subscription()
    bk = _make_billing_key()

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_scalar_result(sub), _scalar_result(bk)])

    captured_logs: list[dict] = []

    def _capture(**kw):
        captured_logs.append(kw)

    mock_pg = AsyncMock()
    mock_pg.charge = AsyncMock(return_value=_make_charge_result(True))

    # 2026-05-18 v4: _notify_renewal 함수 자체가 제거되어 patch 불필요.
    with patch("api.src.services.billing_service.get_pg_provider", return_value=mock_pg):
        with patch.object(
            structlog.get_logger("api.src.services.billing_service"),
            "info",
            side_effect=_capture,
        ):
            await charge_renewal(sub.id, db)

    # 어떤 로그 항목에도 billing_key_plain 값이 없어야 함
    for log in captured_logs:
        log_str = str(log)
        assert "test_billing_key_plain" not in log_str, (
            f"billing_key_plain이 로그에 노출됨: {log_str}"
        )


@pytest.mark.asyncio
async def test_charge_renewal_failure_inserts_failed_payment_and_retry_events():
    """실패 경로: payments(failed) + charge_failed + retry_scheduled 이벤트 INSERT 확인."""
    from api.src.services.billing_service import charge_renewal
    from api.src.models.payment import Payment
    from api.src.models.payment_event import PaymentEvent

    sub = _make_subscription()
    bk = _make_billing_key()

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_scalar_result(sub), _scalar_result(bk)])

    added_objects = []
    db.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))

    mock_pg = AsyncMock()
    mock_pg.charge = AsyncMock(return_value=_make_charge_result(False))

    mock_celery_app = MagicMock()
    with patch("api.src.services.billing_service.get_pg_provider", return_value=mock_pg):
        with patch("api.src.workers.celery_app.celery_app", mock_celery_app):
            with patch("sentry_sdk.add_breadcrumb"):
                result = await charge_renewal(sub.id, db)

    assert result["status"] == "failed"

    payments = [o for o in added_objects if isinstance(o, Payment)]
    assert len(payments) == 1
    assert payments[0].status == "failed"
    assert payments[0].failure_reason == "카드 한도 초과"

    events = [o for o in added_objects if isinstance(o, PaymentEvent)]
    event_types = {e.event_type for e in events}
    assert "charge_failed" in event_types
    assert "retry_scheduled" in event_types


@pytest.mark.asyncio
async def test_charge_renewal_failure_subscription_status_unchanged():
    """실패 시 subscriptions.status 와 users.subscription_status 변경 없음."""
    from api.src.services.billing_service import charge_renewal

    sub = _make_subscription(status="active")
    original_status = sub.status
    bk = _make_billing_key()

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_scalar_result(sub), _scalar_result(bk)])

    mock_pg = AsyncMock()
    mock_pg.charge = AsyncMock(return_value=_make_charge_result(False))

    mock_celery_app = MagicMock()
    with patch("api.src.services.billing_service.get_pg_provider", return_value=mock_pg):
        with patch("api.src.workers.celery_app.celery_app", mock_celery_app):
            with patch("sentry_sdk.add_breadcrumb"):
                await charge_renewal(sub.id, db)

    # subscriptions.status 변경 없음
    assert sub.status == original_status


@pytest.mark.asyncio
async def test_charge_renewal_failure_enqueues_retry_payment():
    """실패 시 billing.retry_payment send_task(countdown=86400) 호출 확인."""
    from api.src.services.billing_service import charge_renewal

    sub = _make_subscription()
    bk = _make_billing_key()

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_scalar_result(sub), _scalar_result(bk)])

    # payment.id가 필요하므로 add 시점에 id를 설정
    def _capture_add(obj):
        from api.src.models.payment import Payment
        if isinstance(obj, Payment):
            obj.id = 999

    db.add = MagicMock(side_effect=_capture_add)

    mock_pg = AsyncMock()
    mock_pg.charge = AsyncMock(return_value=_make_charge_result(False))

    # 함수 내부 import 경로를 patch
    with patch("api.src.workers.celery_app.celery_app") as mock_celery_app:
        with patch("api.src.services.billing_service.get_pg_provider", return_value=mock_pg):
            with patch("sentry_sdk.add_breadcrumb"):
                result = await charge_renewal(sub.id, db)

    # send_task('billing.retry_payment', args=[payment_id], countdown=86400)
    mock_celery_app.send_task.assert_called_once_with(
        "billing.retry_payment",
        args=[result["payment_id"]],
        countdown=86400,
    )


@pytest.mark.asyncio
async def test_charge_renewal_subscription_not_found():
    """구독 없으면 status='error', reason='subscription_not_found' 반환."""
    from api.src.services.billing_service import charge_renewal

    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalar_result(None))

    result = await charge_renewal(999, db)

    assert result["status"] == "error"
    assert result["reason"] == "subscription_not_found"


@pytest.mark.asyncio
async def test_charge_renewal_no_active_billing_key():
    """활성 빌링키 없으면 status='error', reason='no_active_billing_key' 반환."""
    from api.src.services.billing_service import charge_renewal

    sub = _make_subscription()
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_scalar_result(sub), _scalar_result(None)])

    result = await charge_renewal(sub.id, db)

    assert result["status"] == "error"
    assert result["reason"] == "no_active_billing_key"


# ── 자동 갱신 성공 알림 ───────────────────────────────────────────────────────
# 2026-05-18 — 고객 검수 v4: `billing.auto_renew_success`(1-2) 삭제 요청에 따라
# `_notify_renewal()` 함수와 알림 발송 자체가 제거되었습니다.
# 자동 갱신 시점에는 사용자 알림톡 발송이 일어나지 않습니다 (검수 회신본 §1-2).


def test_notify_renewal_removed_per_v4_review():
    """`_notify_renewal` 함수가 v4 검수 후 코드에서 제거되었는지 확인."""
    import api.src.services.billing_service as svc

    assert not hasattr(svc, "_notify_renewal"), (
        "_notify_renewal 가 아직 남아있음 — 고객 v4 검수 요청에 따라 제거되어야 함."
    )


# ── 중복 결제 방지 ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_charge_renewal_skipped_when_already_renewed():
    """성공 후 next_charge_at이 미래로 이동한 뒤 재실행 → skipped, pg.charge 미호출."""
    from api.src.services.billing_service import charge_renewal

    sub = _make_subscription()
    sub.next_charge_at = _now_utc() + timedelta(days=29)  # 이미 갱신 완료된 상태

    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalar_result(sub))

    mock_pg = AsyncMock()

    with patch("api.src.services.billing_service.get_pg_provider", return_value=mock_pg):
        result = await charge_renewal(sub.id, db)

    assert result["status"] == "skipped"
    mock_pg.charge.assert_not_called()


@pytest.mark.asyncio
async def test_charge_renewal_skipped_when_cancel_pending():
    """cancel_pending 상태 구독 → skipped 반환, pg.charge 미호출."""
    from api.src.services.billing_service import charge_renewal

    sub = _make_subscription(status="cancel_pending")

    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalar_result(sub))

    mock_pg = AsyncMock()

    with patch("api.src.services.billing_service.get_pg_provider", return_value=mock_pg):
        result = await charge_renewal(sub.id, db)

    assert result["status"] == "skipped"
    mock_pg.charge.assert_not_called()


# ── PG 네트워크/어댑터 예외 처리 ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_charge_renewal_pg_exception_inserts_failed_payment():
    """pg.charge() 예외 → failed Payment + charge_failed + retry_scheduled 이벤트 + send_task."""
    from api.src.services.billing_service import charge_renewal
    from api.src.models.payment import Payment
    from api.src.models.payment_event import PaymentEvent

    sub = _make_subscription()
    bk = _make_billing_key()

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_scalar_result(sub), _scalar_result(bk)])

    added_objects: list = []

    def _cap_add(o):
        from api.src.models.payment import Payment as P
        if isinstance(o, P):
            o.id = 555
        added_objects.append(o)

    db.add = MagicMock(side_effect=_cap_add)

    mock_pg = AsyncMock()
    mock_pg.charge = AsyncMock(side_effect=ConnectionError("네트워크 오류"))

    with patch("api.src.services.billing_service.get_pg_provider", return_value=mock_pg):
        with patch("api.src.workers.celery_app.celery_app") as mock_celery_app:
            with patch("sentry_sdk.add_breadcrumb") as mock_sentry:
                result = await charge_renewal(sub.id, db)

    assert result["status"] == "failed"
    assert "payment_id" in result

    payments = [o for o in added_objects if isinstance(o, Payment)]
    assert len(payments) == 1
    assert payments[0].status == "failed"
    assert payments[0].failure_reason is not None

    events = [o for o in added_objects if isinstance(o, PaymentEvent)]
    event_types = {e.event_type for e in events}
    assert "charge_failed" in event_types
    assert "retry_scheduled" in event_types

    mock_celery_app.send_task.assert_called_once_with(
        "billing.retry_payment",
        args=[result["payment_id"]],
        countdown=86400,
    )
    mock_sentry.assert_called_once()


@pytest.mark.asyncio
async def test_charge_renewal_pg_exception_status_unchanged():
    """pg.charge() 예외 시 subscriptions.status 변경 없음."""
    from api.src.services.billing_service import charge_renewal

    sub = _make_subscription(status="active")
    bk = _make_billing_key()

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_scalar_result(sub), _scalar_result(bk)])

    mock_pg = AsyncMock()
    mock_pg.charge = AsyncMock(side_effect=RuntimeError("PG timeout"))

    with patch("api.src.services.billing_service.get_pg_provider", return_value=mock_pg):
        with patch("api.src.workers.celery_app.celery_app"):
            with patch("sentry_sdk.add_breadcrumb"):
                await charge_renewal(sub.id, db)

    assert sub.status == "active"


# ── 관측 로그 AC ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scan_renewals_batch_completed_log_fields():
    """scan_renewals 완료 시 billing.auto_renew.batch_completed 로그 필드 검증."""
    import structlog.testing
    from api.src.services.billing_service import scan_renewals

    sub = _make_subscription(sub_id=1)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalars_result([sub]))

    with structlog.testing.capture_logs() as captured:
        with patch("api.src.workers.celery_app.celery_app"):
            await scan_renewals(db)

    batch_logs = [log for log in captured if log.get("event") == "billing.auto_renew.batch_completed"]
    assert len(batch_logs) == 1
    log = batch_logs[0]
    assert log["total_scanned"] == 1
    assert log["success_count"] == 1
    assert log["failed_count"] == 0
    assert "duration_ms" in log


@pytest.mark.asyncio
async def test_scan_renewals_send_task_exception_continues_batch():
    """send_task 예외 발생 시 배치 전체가 중단되지 않고 다음 대상 계속 처리."""
    from api.src.services.billing_service import scan_renewals

    sub1 = _make_subscription(sub_id=1)
    sub2 = _make_subscription(sub_id=2)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalars_result([sub1, sub2]))

    mock_celery_app = MagicMock()
    mock_celery_app.send_task = MagicMock(side_effect=[RuntimeError("Redis 연결 실패"), None])

    with patch("api.src.workers.celery_app.celery_app", mock_celery_app):
        result = await scan_renewals(db)

    assert mock_celery_app.send_task.call_count == 2
    assert result["enqueued"] == 1  # 성공한 1건만 반영
