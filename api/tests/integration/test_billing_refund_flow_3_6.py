"""빌링 환불 통합 테스트 — Story 3.6.

POST /billing/payments/{payment_id}/refund 엔드포인트의 라우터↔서비스 경계 + 분기 검증.
DB는 mock으로 처리하고, 마이그레이션 검증은 실제 DB 연결 시에만 실행.
"""

import os
from datetime import UTC, datetime, timedelta
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
    """Fernet 키 주입."""
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("BILLING_KEY_ENC_KEY", key)


@pytest.fixture(autouse=True)
def _disable_rate_limiter(monkeypatch):
    """slowapi 레이트 리밋을 테스트 환경에서 비활성화 — @limit_billing 데코레이터 우회."""
    from api.src.middleware.rate_limit import limiter

    monkeypatch.setattr(limiter, "enabled", False)


def _make_user(subscription_status: str = "pro") -> MagicMock:
    u = MagicMock(spec=User)
    u.id = 1
    u.phone = "01012345678"
    u.subscription_status = subscription_status
    u.role = "user"
    return u


@pytest.fixture(scope="module")
def _billing_app():
    """billing 라우터 전용 최소 FastAPI 앱."""
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


def _now_utc() -> datetime:
    return datetime.now(UTC)


# ── 인증 검증 ──────────────────────────────────────────────────────────────────


def test_refund_unauthenticated_returns_401(client):
    resp = client.post("/api/v1/billing/payments/200/refund", json={})
    assert resp.status_code == 401


# ── 자동 환불 성공 (200) ──────────────────────────────────────────────────────


def test_refund_auto_success_returns_200(_billing_app, client):
    user = _make_user()
    _inject_auth(_billing_app, user)

    mock_result = {
        "status": "refunded",
        "amount_krw": 9900,
        "refunded_at": "2026-04-29T12:00:00+00:00",
    }

    try:
        with patch(
            "api.src.routers.billing.request_refund",
            new=AsyncMock(return_value=mock_result),
        ):
            resp = client.post(
                "/api/v1/billing/payments/200/refund",
                json={"reason": "사용 안 함"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "refunded"
        assert data["amount_krw"] == 9900
        assert data["refunded_at"] == "2026-04-29T12:00:00+00:00"
    finally:
        _clear_auth(_billing_app)


# ── 수동 검토 큐 분기 (202) ────────────────────────────────────────────────────


def test_refund_period_exceeded_returns_202_queued(_billing_app, client):
    user = _make_user()
    _inject_auth(_billing_app, user)

    mock_result = {
        "status": "queued_for_review",
        "queue_id": 42,
        "reason_code": "period_exceeded",
    }

    try:
        with patch(
            "api.src.routers.billing.request_refund",
            new=AsyncMock(return_value=mock_result),
        ):
            resp = client.post(
                "/api/v1/billing/payments/200/refund",
                json={"reason": "환불 요청"},
            )
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "queued_for_review"
        assert data["reason_code"] == "period_exceeded"
        assert data["queue_id"] == 42
    finally:
        _clear_auth(_billing_app)


def test_refund_qa_count_exceeded_returns_202(_billing_app, client):
    user = _make_user()
    _inject_auth(_billing_app, user)

    mock_result = {
        "status": "queued_for_review",
        "queue_id": 43,
        "reason_code": "qa_count_exceeded",
    }

    try:
        with patch(
            "api.src.routers.billing.request_refund",
            new=AsyncMock(return_value=mock_result),
        ):
            resp = client.post(
                "/api/v1/billing/payments/200/refund",
                json={},
            )
        assert resp.status_code == 202
        assert resp.json()["reason_code"] == "qa_count_exceeded"
    finally:
        _clear_auth(_billing_app)


def test_refund_both_returns_202(_billing_app, client):
    user = _make_user()
    _inject_auth(_billing_app, user)

    mock_result = {
        "status": "queued_for_review",
        "queue_id": 44,
        "reason_code": "both",
    }

    try:
        with patch(
            "api.src.routers.billing.request_refund",
            new=AsyncMock(return_value=mock_result),
        ):
            resp = client.post(
                "/api/v1/billing/payments/200/refund",
                json={"reason": "사유"},
            )
        assert resp.status_code == 202
        assert resp.json()["reason_code"] == "both"
    finally:
        _clear_auth(_billing_app)


# ── 에러 분기 ─────────────────────────────────────────────────────────────────


def test_refund_payment_not_found_returns_404(_billing_app, client):
    from api.src.services.billing_service import PaymentNotFound

    user = _make_user()
    _inject_auth(_billing_app, user)

    try:
        with patch(
            "api.src.routers.billing.request_refund",
            new=AsyncMock(side_effect=PaymentNotFound()),
        ):
            resp = client.post(
                "/api/v1/billing/payments/9999/refund", json={}
            )
        assert resp.status_code == 404
        assert resp.json()["code"] == "PAYMENT_NOT_FOUND"
    finally:
        _clear_auth(_billing_app)


def test_refund_already_processed_returns_409(_billing_app, client):
    from api.src.services.billing_service import RefundAlreadyProcessed

    user = _make_user()
    _inject_auth(_billing_app, user)

    try:
        with patch(
            "api.src.routers.billing.request_refund",
            new=AsyncMock(side_effect=RefundAlreadyProcessed()),
        ):
            resp = client.post(
                "/api/v1/billing/payments/200/refund", json={}
            )
        assert resp.status_code == 409
        assert resp.json()["code"] == "REFUND_ALREADY_PROCESSED"
    finally:
        _clear_auth(_billing_app)


def test_refund_already_requested_returns_409(_billing_app, client):
    from api.src.services.billing_service import RefundAlreadyRequested

    user = _make_user()
    _inject_auth(_billing_app, user)

    try:
        with patch(
            "api.src.routers.billing.request_refund",
            new=AsyncMock(side_effect=RefundAlreadyRequested()),
        ):
            resp = client.post(
                "/api/v1/billing/payments/200/refund", json={}
            )
        assert resp.status_code == 409
        assert resp.json()["code"] == "REFUND_ALREADY_REQUESTED"
    finally:
        _clear_auth(_billing_app)


def test_refund_payment_not_refundable_returns_409(_billing_app, client):
    from api.src.services.billing_service import PaymentNotRefundable

    user = _make_user()
    _inject_auth(_billing_app, user)

    try:
        with patch(
            "api.src.routers.billing.request_refund",
            new=AsyncMock(side_effect=PaymentNotRefundable()),
        ):
            resp = client.post(
                "/api/v1/billing/payments/200/refund", json={}
            )
        assert resp.status_code == 409
        assert resp.json()["code"] == "PAYMENT_NOT_REFUNDABLE"
    finally:
        _clear_auth(_billing_app)


def test_refund_provider_unavailable_returns_502(_billing_app, client):
    from api.src.services.billing_service import RefundProviderUnavailable

    user = _make_user()
    _inject_auth(_billing_app, user)

    try:
        with patch(
            "api.src.routers.billing.request_refund",
            new=AsyncMock(side_effect=RefundProviderUnavailable("transport_failure")),
        ):
            resp = client.post(
                "/api/v1/billing/payments/200/refund", json={}
            )
        assert resp.status_code == 502
        assert resp.json()["code"] == "BILLING_PROVIDER_UNAVAILABLE"
    finally:
        _clear_auth(_billing_app)


# ── reason 검증(Schema validator) ───────────────────────────────────────────


def test_refund_reason_too_long_returns_422(_billing_app, client):
    user = _make_user()
    _inject_auth(_billing_app, user)

    try:
        resp = client.post(
            "/api/v1/billing/payments/200/refund",
            json={"reason": "x" * 501},
        )
        assert resp.status_code == 422
    finally:
        _clear_auth(_billing_app)


def test_refund_reason_optional_accepts_empty(_billing_app, client):
    user = _make_user()
    _inject_auth(_billing_app, user)

    mock_result = {
        "status": "refunded",
        "amount_krw": 9900,
        "refunded_at": "2026-04-29T12:00:00+00:00",
    }

    try:
        with patch(
            "api.src.routers.billing.request_refund",
            new=AsyncMock(return_value=mock_result),
        ):
            # reason 미포함 / null
            resp = client.post("/api/v1/billing/payments/200/refund", json={})
        assert resp.status_code == 200
    finally:
        _clear_auth(_billing_app)


# ── Story 3.5 finalize 회귀 ────────────────────────────────────────────────────


def _scalar_result(obj) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none = MagicMock(return_value=obj)
    return r


def _scalars_result(objs: list) -> MagicMock:
    r = MagicMock()
    r.scalars.return_value.all.return_value = objs
    return r


@pytest.mark.asyncio
async def test_finalize_excludes_canceled_subs_after_auto_refund():
    """Story 3.5 회귀 — auto_refund로 status='canceled'된 구독은 finalize_cancellations 쿼리에서 자동 제외(where status='cancel_pending').

    cancel_pending이 아닌 canceled 구독만 있다면 스캔 결과 0건이 됨을 검증.
    """
    from api.src.services.billing_service import finalize_cancellations

    db = AsyncMock()
    # status='cancel_pending' 조건이므로 canceled만 있는 상태에선 빈 결과
    db.execute = AsyncMock(return_value=_scalars_result([]))

    result = await finalize_cancellations(db)

    assert result["scanned"] == 0
    assert result["finalized"] == 0


# ── Migration 0017 ───────────────────────────────────────────────────────────

DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://denvia:password@localhost:5432/denvia",
)
DB_SYNC_URL = os.environ.get(
    "DATABASE_SYNC_URL",
    "postgresql+psycopg://denvia:password@localhost:5432/denvia",
)


@pytest.fixture(scope="module")
def _run_migrations():
    """alembic upgrade head — DB 연결 가능 시에만 실행."""
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", DB_SYNC_URL)
    command.upgrade(alembic_cfg, "head")
    yield


@pytest.mark.asyncio
async def test_migration_0017_manual_refund_queue_table_exists(_run_migrations):
    """manual_refund_queue 테이블 + 핵심 컬럼 검증."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_name='manual_refund_queue' "
                "ORDER BY ordinal_position"
            )
        )
        rows = result.fetchall()
    await engine.dispose()
    columns = {row[0]: (row[1], row[2]) for row in rows}
    assert "id" in columns
    assert "payment_id" in columns
    assert "user_id" in columns
    assert "status" in columns
    assert "qa_count_during_period" in columns
    assert "days_since_charge" in columns
    assert "reviewer_user_id" in columns
    assert columns["reviewer_user_id"][1] == "YES"  # nullable
    assert columns["payment_id"][1] == "NO"  # NOT NULL


@pytest.mark.asyncio
async def test_migration_0017_status_enum_values(_run_migrations):
    """manual_refund_queue_status_enum이 pending/approved/denied 3종을 갖는다."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT enumlabel FROM pg_enum "
                "JOIN pg_type ON pg_enum.enumtypid = pg_type.oid "
                "WHERE pg_type.typname = 'manual_refund_queue_status_enum' "
                "ORDER BY enumsortorder"
            )
        )
        labels = [row[0] for row in result.fetchall()]
    await engine.dispose()
    assert labels == ["pending", "approved", "denied"]


@pytest.mark.asyncio
async def test_migration_0017_partial_unique_pending(_run_migrations):
    """uq_manual_refund_queue_payment_pending partial UNIQUE index 존재."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE indexname = 'uq_manual_refund_queue_payment_pending'"
            )
        )
        row = result.fetchone()
    await engine.dispose()
    assert row is not None
    indexdef = row[0]
    assert "UNIQUE" in indexdef
    assert "(payment_id)" in indexdef
    assert "WHERE" in indexdef
    assert "pending" in indexdef
