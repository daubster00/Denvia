"""AdminPaymentService 단위 테스트 — Story 9.1 v1.1 (ADR-0001 편차 #5).

대상: `api.src.services.admin_payment_service.create_refund` (T9, T11).

테스트 범위:
1. 정상 흐름 — 전액 단발 / 부분 1회 / 부분 2회 누적(잔액 0 도달) / partial 시 subscription 미전이.
2. 409 분기 — PAYMENT_NOT_REFUNDABLE / NO_REFUNDABLE_BALANCE / CANCEL_AMOUNT_EXCEEDS_BALANCE.
3. 502 분기 — transport 장애(PG_REFUND_UNAVAILABLE + rollback) / PG 4xx(PG_REFUND_FAILED +
   refund_denied 이벤트 보존 + commit).
4. 멱등 키 패턴 — `refund:{payment_id}:manual:{sequence}` 형태 검증.
5. UNIQUE race — commit IntegrityError → REFUND_RACE_DETECTED 409.

테스트 전략:
- DB는 `FakeDB`로 stateful mock. execute 결과를 큐로 미리 등록하고 add/commit/rollback을
  카운트한다. `Refund.id`는 commit 시점이 아닌 db.add 시점에 주입(simpler than 실 SQLAlchemy
  flush 시뮬레이션).
- PG는 `pg.refund`만 mocking — 모듈의 `get_pg_provider`를 patch.
- 후처리 알림톡·Redis publish는 라우터 책임이므로 본 단위 테스트 범위가 아님 (별도 통합 테스트).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from api.src.models.inbox_message import InboxMessage
from api.src.models.payment_event import PaymentEvent
from api.src.models.refund import Refund
from api.src.schemas.admin.payment_refunds import RefundCreateRequest
from api.src.services import admin_payment_service


_NOW = datetime.now(UTC)


def _make_payment(
    payment_id: int = 200,
    user_id: int = 10,
    subscription_id: int | None = 50,
    status: str = "success",
    amount_krw: int = 19800,
    provider_order_id: str = "denvia-pro-test-200",
) -> MagicMock:
    p = MagicMock()
    p.id = payment_id
    p.user_id = user_id
    p.subscription_id = subscription_id
    p.status = status
    p.amount_krw = amount_krw
    p.provider_order_id = provider_order_id
    p.charged_at = _NOW - timedelta(days=2)
    return p


def _make_subscription(sub_id: int = 50, status: str = "active") -> MagicMock:
    sub = MagicMock()
    sub.id = sub_id
    sub.status = status
    sub.next_charge_at = _NOW + timedelta(days=20)
    sub.canceled_at = None
    sub.cancel_reason = None
    return sub


def _make_request() -> MagicMock:
    req = MagicMock()
    req.state = SimpleNamespace()
    return req


class FakeDB:
    """create_refund 전용 stateful mock.

    execute는 큐된 결과를 순차 반환. add는 _added에 누적하고 Refund면 _next_refund_id를
    부여한다. commit/rollback은 카운트만 한다. commit 시 예외를 던지도록 설정할 수 있다.
    """

    def __init__(self) -> None:
        self._execute_queue: list = []
        self._added: list = []
        self.commits = 0
        self.rollbacks = 0
        self._commit_exc: BaseException | None = None
        self._next_refund_id: int = 42

    def queue_scalar(self, value) -> "FakeDB":
        r = MagicMock()
        r.scalar_one_or_none = MagicMock(return_value=value)
        r.scalar_one = MagicMock(return_value=value)
        self._execute_queue.append(r)
        return self

    def queue_row(self, *values) -> "FakeDB":
        r = MagicMock()
        r.one = MagicMock(return_value=tuple(values))
        self._execute_queue.append(r)
        return self

    def queue_noop(self) -> "FakeDB":
        self._execute_queue.append(MagicMock())
        return self

    def raise_on_commit(self, exc: BaseException) -> "FakeDB":
        self._commit_exc = exc
        return self

    async def execute(self, _stmt):
        if not self._execute_queue:
            return MagicMock()
        return self._execute_queue.pop(0)

    def add(self, obj) -> None:
        if isinstance(obj, Refund) and obj.id is None:
            obj.id = self._next_refund_id
            self._next_refund_id += 1
        self._added.append(obj)

    async def commit(self) -> None:
        if self._commit_exc is not None:
            raise self._commit_exc
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    @property
    def added(self) -> list:
        return self._added

    def added_of(self, cls) -> list:
        return [a for a in self._added if isinstance(a, cls)]


def _make_pg(success: bool = True, raw: dict | None = None, raise_exc: bool = False):
    pg = MagicMock()
    if raise_exc:
        pg.refund = AsyncMock(side_effect=RuntimeError("transport down"))
    else:
        pg.refund = AsyncMock(
            return_value={
                "success": success,
                "raw_response": raw or ({"status": "DONE"} if success else {"code": "X"}),
            }
        )
    return pg


# ── 정상 흐름 ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_refund_full_single_shot_transitions_payment_and_subscription():
    """sequence=1 + 전액 → status='refunded' + subscription canceled + user free + refund_kind='manual_full'."""
    payment = _make_payment(amount_krw=19800)
    sub = _make_subscription()
    db = FakeDB()
    db.queue_scalar(payment)           # SELECT Payment FOR UPDATE
    db.queue_row(0, 0)                 # _aggregate_refunds
    db.queue_scalar(sub)               # SELECT Subscription FOR UPDATE (전액이라 호출됨)
    db.queue_noop()                    # UPDATE User → free

    payload = RefundCreateRequest(
        cancel_amount=19800, reason_category="customer_complaint", memo="full refund"
    )
    request = _make_request()

    with patch.object(admin_payment_service, "get_pg_provider", return_value=_make_pg()):
        result = await admin_payment_service.create_refund(
            request, db, 200, payload, admin_id=1
        )

    # 응답
    assert result.refund_id == 42
    assert result.refund_sequence == 1
    assert result.cancel_amount == 19800
    # payment·subscription·user 전이
    assert payment.status == "refunded"
    assert sub.status == "canceled"
    assert sub.next_charge_at is None
    assert sub.cancel_reason == "manual_admin_refund"
    # 환불 row + payment_event refund_success + inbox 1건
    refunds = db.added_of(Refund)
    assert len(refunds) == 1
    assert refunds[0].refund_sequence == 1
    assert refunds[0].idempotency_key == "refund:200:manual:1"
    events = [e for e in db.added_of(PaymentEvent) if e.event_type == "refund_success"]
    assert len(events) == 1
    assert events[0].raw_response_json["refund_kind"] == "manual_full"
    inbox = db.added_of(InboxMessage)
    assert len(inbox) == 1
    assert "전액" in inbox[0].title or "환불" in inbox[0].title
    # request.state 후처리 페이로드
    assert request.state.audit_action == "refund.operational.create"
    assert request.state.refund_op_refund_reason == "manual_full"
    assert db.commits == 1


@pytest.mark.asyncio
async def test_create_refund_partial_first_keeps_payment_and_subscription():
    """sequence=1 + 부분 → status='success' 유지, subscription 미전이, refund_kind='manual_partial'."""
    payment = _make_payment(amount_krw=19800)
    db = FakeDB()
    db.queue_scalar(payment)
    db.queue_row(0, 0)
    # 부분이라 Subscription/User execute는 호출되지 않음

    payload = RefundCreateRequest(
        cancel_amount=5000, reason_category="duplicate_payment"
    )
    request = _make_request()

    with patch.object(admin_payment_service, "get_pg_provider", return_value=_make_pg()):
        result = await admin_payment_service.create_refund(
            request, db, 200, payload, admin_id=1
        )

    assert result.refund_sequence == 1
    assert result.cancel_amount == 5000
    # payment 변경 없음 — partial은 success 유지
    assert payment.status == "success"
    # subscription select가 호출되지 않았음을 큐 잔량으로 확인
    assert db._execute_queue == []  # 모두 소비됨 (전액 분기였다면 2개 더 남았어야)
    events = [e for e in db.added_of(PaymentEvent) if e.event_type == "refund_success"]
    assert events[0].raw_response_json["refund_kind"] == "manual_partial"


@pytest.mark.asyncio
async def test_create_refund_partial_second_reaches_zero_balance_transitions_status():
    """2회 누적: 1차 5000 후 2차 14800 → 잔액 0, payment='refunded', subscription canceled.

    sequence=2이므로 단발 전액이 아니어서 refund_kind='manual_partial' (회계 구분).
    """
    payment = _make_payment(amount_krw=19800)
    sub = _make_subscription()
    db = FakeDB()
    db.queue_scalar(payment)
    db.queue_row(5000, 1)              # 이미 1차 5000 환불됨, sequence=1까지 사용
    db.queue_scalar(sub)               # 전액 도달이라 subscription select 호출
    db.queue_noop()                    # user update

    payload = RefundCreateRequest(
        cancel_amount=14800, reason_category="system_error"
    )
    request = _make_request()

    with patch.object(admin_payment_service, "get_pg_provider", return_value=_make_pg()):
        result = await admin_payment_service.create_refund(
            request, db, 200, payload, admin_id=1
        )

    assert result.refund_sequence == 2
    assert payment.status == "refunded"
    assert sub.status == "canceled"
    refunds = db.added_of(Refund)
    assert refunds[0].idempotency_key == "refund:200:manual:2"
    events = [e for e in db.added_of(PaymentEvent) if e.event_type == "refund_success"]
    # 누적 잔액 0이지만 단발 전액이 아니어서 manual_partial로 분류
    assert events[0].raw_response_json["refund_kind"] == "manual_partial"


# ── 409 분기 ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_refund_payment_not_found_raises_404():
    """payment_id 미존재 → 404."""
    db = FakeDB()
    db.queue_scalar(None)

    payload = RefundCreateRequest(cancel_amount=1000, reason_category="other")
    with pytest.raises(HTTPException) as exc_info:
        await admin_payment_service.create_refund(
            _make_request(), db, 99999, payload, admin_id=1
        )
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["code"] == "PAYMENT_NOT_FOUND"


@pytest.mark.asyncio
async def test_create_refund_payment_not_refundable_status_raises_409():
    """payment.status != 'success' → 409 PAYMENT_NOT_REFUNDABLE (current_status 동봉)."""
    payment = _make_payment(status="refund_pending")
    db = FakeDB()
    db.queue_scalar(payment)

    payload = RefundCreateRequest(cancel_amount=1000, reason_category="other")
    with pytest.raises(HTTPException) as exc_info:
        await admin_payment_service.create_refund(
            _make_request(), db, 200, payload, admin_id=1
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "PAYMENT_NOT_REFUNDABLE"
    assert exc_info.value.detail["current_status"] == "refund_pending"


@pytest.mark.asyncio
async def test_create_refund_no_refundable_balance_raises_409():
    """누적 환불이 이미 amount_krw 이상이면 NO_REFUNDABLE_BALANCE."""
    payment = _make_payment(amount_krw=19800)
    db = FakeDB()
    db.queue_scalar(payment)
    db.queue_row(19800, 2)             # 이미 전액 환불됨

    payload = RefundCreateRequest(cancel_amount=1, reason_category="other")
    with pytest.raises(HTTPException) as exc_info:
        await admin_payment_service.create_refund(
            _make_request(), db, 200, payload, admin_id=1
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "NO_REFUNDABLE_BALANCE"


@pytest.mark.asyncio
async def test_create_refund_cancel_amount_exceeds_balance_raises_409():
    """cancel_amount > 잔액 → CANCEL_AMOUNT_EXCEEDS_BALANCE + 두 값 동봉."""
    payment = _make_payment(amount_krw=19800)
    db = FakeDB()
    db.queue_scalar(payment)
    db.queue_row(5000, 1)              # 잔액 14800

    payload = RefundCreateRequest(cancel_amount=20000, reason_category="other")
    with pytest.raises(HTTPException) as exc_info:
        await admin_payment_service.create_refund(
            _make_request(), db, 200, payload, admin_id=1
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "CANCEL_AMOUNT_EXCEEDS_BALANCE"
    assert exc_info.value.detail["refundable_balance"] == 14800
    assert exc_info.value.detail["requested"] == 20000


# ── 502 분기 ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_refund_pg_transport_failure_rolls_back_and_raises_502():
    """pg.refund 예외 → rollback + PG_REFUND_UNAVAILABLE 502, refund row 미생성."""
    payment = _make_payment(amount_krw=19800)
    db = FakeDB()
    db.queue_scalar(payment)
    db.queue_row(0, 0)

    payload = RefundCreateRequest(cancel_amount=10000, reason_category="other")
    with patch.object(
        admin_payment_service, "get_pg_provider", return_value=_make_pg(raise_exc=True)
    ):
        with pytest.raises(HTTPException) as exc_info:
            await admin_payment_service.create_refund(
                _make_request(), db, 200, payload, admin_id=1
            )

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail["code"] == "PG_REFUND_UNAVAILABLE"
    assert db.rollbacks == 1
    assert db.commits == 0
    assert db.added_of(Refund) == []


@pytest.mark.asyncio
async def test_create_refund_pg_4xx_inserts_refund_denied_event_and_raises_502():
    """pg.refund success=False → refund_denied 이벤트 INSERT + commit + PG_REFUND_FAILED."""
    payment = _make_payment(amount_krw=19800)
    db = FakeDB()
    db.queue_scalar(payment)
    db.queue_row(0, 0)

    pg = _make_pg(
        success=False,
        raw={"code": "ALREADY_CANCELED_PAYMENT", "message": "이미 취소"},
    )
    payload = RefundCreateRequest(cancel_amount=10000, reason_category="other")

    with patch.object(admin_payment_service, "get_pg_provider", return_value=pg):
        with pytest.raises(HTTPException) as exc_info:
            await admin_payment_service.create_refund(
                _make_request(), db, 200, payload, admin_id=1
            )

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail["code"] == "PG_REFUND_FAILED"
    assert exc_info.value.detail["pg_error_code"] == "ALREADY_CANCELED_PAYMENT"
    # commit은 되지만 refund row는 없고 refund_denied 이벤트는 있음
    assert db.commits == 1
    denied = [e for e in db.added_of(PaymentEvent) if e.event_type == "refund_denied"]
    assert len(denied) == 1
    assert denied[0].raw_response_json["attempted_cancel_amount"] == 10000
    assert denied[0].raw_response_json["attempted_sequence"] == 1
    assert db.added_of(Refund) == []


# ── 멱등 키 + UNIQUE race ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_refund_idempotency_key_pattern_uses_sequence():
    """멱등 키는 `refund:{payment_id}:manual:{sequence}` 패턴이며 sequence가 증가한다."""
    payment = _make_payment(payment_id=777, amount_krw=19800)
    db = FakeDB()
    db.queue_scalar(payment)
    db.queue_row(5000, 1)              # 이미 1차 진행, 다음 sequence=2

    payload = RefundCreateRequest(cancel_amount=3000, reason_category="other")
    with patch.object(admin_payment_service, "get_pg_provider", return_value=_make_pg()):
        result = await admin_payment_service.create_refund(
            _make_request(), db, 777, payload, admin_id=1
        )

    assert result.refund_sequence == 2
    refund = db.added_of(Refund)[0]
    assert refund.idempotency_key == "refund:777:manual:2"


@pytest.mark.asyncio
async def test_create_refund_unique_violation_on_commit_raises_race_409():
    """commit에서 IntegrityError → REFUND_RACE_DETECTED 409 (PG 이미 호출됐을 가능성 안내)."""
    payment = _make_payment(amount_krw=19800)
    sub = _make_subscription()
    db = FakeDB()
    db.queue_scalar(payment)
    db.queue_row(0, 0)
    db.queue_scalar(sub)               # 전액 분기
    db.queue_noop()
    db.raise_on_commit(IntegrityError("INSERT", {}, Exception("uq violation")))

    payload = RefundCreateRequest(cancel_amount=19800, reason_category="other")
    with patch.object(admin_payment_service, "get_pg_provider", return_value=_make_pg()):
        with pytest.raises(HTTPException) as exc_info:
            await admin_payment_service.create_refund(
                _make_request(), db, 200, payload, admin_id=1
            )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "REFUND_RACE_DETECTED"
