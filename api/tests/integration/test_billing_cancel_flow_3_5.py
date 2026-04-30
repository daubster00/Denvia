"""빌링 해지/철회 통합 테스트 — Story 3.5.

POST /billing/subscriptions/cancel, /resume, GET /billing/subscriptions/current 검증.
finalize_cancellations 배치 동작 검증.
DB는 mock으로 처리하고 라우터 ↔ 서비스 경계만 통합 테스트.
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


def _scalar_result(obj) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none = MagicMock(return_value=obj)
    return r


def _scalars_result(objs: list) -> MagicMock:
    r = MagicMock()
    r.scalars.return_value.all.return_value = objs
    return r


def _make_subscription_mock(
    sub_id: int = 50,
    user_id: int = 1,
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


# ── 인증 검증 ──────────────────────────────────────────────────────────────────


def test_cancel_unauthenticated_returns_401(client):
    resp = client.post(
        "/api/v1/billing/subscriptions/cancel",
        json={"reason": "사유"},
    )
    assert resp.status_code == 401


def test_resume_unauthenticated_returns_401(client):
    resp = client.post("/api/v1/billing/subscriptions/resume")
    assert resp.status_code == 401


def test_current_unauthenticated_returns_401(client):
    resp = client.get("/api/v1/billing/subscriptions/current")
    assert resp.status_code == 401


# ── POST /cancel ───────────────────────────────────────────────────────────────


def test_cancel_success(_billing_app, client):
    """정상 cancel: 200 + status='cancel_pending'."""
    user = _make_user()
    _inject_auth(_billing_app, user)

    mock_result = {
        "status": "cancel_pending",
        "effective_at": "2026-05-29T00:00:00+00:00",
    }

    try:
        with patch(
            "api.src.routers.billing.cancel_subscription",
            new=AsyncMock(return_value=mock_result),
        ):
            resp = client.post(
                "/api/v1/billing/subscriptions/cancel",
                json={"reason": "비용 부담"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "cancel_pending"
        assert data["effective_at"] == "2026-05-29T00:00:00+00:00"
    finally:
        _clear_auth(_billing_app)


def test_cancel_already_canceled_returns_409(_billing_app, client):
    from api.src.services.billing_service import SubscriptionAlreadyCanceled

    user = _make_user()
    _inject_auth(_billing_app, user)

    try:
        with patch(
            "api.src.routers.billing.cancel_subscription",
            new=AsyncMock(side_effect=SubscriptionAlreadyCanceled()),
        ):
            resp = client.post(
                "/api/v1/billing/subscriptions/cancel",
                json={"reason": "사유"},
            )
        assert resp.status_code == 409
        assert resp.json()["code"] == "SUBSCRIPTION_ALREADY_CANCELED"
    finally:
        _clear_auth(_billing_app)


def test_cancel_no_subscription_returns_404(_billing_app, client):
    from api.src.services.billing_service import SubscriptionNotFound

    user = _make_user(subscription_status="free")
    _inject_auth(_billing_app, user)

    try:
        with patch(
            "api.src.routers.billing.cancel_subscription",
            new=AsyncMock(side_effect=SubscriptionNotFound()),
        ):
            resp = client.post(
                "/api/v1/billing/subscriptions/cancel",
                json={"reason": "사유"},
            )
        assert resp.status_code == 404
        assert resp.json()["code"] == "SUBSCRIPTION_NOT_FOUND"
    finally:
        _clear_auth(_billing_app)


def test_cancel_empty_reason_returns_422(_billing_app, client):
    """빈 reason → 422 (schema validator)."""
    user = _make_user()
    _inject_auth(_billing_app, user)

    try:
        resp = client.post(
            "/api/v1/billing/subscriptions/cancel",
            json={"reason": "   "},
        )
        assert resp.status_code == 422
    finally:
        _clear_auth(_billing_app)


def test_cancel_too_long_reason_returns_422(_billing_app, client):
    user = _make_user()
    _inject_auth(_billing_app, user)

    try:
        resp = client.post(
            "/api/v1/billing/subscriptions/cancel",
            json={"reason": "x" * 501},
        )
        assert resp.status_code == 422
    finally:
        _clear_auth(_billing_app)


# ── POST /resume ───────────────────────────────────────────────────────────────


def test_resume_success(_billing_app, client):
    user = _make_user()
    _inject_auth(_billing_app, user)

    mock_result = {
        "status": "active",
        "next_charge_at": "2026-05-29T00:00:00+00:00",
    }

    try:
        with patch(
            "api.src.routers.billing.resume_subscription",
            new=AsyncMock(return_value=mock_result),
        ):
            resp = client.post("/api/v1/billing/subscriptions/resume")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active"
        assert data["next_charge_at"] == "2026-05-29T00:00:00+00:00"
    finally:
        _clear_auth(_billing_app)


def test_resume_already_canceled_returns_409(_billing_app, client):
    from api.src.services.billing_service import SubscriptionAlreadyCanceled

    user = _make_user()
    _inject_auth(_billing_app, user)

    try:
        with patch(
            "api.src.routers.billing.resume_subscription",
            new=AsyncMock(side_effect=SubscriptionAlreadyCanceled()),
        ):
            resp = client.post("/api/v1/billing/subscriptions/resume")
        assert resp.status_code == 409
        assert resp.json()["code"] == "SUBSCRIPTION_ALREADY_CANCELED"
    finally:
        _clear_auth(_billing_app)


def test_resume_not_applicable_returns_409(_billing_app, client):
    from api.src.services.billing_service import ResumeNotApplicable

    user = _make_user()
    _inject_auth(_billing_app, user)

    try:
        with patch(
            "api.src.routers.billing.resume_subscription",
            new=AsyncMock(side_effect=ResumeNotApplicable()),
        ):
            resp = client.post("/api/v1/billing/subscriptions/resume")
        assert resp.status_code == 409
        assert resp.json()["code"] == "SUBSCRIPTION_NOT_CANCELED"
    finally:
        _clear_auth(_billing_app)


# ── GET /current ───────────────────────────────────────────────────────────────


def test_current_active(_billing_app, client):
    user = _make_user()
    _inject_auth(_billing_app, user)

    mock_result = {
        "status": "active",
        "started_at": "2026-04-01T00:00:00+00:00",
        "current_period_end": "2026-05-01T00:00:00+00:00",
        "next_charge_at": "2026-05-01T00:00:00+00:00",
        "canceled_at": None,
        "cancel_reason": None,
    }

    try:
        with patch(
            "api.src.routers.billing.get_current_subscription",
            new=AsyncMock(return_value=mock_result),
        ):
            resp = client.get("/api/v1/billing/subscriptions/current")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active"
        assert data["next_charge_at"] == "2026-05-01T00:00:00+00:00"
    finally:
        _clear_auth(_billing_app)


def test_current_cancel_pending(_billing_app, client):
    user = _make_user()
    _inject_auth(_billing_app, user)

    mock_result = {
        "status": "cancel_pending",
        "started_at": "2026-04-01T00:00:00+00:00",
        "current_period_end": "2026-05-01T00:00:00+00:00",
        "next_charge_at": "2026-05-01T00:00:00+00:00",
        "canceled_at": "2026-04-15T00:00:00+00:00",
        "cancel_reason": "사용 빈도 감소",
    }

    try:
        with patch(
            "api.src.routers.billing.get_current_subscription",
            new=AsyncMock(return_value=mock_result),
        ):
            resp = client.get("/api/v1/billing/subscriptions/current")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "cancel_pending"
        assert data["cancel_reason"] == "사용 빈도 감소"
    finally:
        _clear_auth(_billing_app)


def test_current_none(_billing_app, client):
    user = _make_user(subscription_status="free")
    _inject_auth(_billing_app, user)

    mock_result = {
        "status": "none",
        "started_at": None,
        "current_period_end": None,
        "next_charge_at": None,
        "canceled_at": None,
        "cancel_reason": None,
    }

    try:
        with patch(
            "api.src.routers.billing.get_current_subscription",
            new=AsyncMock(return_value=mock_result),
        ):
            resp = client.get("/api/v1/billing/subscriptions/current")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "none"
        assert data["next_charge_at"] is None
    finally:
        _clear_auth(_billing_app)


# ── finalize_cancellations 배치 ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_finalize_cancellations_e2e_canceled():
    """cancel_pending+expired 1건 → canceled + users.subscription_status='free' + next_charge_at NULL."""
    from api.src.services.billing_service import finalize_cancellations

    sub = _make_subscription_mock(status="cancel_pending", period_end_offset_days=-1)

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalars_result([sub]),
            _scalar_result(sub),
            MagicMock(),  # User update
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
    assert result["finalized"] == 1


@pytest.mark.asyncio
async def test_finalize_cancellations_skips_not_expired():
    """cancel_pending+not_expired → 스캔 0(쿼리 필터에서 자동 제외)."""
    from api.src.services.billing_service import finalize_cancellations

    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalars_result([]))

    result = await finalize_cancellations(db)

    assert result["scanned"] == 0
    assert result["finalized"] == 0


# ── scan_renewals 회귀: cancel_pending 자동 제외 ──────────────────────────────


@pytest.mark.asyncio
async def test_scan_renewals_excludes_cancel_pending_after_3_5():
    """Story 3.3 회귀 — cancel_pending 구독은 send_task 호출되지 않음."""
    from api.src.services.billing_service import scan_renewals

    # cancel_pending만 있는 상황 → ORM where status='active'에서 빈 결과
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalars_result([]))

    with patch("api.src.workers.celery_app.celery_app") as mock_celery_app:
        result = await scan_renewals(db)

    assert result["enqueued"] == 0
    mock_celery_app.send_task.assert_not_called()


# ── Beat 스케줄 등록 검증 ─────────────────────────────────────────────────────


def test_beat_schedule_includes_finalize_cancellations():
    """celery_app.beat_schedule에 finalize-cancellations-hourly-15가 등록되어야 한다."""
    from api.src.workers.celery_app import celery_app

    schedule = celery_app.conf.beat_schedule
    assert "finalize-cancellations-hourly-15" in schedule
    entry = schedule["finalize-cancellations-hourly-15"]
    assert entry["task"] == "billing.finalize_cancellations"
    # crontab(minute=15) — 분 슬롯이 15
    cron = entry["schedule"]
    assert hasattr(cron, "minute")
    # crontab.minute는 set 타입
    assert 15 in cron.minute


# ── migration 0016 — next_charge_at NULLABLE ─────────────────────────────────

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
    """alembic upgrade head."""
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", DB_SYNC_URL)
    command.upgrade(alembic_cfg, "head")
    yield


@pytest.mark.asyncio
async def test_migration_0016_next_charge_at_is_nullable(_run_migrations):
    """subscriptions.next_charge_at 컬럼은 nullable이어야 한다."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name='subscriptions' AND column_name='next_charge_at'"
            )
        )
        row = result.fetchone()
    await engine.dispose()
    assert row is not None
    assert row[0] == "YES", "next_charge_at 컬럼은 nullable이어야 함"
