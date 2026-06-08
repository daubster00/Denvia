"""빌링 플로우 통합 테스트 — Story 3.2.

POST /billing/billing-key, POST /billing/subscriptions 엔드포인트 검증.
TossAdapter는 mock으로 대체 — 실 API 미호출.
"""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from cryptography.fernet import Fernet

from api.src.models.user import User
from api.src.routers.billing import router as _billing_router
from api.src.models.base import get_session
from api.src.deps.auth import get_current_user
from api.src.deps.rate_limit import limit_billing


@pytest.fixture(autouse=True)
def _set_enc_key(monkeypatch):
    """Fernet 키 주입."""
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("BILLING_KEY_ENC_KEY", key)


def _make_user(subscription_status: str = "free") -> MagicMock:
    u = MagicMock(spec=User)
    u.id = 1
    u.phone = "01012345678"
    u.subscription_status = subscription_status
    u.role = "user"
    u.current_session_id = None
    u.admin_grade = "master"
    return u


@pytest.fixture(scope="module")
def _billing_app():
    """billing 라우터 전용 최소 FastAPI 앱 — DB/레이트 리밋 모킹."""
    from fastapi import Request
    from fastapi.responses import JSONResponse

    mini = FastAPI()
    mini.include_router(_billing_router, prefix="/api/v1")

    async def _mock_db():
        yield MagicMock()

    # 레이트 리밋 Depends 우회
    mini.dependency_overrides[get_session] = _mock_db
    mini.dependency_overrides[limit_billing] = lambda: None

    # HTTPException을 Denvia 표준 포맷으로 변환 (main.py 핸들러와 동일)
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


# ── 인증 테스트 ────────────────────────────────────────────────────────────────


def test_billing_key_unauthenticated_returns_401(client):
    """쿠키 없이 POST /billing/billing-key 호출 시 401을 반환해야 한다."""
    resp = client.post(
        "/api/v1/billing/billing-key",
        json={"pg_token": "tok", "customer_key": "denvia_uuid_valid_key_here"},
    )
    assert resp.status_code == 401


def test_subscriptions_unauthenticated_returns_401(client):
    """쿠키 없이 POST /billing/subscriptions 호출 시 401을 반환해야 한다."""
    resp = client.post("/api/v1/billing/subscriptions")
    assert resp.status_code == 401


# ── customer_key 검증 ──────────────────────────────────────────────────────────


def test_billing_key_forbidden_customer_key_pattern(_billing_app, client):
    """user ID를 포함한 customer_key 패턴은 422를 반환해야 한다."""
    _inject_auth(_billing_app, _make_user())
    try:
        resp = client.post(
            "/api/v1/billing/billing-key",
            json={"pg_token": "tok", "customer_key": "denvia-user-1"},
        )
        assert resp.status_code == 422
    finally:
        _clear_auth(_billing_app)


def test_billing_key_invalid_customer_key_chars(_billing_app, client):
    """허용되지 않는 문자가 포함된 customer_key는 422를 반환해야 한다."""
    _inject_auth(_billing_app, _make_user())
    try:
        resp = client.post(
            "/api/v1/billing/billing-key",
            json={"pg_token": "tok", "customer_key": "invalid key with spaces"},
        )
        assert resp.status_code == 422
    finally:
        _clear_auth(_billing_app)


# ── 빌링키 발급 성공 ───────────────────────────────────────────────────────────


def test_billing_key_issue_success(_billing_app, client):
    """정상 요청 시 POST /billing/billing-key가 201 + billing_key_id를 반환한다."""
    user = _make_user()
    _inject_auth(_billing_app, user)

    mock_result = {
        "billing_key_id": 1,
        "card_last4": "1234",
        "card_company": "신한",
        "masked_number": "**** **** **** 1234",
    }

    try:
        with patch(
            "api.src.routers.billing.issue_billing_key",
            new=AsyncMock(return_value=mock_result),
        ):
            resp = client.post(
                "/api/v1/billing/billing-key",
                json={
                    "pg_token": "valid_auth_key",
                    "customer_key": "denvia_cust_valid_uuid_here",
                },
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["billing_key_id"] == 1
        assert data["card_last4"] == "1234"
    finally:
        _clear_auth(_billing_app)


# ── 구독 시작 성공 ─────────────────────────────────────────────────────────────


def test_start_subscription_success(_billing_app, client):
    """POST /billing/subscriptions 성공 시 200 + subscription_id를 반환한다."""
    user = _make_user(subscription_status="free")
    _inject_auth(_billing_app, user)

    mock_result = {
        "subscription_id": 42,
        "started_at": "2026-04-29T00:00:00+00:00",
        "current_period_end": "2026-05-29T00:00:00+00:00",
        "amount_krw": 9900,
    }

    try:
        with patch(
            "api.src.routers.billing.start_subscription",
            new=AsyncMock(return_value=mock_result),
        ):
            resp = client.post("/api/v1/billing/subscriptions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["subscription_id"] == 42
        assert data["amount_krw"] == 9900
    finally:
        _clear_auth(_billing_app)


# ── 오류 케이스 ───────────────────────────────────────────────────────────────


def test_start_subscription_already_active(_billing_app, client):
    """이미 Pro 상태이면 409 SUBSCRIPTION_ALREADY_ACTIVE를 반환한다."""
    from api.src.services.billing_service import SubscriptionAlreadyActive

    user = _make_user(subscription_status="pro")
    _inject_auth(_billing_app, user)

    try:
        with patch(
            "api.src.routers.billing.start_subscription",
            new=AsyncMock(side_effect=SubscriptionAlreadyActive()),
        ):
            resp = client.post("/api/v1/billing/subscriptions")
        assert resp.status_code == 409
        assert resp.json()["code"] == "SUBSCRIPTION_ALREADY_ACTIVE"
    finally:
        _clear_auth(_billing_app)


def test_start_subscription_billing_key_required(_billing_app, client):
    """활성 빌링키 없으면 400 BILLING_KEY_REQUIRED를 반환한다."""
    from api.src.services.billing_service import BillingKeyRequired

    user = _make_user()
    _inject_auth(_billing_app, user)

    try:
        with patch(
            "api.src.routers.billing.start_subscription",
            new=AsyncMock(side_effect=BillingKeyRequired()),
        ):
            resp = client.post("/api/v1/billing/subscriptions")
        assert resp.status_code == 400
        assert resp.json()["code"] == "BILLING_KEY_REQUIRED"
    finally:
        _clear_auth(_billing_app)


def test_start_subscription_card_declined(_billing_app, client):
    """결제 실패 시 400 BILLING_CARD_DECLINED를 반환한다."""
    from api.src.services.billing_service import BillingCardDeclined

    user = _make_user()
    _inject_auth(_billing_app, user)

    try:
        with patch(
            "api.src.routers.billing.start_subscription",
            new=AsyncMock(
                side_effect=BillingCardDeclined(
                    pg_error_code="EXCEED_MAX_AMOUNT",
                    message="카드 한도 초과",
                )
            ),
        ):
            resp = client.post("/api/v1/billing/subscriptions")
        assert resp.status_code == 400
        data = resp.json()
        assert data["code"] == "BILLING_CARD_DECLINED"
    finally:
        _clear_auth(_billing_app)
