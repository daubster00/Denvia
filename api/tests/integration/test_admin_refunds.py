"""Story 9.3 — admin/refunds 통합 테스트.

신규 endpoint:
- GET  /admin/refunds                       (status/from/to/q + 페이지네이션)
- POST /admin/refunds/{queue_id}/approve    (PG mock)
- POST /admin/refunds/{queue_id}/deny
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
from api.src.schemas.admin.refunds import (
    RefundActionResponse,
    RefundQueueItem,
    RefundQueueListResponse,
)
from api.src.settings import settings


def _make_admin_jwt(user_id: int = 99) -> str:
    payload = {
        "sub": str(user_id),
        "aud": "denvia-admin",
        "exp": int(time.time()) + 3600,
    }
    return pyjwt.encode(
        payload, settings.denvia_jwt_secret, algorithm=settings.denvia_jwt_algorithm
    )


def _make_admin():
    user = MagicMock()
    user.id = 1
    user.email = "admin@denvia.local"
    user.role = "admin"
    user.subscription_status = "free"
    user.segment = None
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


def _make_queue_item(queue_id: int = 42, status: str = "pending") -> RefundQueueItem:
    return RefundQueueItem(
        queue_id=queue_id,
        payment_id=1234,
        user_id=7,
        user_email_masked="u****@example.com",
        amount_krw=9900,
        card_last4="1234",
        card_company="현대",
        days_since_charge=9,
        qa_count_during_period=12,
        reason_code="both",
        reason_text=None,
        requested_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        status=status,
        reviewer_user_email_masked=None,
        reviewer_note=None,
        reviewed_at=None,
    )


@pytest.mark.asyncio
class TestRefundsAuth:
    async def test_unauthenticated_returns_401(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.get("/api/v1/admin/refunds")
        assert res.status_code == 401


@pytest.mark.asyncio
class TestRefundsList:
    async def _call(self, qs: str = ""):
        token = _make_admin_jwt()
        admin = _make_admin()
        gen = _stub_session()
        response = RefundQueueListResponse(
            items=[_make_queue_item()], page=1, per_page=50, total=1
        )
        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
            patch(
                "api.src.routers.admin.refunds.admin_refund_service.list_queue",
                new=AsyncMock(return_value=response),
            ) as svc,
        ):
            app.dependency_overrides[get_session] = gen
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.get(
                        f"/api/v1/admin/refunds{qs}",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()
        return res, svc

    async def test_default_returns_pending_list(self):
        res, svc = await self._call()
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 1
        assert body["items"][0]["queue_id"] == 42
        assert res.headers.get("Cache-Control") == "no-store"
        # default status
        assert svc.call_args.kwargs["status"] == "pending"

    async def test_invalid_status_returns_422(self):
        res, _ = await self._call("?status=bogus")
        assert res.status_code == 422

    async def test_invalid_per_page_returns_422(self):
        res, _ = await self._call("?per_page=37")
        assert res.status_code == 422


@pytest.mark.asyncio
class TestRefundsApprove:
    async def _call(self, queue_id: int, payload: dict):
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
                        f"/api/v1/admin/refunds/{queue_id}/approve",
                        json=payload,
                        cookies={
                            "denvia_admin_session": token,
                            "denvia_admin_csrf": "csrf-test",
                        },
                        headers={"X-CSRF-Token": "csrf-test"},
                    )
            finally:
                app.dependency_overrides.clear()
        return res

    async def test_approve_success_returns_200(self):
        approved = RefundActionResponse(
            queue_id=42,
            payment_id=1234,
            status="approved",
            amount_krw=9900,
            refunded_at=datetime(2026, 5, 7, tzinfo=timezone.utc),
        )
        with patch(
            "api.src.routers.admin.refunds.admin_refund_service.approve",
            new=AsyncMock(return_value=approved),
        ):
            res = await self._call(42, {"note": "정상 환불"})
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "approved"
        assert body["amount_krw"] == 9900

    async def test_approve_pg_failure_propagates_502(self):
        async def raise_pg_failed(*_a, **_kw):
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "PG_REFUND_FAILED",
                    "message": "PG가 환불을 거부했습니다.",
                    "pg_error_code": "INVALID_PAYMENT",
                },
            )

        with patch(
            "api.src.routers.admin.refunds.admin_refund_service.approve",
            new=AsyncMock(side_effect=raise_pg_failed),
        ):
            res = await self._call(42, {"note": "정상 환불"})
        assert res.status_code == 502
        body = res.json()
        assert body["code"] == "PG_REFUND_FAILED"

    async def test_approve_queue_not_pending_409(self):
        async def raise_409(*_a, **_kw):
            raise HTTPException(
                status_code=409,
                detail={"code": "QUEUE_NOT_PENDING", "message": "이미 처리됨"},
            )

        with patch(
            "api.src.routers.admin.refunds.admin_refund_service.approve",
            new=AsyncMock(side_effect=raise_409),
        ):
            res = await self._call(42, {"note": "ok"})
        assert res.status_code == 409

    async def test_approve_empty_note_422(self):
        res = await self._call(42, {"note": ""})
        assert res.status_code == 422


@pytest.mark.asyncio
class TestRefundsDeny:
    async def _call(self, queue_id: int, payload: dict):
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
                        f"/api/v1/admin/refunds/{queue_id}/deny",
                        json=payload,
                        cookies={
                            "denvia_admin_session": token,
                            "denvia_admin_csrf": "csrf-test",
                        },
                        headers={"X-CSRF-Token": "csrf-test"},
                    )
            finally:
                app.dependency_overrides.clear()
        return res

    async def test_deny_returns_200(self):
        denied = RefundActionResponse(
            queue_id=42,
            payment_id=1234,
            status="denied",
            amount_krw=9900,
            refunded_at=None,
        )
        with patch(
            "api.src.routers.admin.refunds.admin_refund_service.deny",
            new=AsyncMock(return_value=denied),
        ):
            res = await self._call(42, {"note": "거부 사유"})
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "denied"
        assert body["refunded_at"] is None

    @pytest.mark.parametrize("current_status", ["refunded", "failed"])
    async def test_deny_returns_409_when_payment_not_refund_pending(self, current_status):
        """payment.status 가 이미 refunded/failed 등이면 거부가 success 로 되살리지 않도록 409."""
        async def raise_not_refund_pending(*_a, **_kw):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "PAYMENT_NOT_REFUND_PENDING",
                    "message": "환불 대기 상태가 아닌 결제는 거부 처리할 수 없습니다.",
                    "current_status": current_status,
                },
            )

        with patch(
            "api.src.routers.admin.refunds.admin_refund_service.deny",
            new=AsyncMock(side_effect=raise_not_refund_pending),
        ):
            res = await self._call(42, {"note": "거부 사유"})
        assert res.status_code == 409
        body = res.json()
        assert body["code"] == "PAYMENT_NOT_REFUND_PENDING"
        # current_status 는 표준 에러 포맷 (api.src.main._http_exception_handler) 의 details 로 떨어짐
        assert body["details"]["current_status"] == current_status
