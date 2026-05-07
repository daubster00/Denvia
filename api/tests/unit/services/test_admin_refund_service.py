"""Story 9.3 — admin_refund_service unit tests.

대상:
- _escape_ilike + _kst_date_range (재사용 헬퍼)
- approve / deny (PG mock 시나리오)
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api.src.services import admin_refund_service as svc


class TestEscapeIlike:
    def test_escape_percent(self):
        assert svc._escape_ilike("9900%") == "9900\\%"

    def test_escape_underscore(self):
        assert svc._escape_ilike("a_b") == "a\\_b"


class TestKstDateRange:
    def test_to_includes_full_day(self):
        _, e = svc._kst_date_range(None, date(2026, 5, 1))
        assert e is not None
        assert e.day == 2


class TestApproveQueueNotPending:
    @pytest.mark.asyncio
    async def test_approve_returns_409_when_already_processed(self):
        queue = MagicMock()
        queue.id = 42
        queue.status = "approved"  # 이미 처리됨
        payment = MagicMock()
        payment.id = 1234

        async def fake_lock(_db, _qid):
            return queue, payment

        request = MagicMock()
        request.state = MagicMock()
        db = MagicMock()
        db.commit = AsyncMock()

        with patch.object(svc, "_lock_queue_and_payment", new=fake_lock):
            with pytest.raises(HTTPException) as exc:
                await svc.approve(request, db, 42, "ok", admin_id=1)

        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "QUEUE_NOT_PENDING"


class TestApprovePaymentNotRefundable:
    @pytest.mark.asyncio
    async def test_approve_returns_409_when_payment_failed(self):
        queue = MagicMock()
        queue.status = "pending"
        payment = MagicMock()
        payment.status = "failed"  # 환불 불가

        async def fake_lock(_db, _qid):
            return queue, payment

        request = MagicMock()
        request.state = MagicMock()
        db = MagicMock()

        with patch.object(svc, "_lock_queue_and_payment", new=fake_lock):
            with pytest.raises(HTTPException) as exc:
                await svc.approve(request, db, 42, "ok", admin_id=1)

        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "PAYMENT_NOT_REFUNDABLE"


class TestApprovePgFailureRaises502:
    @pytest.mark.asyncio
    async def test_approve_pg_4xx_raises_502_with_pg_error(self):
        queue = MagicMock()
        queue.status = "pending"
        payment = MagicMock()
        payment.id = 1234
        payment.status = "refund_pending"
        payment.provider_order_id = "order_1234"
        payment.amount_krw = 9900

        async def fake_lock(_db, _qid):
            return queue, payment

        pg_mock = MagicMock()
        pg_mock.refund = AsyncMock(
            return_value={
                "success": False,
                "raw_response": {"code": "INVALID_PAYMENT", "message": "결제 정보 오류"},
            }
        )
        request = MagicMock()
        request.state = MagicMock()
        db = MagicMock()
        db.commit = AsyncMock()
        db.add = MagicMock()

        with (
            patch.object(svc, "_lock_queue_and_payment", new=fake_lock),
            patch.object(svc, "get_pg_provider", return_value=pg_mock),
        ):
            with pytest.raises(HTTPException) as exc:
                await svc.approve(request, db, 42, "정상 환불", admin_id=1)

        assert exc.value.status_code == 502
        assert exc.value.detail["code"] == "PG_REFUND_FAILED"
        assert exc.value.detail["pg_error_code"] == "INVALID_PAYMENT"


class TestDenyHappyPath:
    @pytest.mark.asyncio
    async def test_deny_transitions_payment_to_success(self):
        queue = MagicMock()
        queue.id = 42
        queue.status = "pending"
        queue.reason = None
        payment = MagicMock()
        payment.id = 1234
        payment.user_id = 7
        payment.status = "refund_pending"
        payment.amount_krw = 9900

        async def fake_lock(_db, _qid):
            return queue, payment

        request = MagicMock()
        request.state = MagicMock()
        db = MagicMock()
        db.commit = AsyncMock()
        db.add = MagicMock()

        # _fetch_reason_code가 DB 쿼리하지 않도록 mock
        with (
            patch.object(svc, "_lock_queue_and_payment", new=fake_lock),
            patch.object(svc, "_fetch_reason_code", new=AsyncMock(return_value="both")),
        ):
            result = await svc.deny(request, db, 42, "사용자 사유 부적합", admin_id=1)

        assert result.queue_id == 42
        assert result.status == "denied"
        assert result.refunded_at is None
        # payment.status 원복 (refund_pending → success)
        assert payment.status == "success"
        # queue 마감
        assert queue.status == "denied"
        assert queue.reviewer_user_id == 1
        assert queue.reviewer_note == "사용자 사유 부적합"


class TestDenyPaymentNotRefundPending:
    """payment.status 가 refund_pending 이 아닌 상태에서 거부 시도 → 409.

    queue 가 pending 으로 남아 있더라도, payment 가 이미 refunded/failed/success 등으로
    전이된 경우 deny 가 그것을 success 로 되살리는 사고를 방지하기 위한 가드.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("current_status", ["refunded", "failed", "success", "pending"])
    async def test_deny_returns_409_when_payment_not_refund_pending(self, current_status):
        queue = MagicMock()
        queue.id = 42
        queue.status = "pending"
        payment = MagicMock()
        payment.id = 1234
        payment.status = current_status
        original_status = current_status

        async def fake_lock(_db, _qid):
            return queue, payment

        request = MagicMock()
        request.state = MagicMock()
        db = MagicMock()
        db.commit = AsyncMock()
        db.add = MagicMock()

        with patch.object(svc, "_lock_queue_and_payment", new=fake_lock):
            with pytest.raises(HTTPException) as exc:
                await svc.deny(request, db, 42, "거부 사유", admin_id=1)

        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "PAYMENT_NOT_REFUND_PENDING"
        assert exc.value.detail["current_status"] == current_status
        # payment.status 가 변경되지 않아야 한다 (success 등으로 되살리는 사고 방지).
        assert payment.status == original_status
        # queue 도 그대로
        assert queue.status == "pending"
        # commit 되어선 안 됨
        db.commit.assert_not_called()


class TestApproveInboxBodyUsesKstDate:
    """KST 자정~오전 9시 사이에 처리되면 UTC 날짜는 전날이지만 사용자에게는 KST 기준 처리일이 보여야 한다."""

    @pytest.mark.asyncio
    async def test_approve_inbox_body_uses_kst_date_around_kst_midnight(self):
        queue = MagicMock()
        queue.id = 42
        queue.status = "pending"
        payment = MagicMock()
        payment.id = 1234
        payment.user_id = 7
        payment.status = "refund_pending"
        payment.subscription_id = None
        payment.amount_krw = 9900
        payment.provider_order_id = "order_1234"

        async def fake_lock(_db, _qid):
            return queue, payment

        pg_mock = MagicMock()
        pg_mock.refund = AsyncMock(
            return_value={"success": True, "raw_response": {"status": "CANCELED"}}
        )

        request = MagicMock()
        request.state = MagicMock()
        db = MagicMock()
        db.commit = AsyncMock()
        db.execute = AsyncMock()
        db.add = MagicMock()

        # UTC 2026-05-06 23:00 → KST 2026-05-07 08:00 (날짜 차이가 발생하는 경계)
        fixed_utc = datetime(2026, 5, 6, 23, 0, tzinfo=UTC)

        class _DT(datetime):
            @classmethod
            def now(cls, tz=None):  # type: ignore[override]
                if tz is None:
                    return fixed_utc.replace(tzinfo=None)
                return fixed_utc.astimezone(tz)

        with (
            patch.object(svc, "_lock_queue_and_payment", new=fake_lock),
            patch.object(svc, "get_pg_provider", return_value=pg_mock),
            patch.object(svc, "_fetch_reason_code", new=AsyncMock(return_value="both")),
            patch.object(svc, "datetime", _DT),
        ):
            await svc.approve(request, db, 42, "정상 환불", admin_id=1)

        inbox_calls = [
            call_args
            for call_args in db.add.call_args_list
            if call_args.args and getattr(call_args.args[0], "title", None) == svc._INBOX_TITLE_APPROVED
        ]
        assert inbox_calls, "InboxMessage(approved) 가 add 되어야 한다"
        body_html = inbox_calls[0].args[0].body_html
        # KST 기준 2026년 05월 07일이 본문에 포함되어야 함 (UTC 기준 06일이 아니라)
        assert "2026년 05월 07일" in body_html
        assert "2026년 05월 06일" not in body_html


def _async_session_factory(session: MagicMock) -> MagicMock:
    """기존 retention_tasks 테스트 패턴 답습 — async with 컨텍스트로 session 을 내려준다."""
    factory = MagicMock()

    class _Ctx:
        async def __aenter__(self_inner):
            return session

        async def __aexit__(self_inner, *exc):
            return False

    factory.return_value = _Ctx()
    return factory


class TestNotifyRefundApprovedKst:
    """알림톡 effective_at 도 KST 날짜로 변환되어야 한다."""

    @pytest.mark.asyncio
    async def test_notify_uses_kst_date(self):
        # UTC 2026-05-06 23:00 == KST 2026-05-07 08:00 — 날짜 경계가 변하는 시각
        refunded_at = datetime(2026, 5, 6, 23, 0, tzinfo=UTC)

        user_mock = MagicMock()
        user_mock.phone = "01012345678"
        user_mock.withdrawn_at = None

        execute_result = MagicMock()
        execute_result.scalar_one_or_none = MagicMock(return_value=user_mock)

        session = MagicMock()
        session.execute = AsyncMock(return_value=execute_result)

        notification_svc = MagicMock()
        notification_svc.send = AsyncMock()

        with (
            patch(
                "api.src.models.base.async_session_factory",
                _async_session_factory(session),
            ),
            patch(
                "api.src.integrations.messaging.notification_service.get_notification_service",
                return_value=notification_svc,
            ),
        ):
            await svc.notify_refund_approved(
                user_id=7, payment_id=1234, amount_krw=9900, refunded_at=refunded_at
            )

        notification_svc.send.assert_awaited_once()
        kwargs = notification_svc.send.await_args.kwargs
        assert kwargs["variables"]["effective_at"] == "2026년 05월 07일"
