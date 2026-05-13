"""Story 9.1 v1.1 — admin/payments/{payment_id}/refund* 통합 테스트.

신규 endpoint (api/src/routers/admin/payments.py — admin_payments 라우터):
- GET  /api/v1/admin/payments/{payment_id}/refund-quote   60/min
- POST /api/v1/admin/payments/{payment_id}/refunds        30/min
- GET  /api/v1/admin/payments/{payment_id}/refunds        60/min

본 테스트는 라우터↔서비스 경계, 인증 가드(401), 표준 에러 포맷 변환, 후처리 hook
(audit_logs INSERT, 알림톡 fire-and-forget, Redis admin:events publish)을 검증한다.
실제 DB/PG 호출과 환불 트랜잭션 세부 분기는 단위 테스트
(`api/tests/unit/test_admin_payment_service_v1_1.py`)가 책임진다.

레이트 리밋 자체 트리거는 Redis 의존이라 본 모듈에서는 비활성화하고, 데코레이터 등록만
인스펙션으로 검증한다 (실제 트리거는 slowapi의 책임이며 미들웨어가 표준 429를 반환함을
존재로 신뢰).
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from api.src.main import app
from api.src.models.base import get_session
from api.src.schemas.admin.payment_refunds import (
    RefundCreateResponse,
    RefundListItem,
    RefundListResponse,
    RefundQuoteResponse,
)
from api.src.settings import settings


# ── 헬퍼 ───────────────────────────────────────────────────────────────────────


def _make_admin_jwt(user_id: int = 99) -> str:
    payload = {
        "sub": str(user_id),
        "aud": "denvia-admin",
        "exp": int(time.time()) + 3600,
    }
    return pyjwt.encode(
        payload, settings.denvia_jwt_secret, algorithm=settings.denvia_jwt_algorithm
    )


def _make_admin(user_id: int = 99):
    user = MagicMock()
    user.id = user_id
    user.email = "admin@denvia.local"
    user.role = "admin"
    user.subscription_status = "free"
    user.segment = None
    user.years_of_experience = None
    user.withdrawn_at = None
    user.must_reset_password = False
    return user


def _stub_session():
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()

    async def gen():
        yield session

    return gen


def _make_audit_ctx(capture: list):
    """audit middleware가 사용하는 async_session_factory 대체.

    db.add()로 들어오는 AuditLog row를 capture 리스트에 누적해 검증한다.
    """
    session = MagicMock()
    session.add = lambda obj: capture.append(obj)
    session.commit = AsyncMock()

    class FakeCtx:
        async def __aenter__(self_inner):
            return session

        async def __aexit__(self_inner, *a):
            pass

    return FakeCtx()


@pytest.fixture(autouse=True)
def _disable_rate_limiter(monkeypatch):
    """slowapi 카운팅을 비활성화 — Redis 의존 + 테스트 격리 어려움."""
    from api.src.middleware.rate_limit import limiter

    monkeypatch.setattr(limiter, "enabled", False)


def _make_quote(payment_id: int = 200) -> RefundQuoteResponse:
    return RefundQuoteResponse(
        payment_id=payment_id,
        user_id=10,
        payment_amount=19800,
        refunded_total=0,
        refundable_balance=19800,
        full_refund_amount=19800,
        prorated_amount=15000,
        prorated_days_remaining=23,
        prorated_total_days=30,
        is_within_cooling_off=True,
        cooling_off_days_since_charge=2,
        cooling_off_qa_count=0,
        next_refund_sequence=1,
        existing_refunds_count=0,
        subscription_period_start=datetime(2026, 5, 1, tzinfo=timezone.utc),
        subscription_period_end=datetime(2026, 5, 31, tzinfo=timezone.utc),
    )


def _make_create_response(refund_id: int = 42, sequence: int = 1, amount: int = 19800):
    return RefundCreateResponse(
        refund_id=refund_id,
        refund_sequence=sequence,
        cancel_amount=amount,
        refunded_at=datetime(2026, 5, 12, 9, 30, tzinfo=timezone.utc),
    )


def _make_list_response(items_count: int = 1) -> RefundListResponse:
    items = [
        RefundListItem(
            id=100 + i,
            refund_sequence=i + 1,
            cancel_amount=5000 * (i + 1),
            reason_category="customer_complaint",
            memo=f"메모 {i + 1}" if i == 0 else None,
            admin_email_masked="a****@denvia.local",
            created_at=datetime(2026, 5, 10 + i, 12, tzinfo=timezone.utc),
        )
        for i in range(items_count)
    ]
    return RefundListResponse(items=items, total=items_count)


# ── 인증 ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestPaymentRefundsAuth:
    async def test_quote_unauthenticated_returns_401(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.get("/api/v1/admin/payments/200/refund-quote")
        assert res.status_code == 401

    async def test_create_unauthenticated_returns_401(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.post(
                "/api/v1/admin/payments/200/refunds",
                json={"cancel_amount": 19800, "reason_category": "customer_complaint"},
            )
        assert res.status_code == 401

    async def test_list_unauthenticated_returns_401(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.get("/api/v1/admin/payments/200/refunds")
        assert res.status_code == 401


# ── GET /refund-quote ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestRefundQuote:
    async def _call(self, payment_id: int = 200, *, get_quote_mock=None):
        token = _make_admin_jwt()
        admin = _make_admin()
        gen = _stub_session()
        get_quote_mock = get_quote_mock or AsyncMock(return_value=_make_quote(payment_id))
        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
            patch(
                "api.src.routers.admin.payments.get_refund_quote", new=get_quote_mock
            ) as svc,
        ):
            app.dependency_overrides[get_session] = gen
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.get(
                        f"/api/v1/admin/payments/{payment_id}/refund-quote",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()
        return res, svc

    async def test_returns_200_with_quote(self):
        res, svc = await self._call(payment_id=200)
        assert res.status_code == 200
        body = res.json()
        assert body["payment_id"] == 200
        assert body["refundable_balance"] == 19800
        assert body["next_refund_sequence"] == 1
        assert body["is_within_cooling_off"] is True
        assert res.headers.get("Cache-Control") == "no-store"
        # 라우터가 payment_id를 그대로 서비스에 전달
        assert svc.await_args.args[1] == 200

    async def test_payment_not_found_returns_404(self):
        async def raise_404(*_a, **_kw):
            raise HTTPException(
                status_code=404,
                detail={"code": "PAYMENT_NOT_FOUND", "message": "결제를 찾을 수 없습니다."},
            )

        res, _ = await self._call(payment_id=99999, get_quote_mock=AsyncMock(side_effect=raise_404))
        assert res.status_code == 404
        body = res.json()
        assert body["code"] == "PAYMENT_NOT_FOUND"


# ── POST /refunds ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestCreateRefund:
    """라우터의 dispatch + 표준 에러 포맷 변환 + 후처리 hook 검증."""

    async def _call(
        self,
        payment_id: int = 200,
        payload: dict | None = None,
        *,
        create_mock=None,
        notify_mock=None,
        publish_mock=None,
        audit_capture: list | None = None,
        with_request_state: bool = True,
    ):
        token = _make_admin_jwt()
        admin = _make_admin()
        gen = _stub_session()
        payload = payload or {
            "cancel_amount": 19800,
            "reason_category": "customer_complaint",
            "memo": "운영 환불 사유",
        }

        # 성공 경로 기본값 — 서비스는 request.state에 후처리 페이로드를 박는다.
        async def default_create(request, db, pid, p, *, admin_id):
            if with_request_state:
                request.state.refund_op_user_id = 10
                request.state.refund_op_payment_id = pid
                request.state.refund_op_amount_krw = 19800
                request.state.refund_op_cancel_amount = p.cancel_amount
                request.state.refund_op_refund_reason = (
                    "manual_full" if p.cancel_amount == 19800 else "manual_partial"
                )
                request.state.refund_op_idempotency_key = f"refund:{pid}:manual:1"
                request.state.refund_op_now = datetime(
                    2026, 5, 12, 9, 30, tzinfo=timezone.utc
                )
                # audit middleware가 읽는 메타도 박아둔다 → 응답 200 → 미들웨어가 INSERT.
                request.state.audit_action = "refund.operational.create"
                request.state.audit_target_type = "payment"
                request.state.audit_target_id = pid
                request.state.audit_diff = '{"refund_sequence": 1}'
            return _make_create_response(amount=p.cancel_amount)

        create_mock = create_mock or AsyncMock(side_effect=default_create)
        notify_mock = notify_mock or AsyncMock()
        publish_mock = publish_mock or AsyncMock()
        audit_capture = audit_capture if audit_capture is not None else []

        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
            patch(
                "api.src.routers.admin.payments.admin_payment_service.create_refund",
                new=create_mock,
            ),
            patch(
                "api.src.routers.admin.payments.admin_payment_service.notify_refund_succeeded",
                new=notify_mock,
            ),
            patch(
                "api.src.routers.admin.payments.admin_payment_service.publish_admin_event",
                new=publish_mock,
            ),
            patch(
                "api.src.middleware.audit.async_session_factory",
                side_effect=lambda: _make_audit_ctx(audit_capture),
            ),
        ):
            app.dependency_overrides[get_session] = gen
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.post(
                        f"/api/v1/admin/payments/{payment_id}/refunds",
                        json=payload,
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()
        return res, create_mock, notify_mock, publish_mock, audit_capture

    # ── 성공 경로 ──

    async def test_full_refund_success_returns_200_and_fires_notify_and_publish(self):
        audit_capture: list = []
        res, _create, notify_mock, publish_mock, audit_capture = await self._call(
            audit_capture=audit_capture
        )
        assert res.status_code == 200
        body = res.json()
        assert body["refund_id"] == 42
        assert body["refund_sequence"] == 1
        assert body["cancel_amount"] == 19800

        # fire-and-forget — BackgroundTasks는 응답 직후 실행됨 (httpx ASGITransport 내).
        notify_mock.assert_awaited_once()
        notify_kwargs = notify_mock.await_args.kwargs
        assert notify_kwargs["user_id"] == 10
        assert notify_kwargs["payment_id"] == 200
        assert notify_kwargs["amount_krw"] == 19800
        assert notify_kwargs["refund_amount_krw"] == 19800
        assert notify_kwargs["refund_reason"] == "manual_full"
        assert notify_kwargs["idempotency_key"] == "refund:200:manual:1"

        publish_mock.assert_awaited_once()
        published_payload = publish_mock.await_args.args[0]
        assert published_payload["type"] == "refund_operational_created"
        assert published_payload["payment_id"] == 200
        assert published_payload["refund_id"] == 42
        assert published_payload["refund_sequence"] == 1
        assert published_payload["cancel_amount"] == 19800
        assert published_payload["refund_reason"] == "manual_full"

        # audit middleware가 INSERT한 row 1건 — action='refund.operational.create'.
        from api.src.models.audit_log import AuditLog

        audit_rows = [a for a in audit_capture if isinstance(a, AuditLog)]
        assert len(audit_rows) == 1
        assert audit_rows[0].action == "refund.operational.create"
        assert audit_rows[0].target_type == "payment"
        assert audit_rows[0].target_id == 200
        assert audit_rows[0].actor_user_id == 99

    async def test_partial_refund_success_classifies_as_manual_partial(self):
        payload = {
            "cancel_amount": 5000,
            "reason_category": "duplicate_payment",
        }
        res, _create, notify_mock, publish_mock, _audit = await self._call(payload=payload)
        assert res.status_code == 200
        notify_mock.assert_awaited_once()
        assert notify_mock.await_args.kwargs["refund_reason"] == "manual_partial"
        assert notify_mock.await_args.kwargs["refund_amount_krw"] == 5000
        assert publish_mock.await_args.args[0]["refund_reason"] == "manual_partial"

    async def test_two_refunds_in_sequence_invokes_service_twice(self):
        """동일 결제 2회 호출이 서비스 레이어에 누적 전달됨을 확인 (sequence 책임은 서비스)."""
        # 1회차
        res1, create_mock, notify_mock, publish_mock, _audit = await self._call(
            payload={"cancel_amount": 5000, "reason_category": "system_error"}
        )
        assert res1.status_code == 200

        # 2회차 — 같은 mock을 새로 만들어 한 번 더 호출
        res2, create_mock2, notify_mock2, _publish, _ = await self._call(
            payload={"cancel_amount": 14800, "reason_category": "system_error"}
        )
        assert res2.status_code == 200
        # 두 요청 모두 서비스 호출됨
        assert create_mock.await_count == 1
        assert create_mock2.await_count == 1
        assert notify_mock.await_count == 1
        assert notify_mock2.await_count == 1

    # ── 409 분기 (3종) ──

    async def test_payment_not_refundable_returns_409(self):
        async def raise_409(*_a, **_kw):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "PAYMENT_NOT_REFUNDABLE",
                    "message": "환불 가능한 결제 상태가 아닙니다.",
                    "current_status": "refund_pending",
                },
            )

        res, _c, notify_mock, publish_mock, audit_capture = await self._call(
            create_mock=AsyncMock(side_effect=raise_409),
            with_request_state=False,
        )
        assert res.status_code == 409
        body = res.json()
        assert body["code"] == "PAYMENT_NOT_REFUNDABLE"
        assert body["details"]["current_status"] == "refund_pending"
        # 4xx → audit INSERT 안 됨, fire-and-forget 안 됨
        notify_mock.assert_not_awaited()
        publish_mock.assert_not_awaited()
        from api.src.models.audit_log import AuditLog

        assert [a for a in audit_capture if isinstance(a, AuditLog)] == []

    async def test_no_refundable_balance_returns_409(self):
        async def raise_409(*_a, **_kw):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "NO_REFUNDABLE_BALANCE",
                    "message": "이 결제는 이미 전액 환불되었습니다.",
                    "refundable_balance": 0,
                },
            )

        res, *_ = await self._call(
            create_mock=AsyncMock(side_effect=raise_409),
            with_request_state=False,
        )
        assert res.status_code == 409
        assert res.json()["code"] == "NO_REFUNDABLE_BALANCE"

    async def test_cancel_amount_exceeds_balance_returns_409(self):
        async def raise_409(*_a, **_kw):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "CANCEL_AMOUNT_EXCEEDS_BALANCE",
                    "message": "환불 금액이 잔액을 초과합니다.",
                    "refundable_balance": 14800,
                    "requested": 20000,
                },
            )

        res, *_ = await self._call(
            payload={"cancel_amount": 20000, "reason_category": "other"},
            create_mock=AsyncMock(side_effect=raise_409),
            with_request_state=False,
        )
        assert res.status_code == 409
        body = res.json()
        assert body["code"] == "CANCEL_AMOUNT_EXCEEDS_BALANCE"
        assert body["details"]["refundable_balance"] == 14800
        assert body["details"]["requested"] == 20000

    # ── 502 분기 (2종) ──

    async def test_pg_transport_failure_returns_502_unavailable(self):
        async def raise_502(*_a, **_kw):
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "PG_REFUND_UNAVAILABLE",
                    "message": "PG 통신 장애. 잠시 후 다시 시도해주세요.",
                },
            )

        res, _c, notify_mock, publish_mock, audit_capture = await self._call(
            create_mock=AsyncMock(side_effect=raise_502),
            with_request_state=False,
        )
        assert res.status_code == 502
        assert res.json()["code"] == "PG_REFUND_UNAVAILABLE"
        notify_mock.assert_not_awaited()
        publish_mock.assert_not_awaited()
        from api.src.models.audit_log import AuditLog

        assert [a for a in audit_capture if isinstance(a, AuditLog)] == []

    async def test_pg_4xx_returns_502_failed_with_error_details(self):
        async def raise_pg_failed(*_a, **_kw):
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "PG_REFUND_FAILED",
                    "message": "PG가 환불을 거부했습니다.",
                    "pg_error_code": "ALREADY_CANCELED_PAYMENT",
                    "pg_error_message": "이미 취소",
                },
            )

        res, *_ = await self._call(
            create_mock=AsyncMock(side_effect=raise_pg_failed),
            with_request_state=False,
        )
        assert res.status_code == 502
        body = res.json()
        assert body["code"] == "PG_REFUND_FAILED"
        assert body["details"]["pg_error_code"] == "ALREADY_CANCELED_PAYMENT"

    # ── 422 (스키마 validation) ──

    async def test_cancel_amount_zero_returns_422(self):
        token = _make_admin_jwt()
        admin = _make_admin()
        gen = _stub_session()
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
            app.dependency_overrides[get_session] = gen
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.post(
                        "/api/v1/admin/payments/200/refunds",
                        json={"cancel_amount": 0, "reason_category": "other"},
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()
        assert res.status_code == 422


# ── GET /refunds (list) ────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestListPaymentRefunds:
    async def _call(self, payment_id: int = 200, *, list_mock=None):
        token = _make_admin_jwt()
        admin = _make_admin()
        gen = _stub_session()
        list_mock = list_mock or AsyncMock(return_value=_make_list_response(items_count=2))
        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
            patch(
                "api.src.routers.admin.payments.admin_payment_service.list_refunds",
                new=list_mock,
            ) as svc,
        ):
            app.dependency_overrides[get_session] = gen
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.get(
                        f"/api/v1/admin/payments/{payment_id}/refunds",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()
        return res, svc

    async def test_returns_200_with_timeseries(self):
        res, _svc = await self._call(payment_id=200)
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 2
        assert len(body["items"]) == 2
        # 시계열 순(asc) — 서비스 책임이지만 응답 echo 검증.
        assert body["items"][0]["refund_sequence"] == 1
        assert body["items"][1]["refund_sequence"] == 2
        # 마스킹된 admin email 노출
        assert body["items"][0]["admin_email_masked"].startswith("a")
        assert "@" in body["items"][0]["admin_email_masked"]
        assert res.headers.get("Cache-Control") == "no-store"

    async def test_payment_not_found_returns_404(self):
        async def raise_404(*_a, **_kw):
            raise HTTPException(
                status_code=404,
                detail={"code": "PAYMENT_NOT_FOUND", "message": "결제를 찾을 수 없습니다."},
            )

        res, _svc = await self._call(
            payment_id=99999, list_mock=AsyncMock(side_effect=raise_404)
        )
        assert res.status_code == 404
        assert res.json()["code"] == "PAYMENT_NOT_FOUND"


# ── 레이트 리밋 등록 인스펙션 ───────────────────────────────────────────────────


def test_rate_limits_registered_on_routes():
    """slowapi @limiter.limit 데코레이터가 각 endpoint에 적용되어 있는지 인스펙션.

    실제 트리거 (60/min 도달 후 429)는 Redis 카운팅 의존이라 본 통합 테스트 범위 밖.
    데코레이터 등록 자체가 누락되는 회귀를 잡는다.
    """
    from api.src.middleware.rate_limit import limiter

    # slowapi는 _route_limits 또는 _dynamic_route_limits에 endpoint name → limit 문자열을 저장.
    registered = {}
    for attr in ("_route_limits", "_dynamic_route_limits"):
        registry = getattr(limiter, attr, None) or {}
        registered.update(registry)

    # slowapi key = "<module>.<function_name>" 풀 경로.
    base = "api.src.routers.admin.payments"
    expected_endpoints = {
        f"{base}.get_refund_quote_endpoint",
        f"{base}.create_payment_refund",
        f"{base}.list_payment_refunds",
    }
    found = expected_endpoints & set(registered.keys())
    assert found == expected_endpoints, (
        f"등록 누락: 기대 {expected_endpoints} / 실제 {set(registered.keys()) & expected_endpoints}"
    )

    # 분당 한도 문자열 검증 — quote/list=60/min, create=30/min.
    quote_limit = registered[f"{base}.get_refund_quote_endpoint"][0].limit
    create_limit = registered[f"{base}.create_payment_refund"][0].limit
    list_limit = registered[f"{base}.list_payment_refunds"][0].limit
    assert "60 per 1 minute" in str(quote_limit)
    assert "30 per 1 minute" in str(create_limit)
    assert "60 per 1 minute" in str(list_limit)
