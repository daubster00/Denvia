"""빌링 환불 통합 테스트 — Story 3.6 v1.1 청약철회.

GET /billing/subscriptions/me/refund-eligibility + POST /billing/subscriptions/me/cancel-with-refund
의 라우터↔서비스 경계와 예외 매핑 검증.

DB는 service-level 호출을 패치해서 검증한다.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from api.src.deps.auth import get_current_user
from api.src.deps.rate_limit import limit_billing
from api.src.models.base import get_session
from api.src.models.user import User
from api.src.routers.billing import router as _billing_router


@pytest.fixture(autouse=True)
def _set_enc_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("BILLING_KEY_ENC_KEY", key)


@pytest.fixture(autouse=True)
def _disable_rate_limiter(monkeypatch):
    from api.src.middleware.rate_limit import limiter

    monkeypatch.setattr(limiter, "enabled", False)


def _make_user() -> MagicMock:
    u = MagicMock(spec=User)
    u.id = 1
    u.phone = "01012345678"
    u.subscription_status = "pro"
    u.role = "user"
    u.current_session_id = None
    u.admin_grade = "master"
    return u


@pytest.fixture(scope="module")
def _billing_app():
    mini = FastAPI()
    mini.include_router(_billing_router, prefix="/api/v1")

    async def _mock_db():
        yield MagicMock()

    mini.dependency_overrides[get_session] = _mock_db
    mini.dependency_overrides[limit_billing] = lambda: None

    @mini.exception_handler(HTTPException)
    async def _http_exc_handler(request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail
        if isinstance(detail, dict):
            code = detail.get("code", "UNKNOWN_ERROR")
            message = detail.get("message", str(exc.detail))
            extras = {k: v for k, v in detail.items() if k not in ("code", "message")}
        else:
            code = "UNKNOWN_ERROR"
            message = str(detail)
            extras = {}
        body: dict = {"code": code, "message": message}
        if extras:
            body["details"] = extras
        return JSONResponse(status_code=exc.status_code, content=body)

    yield mini


@pytest.fixture
def client(_billing_app):
    with TestClient(_billing_app, raise_server_exceptions=False) as c:
        yield c


def _inject_auth(app, user):
    async def _mock_user():
        return user

    app.dependency_overrides[get_current_user] = _mock_user


def _clear_auth(app):
    app.dependency_overrides.pop(get_current_user, None)


# ── 인증 검증 ──────────────────────────────────────────────────────────────────


def test_eligibility_unauthenticated_returns_401(client):
    resp = client.get("/api/v1/billing/subscriptions/me/refund-eligibility")
    assert resp.status_code == 401


def test_cancel_with_refund_unauthenticated_returns_401(client):
    resp = client.post(
        "/api/v1/billing/subscriptions/me/cancel-with-refund",
        json={"confirmation": True},
    )
    assert resp.status_code == 401


# ── 폐기된 v1.0 엔드포인트 부재 확인 (AC4) ─────────────────────────────────────


def test_old_refund_endpoint_no_longer_registered(client):
    """v1.0 POST /billing/payments/{id}/refund 는 v1.1에서 폐기."""
    resp = client.post("/api/v1/billing/payments/200/refund", json={})
    # 라우터에서 제거되었으므로 404 (router) 또는 405 (method) 응답
    assert resp.status_code in (404, 405)


# ── GET /refund-eligibility (AC1) ─────────────────────────────────────────────


def test_eligibility_ok_returns_200_with_metadata(_billing_app, client):
    user = _make_user()
    _inject_auth(_billing_app, user)

    mock_result = {
        "eligible": True,
        "payment_id": 200,
        "amount_krw": 19800,
        "charged_at": "2026-05-09T12:00:00+00:00",
        "days_since_charge": 3,
        "qa_count_during_period": 0,
        "reason_code": "ok",
    }

    try:
        with patch(
            "api.src.routers.billing.check_refund_eligibility",
            new=AsyncMock(return_value=mock_result),
        ):
            resp = client.get("/api/v1/billing/subscriptions/me/refund-eligibility")
        assert resp.status_code == 200
        data = resp.json()
        assert data["eligible"] is True
        assert data["payment_id"] == 200
        assert data["amount_krw"] == 19800
        assert data["reason_code"] == "ok"
        assert data["qa_count_during_period"] == 0
    finally:
        _clear_auth(_billing_app)


def test_eligibility_no_active_payment(_billing_app, client):
    user = _make_user()
    _inject_auth(_billing_app, user)

    mock_result = {
        "eligible": False,
        "payment_id": None,
        "amount_krw": None,
        "charged_at": None,
        "days_since_charge": None,
        "qa_count_during_period": None,
        "reason_code": "no_active_payment",
    }

    try:
        with patch(
            "api.src.routers.billing.check_refund_eligibility",
            new=AsyncMock(return_value=mock_result),
        ):
            resp = client.get("/api/v1/billing/subscriptions/me/refund-eligibility")
        assert resp.status_code == 200
        data = resp.json()
        assert data["eligible"] is False
        assert data["reason_code"] == "no_active_payment"
        assert data["payment_id"] is None
    finally:
        _clear_auth(_billing_app)


def test_eligibility_period_exceeded(_billing_app, client):
    user = _make_user()
    _inject_auth(_billing_app, user)

    mock_result = {
        "eligible": False,
        "payment_id": 200,
        "amount_krw": 19800,
        "charged_at": "2026-05-01T12:00:00+00:00",
        "days_since_charge": 11,
        "qa_count_during_period": 0,
        "reason_code": "period_exceeded",
    }

    try:
        with patch(
            "api.src.routers.billing.check_refund_eligibility",
            new=AsyncMock(return_value=mock_result),
        ):
            resp = client.get("/api/v1/billing/subscriptions/me/refund-eligibility")
        assert resp.status_code == 200
        data = resp.json()
        assert data["eligible"] is False
        assert data["reason_code"] == "period_exceeded"
        assert data["days_since_charge"] == 11
    finally:
        _clear_auth(_billing_app)


# ── POST /cancel-with-refund (AC2/AC3) ────────────────────────────────────────


def test_cancel_with_refund_success_returns_200(_billing_app, client):
    user = _make_user()
    _inject_auth(_billing_app, user)

    mock_result = {
        "status": "refunded",
        "refund_kind": "cooling_off",
        "amount_krw": 19800,
        "refunded_at": "2026-05-12T09:30:00+00:00",
        "subscription_status": "canceled",
    }

    try:
        with patch(
            "api.src.routers.billing.cancel_with_refund",
            new=AsyncMock(return_value=mock_result),
        ):
            resp = client.post(
                "/api/v1/billing/subscriptions/me/cancel-with-refund",
                json={"confirmation": True},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "refunded"
        assert data["refund_kind"] == "cooling_off"
        assert data["amount_krw"] == 19800
        assert data["subscription_status"] == "canceled"
    finally:
        _clear_auth(_billing_app)


def test_cancel_with_refund_confirmation_false_returns_422(_billing_app, client):
    """confirmation=False → 스키마 validation 422 (PG·서비스 호출 0건)."""
    user = _make_user()
    _inject_auth(_billing_app, user)

    try:
        with patch(
            "api.src.routers.billing.cancel_with_refund",
            new=AsyncMock(),
        ) as service_mock:
            resp = client.post(
                "/api/v1/billing/subscriptions/me/cancel-with-refund",
                json={"confirmation": False},
            )
        assert resp.status_code == 422
        service_mock.assert_not_awaited()
    finally:
        _clear_auth(_billing_app)


# ── 예외 → HTTP 매핑 ──────────────────────────────────────────────────────────


def test_cancel_with_refund_no_active_subscription_returns_422(_billing_app, client):
    from api.src.services.billing_service import NoActiveSubscription

    user = _make_user()
    _inject_auth(_billing_app, user)

    try:
        with patch(
            "api.src.routers.billing.cancel_with_refund",
            new=AsyncMock(side_effect=NoActiveSubscription()),
        ):
            resp = client.post(
                "/api/v1/billing/subscriptions/me/cancel-with-refund",
                json={"confirmation": True},
            )
        assert resp.status_code == 422
        body = resp.json()
        assert body["code"] == "NO_ACTIVE_SUBSCRIPTION"
    finally:
        _clear_auth(_billing_app)


def test_cancel_with_refund_no_refundable_payment_returns_422(_billing_app, client):
    from api.src.services.billing_service import NoRefundablePayment

    user = _make_user()
    _inject_auth(_billing_app, user)

    try:
        with patch(
            "api.src.routers.billing.cancel_with_refund",
            new=AsyncMock(side_effect=NoRefundablePayment()),
        ):
            resp = client.post(
                "/api/v1/billing/subscriptions/me/cancel-with-refund",
                json={"confirmation": True},
            )
        assert resp.status_code == 422
        assert resp.json()["code"] == "NO_REFUNDABLE_PAYMENT"
    finally:
        _clear_auth(_billing_app)


def test_cancel_with_refund_not_eligible_returns_422_with_reason(_billing_app, client):
    """클라이언트 사전 조회 우회 — 422 REFUND_NOT_ELIGIBLE + reason_code 포함."""
    from api.src.services.billing_service import RefundNotEligible

    user = _make_user()
    _inject_auth(_billing_app, user)

    try:
        with patch(
            "api.src.routers.billing.cancel_with_refund",
            new=AsyncMock(side_effect=RefundNotEligible("qa_count_exceeded")),
        ):
            resp = client.post(
                "/api/v1/billing/subscriptions/me/cancel-with-refund",
                json={"confirmation": True},
            )
        assert resp.status_code == 422
        body = resp.json()
        assert body["code"] == "REFUND_NOT_ELIGIBLE"
        assert body["details"]["reason_code"] == "qa_count_exceeded"
    finally:
        _clear_auth(_billing_app)


def test_cancel_with_refund_already_processed_returns_409(_billing_app, client):
    from api.src.services.billing_service import RefundAlreadyProcessed

    user = _make_user()
    _inject_auth(_billing_app, user)

    try:
        with patch(
            "api.src.routers.billing.cancel_with_refund",
            new=AsyncMock(side_effect=RefundAlreadyProcessed()),
        ):
            resp = client.post(
                "/api/v1/billing/subscriptions/me/cancel-with-refund",
                json={"confirmation": True},
            )
        assert resp.status_code == 409
        assert resp.json()["code"] == "REFUND_ALREADY_PROCESSED"
    finally:
        _clear_auth(_billing_app)


def test_cancel_with_refund_already_requested_returns_409(_billing_app, client):
    from api.src.services.billing_service import RefundAlreadyRequested

    user = _make_user()
    _inject_auth(_billing_app, user)

    try:
        with patch(
            "api.src.routers.billing.cancel_with_refund",
            new=AsyncMock(side_effect=RefundAlreadyRequested()),
        ):
            resp = client.post(
                "/api/v1/billing/subscriptions/me/cancel-with-refund",
                json={"confirmation": True},
            )
        assert resp.status_code == 409
        assert resp.json()["code"] == "REFUND_ALREADY_REQUESTED"
    finally:
        _clear_auth(_billing_app)


def test_cancel_with_refund_provider_unavailable_returns_502(_billing_app, client):
    from api.src.services.billing_service import RefundProviderUnavailable

    user = _make_user()
    _inject_auth(_billing_app, user)

    try:
        with patch(
            "api.src.routers.billing.cancel_with_refund",
            new=AsyncMock(side_effect=RefundProviderUnavailable("transport_failure")),
        ):
            resp = client.post(
                "/api/v1/billing/subscriptions/me/cancel-with-refund",
                json={"confirmation": True},
            )
        assert resp.status_code == 502
        assert resp.json()["code"] == "BILLING_PROVIDER_UNAVAILABLE"
    finally:
        _clear_auth(_billing_app)
