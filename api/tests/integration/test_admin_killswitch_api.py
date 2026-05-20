"""Story 9.2 — admin/killswitch 통합 테스트.

신규 endpoint:
- GET  /api/v1/admin/killswitch/status
- POST /api/v1/admin/killswitch/manual/activate
- POST /api/v1/admin/killswitch/manual/deactivate
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest
from httpx import ASGITransport, AsyncClient

from api.src.deps.redis import get_redis_runtime
from api.src.main import app
from api.src.models.base import get_session
from api.src.services.killswitch_service import (
    DeactivationResult,
    KillSwitchAlreadyActive,
    KillSwitchNotActive,
)
from api.src.settings import settings


async def _fake_redis_runtime():
    """get_redis_runtime override — .get(KEY) → None → DEFAULT_USD_TO_KRW(1400) 폴백."""
    mock = MagicMock()
    mock.get = AsyncMock(return_value=None)
    yield mock


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
    user.id = 99
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


@pytest.mark.asyncio
class TestKillswitchAuth:
    async def test_status_unauthenticated_returns_401(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.get("/api/v1/admin/killswitch/status")
        assert res.status_code == 401

    async def test_activate_unauthenticated_returns_401(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.post(
                "/api/v1/admin/killswitch/manual/activate",
                json={"reason": "test reason 1234"},
            )
        assert res.status_code == 401


@pytest.mark.asyncio
class TestKillswitchStatus:
    async def test_returns_inactive_status_with_no_store_header(self):
        token = _make_admin_jwt()
        admin = _make_admin()
        gen = _stub_session()
        payload = {
            "auto_free_only": {
                "active": False,
                "activated_at": None,
                "year_month": "2026-05",
                "current_percent": 12.5,
                "monthly_limit_usd": Decimal("100.00"),
                "spent_usd": Decimal("12.50"),
                "monthly_limit_krw": 140_000,
                "spent_krw": 17_500,
                "usd_to_krw": 1400,
            },
            "manual_total": {
                "active": False,
                "activated_at": None,
                "deactivated_at": None,
                "reason": None,
                "activated_by_admin_email": None,
                "activated_by_admin_id": None,
            },
        }
        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
            patch(
                "api.src.routers.admin.killswitch.get_status",
                new=AsyncMock(return_value=payload),
            ),
        ):
            app.dependency_overrides[get_session] = gen
            app.dependency_overrides[get_redis_runtime] = _fake_redis_runtime
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.get(
                        "/api/v1/admin/killswitch/status",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()
        assert res.status_code == 200
        assert res.headers.get("Cache-Control") == "no-store"
        body = res.json()
        assert body["auto_free_only"]["active"] is False
        assert body["manual_total"]["active"] is False
        assert body["auto_free_only"]["year_month"] == "2026-05"


@pytest.mark.asyncio
class TestKillswitchActivate:
    async def test_reason_too_short_returns_422(self):
        token = _make_admin_jwt()
        admin = _make_admin()
        gen = _stub_session()
        with patch(
            "api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)
        ):
            app.dependency_overrides[get_session] = gen
            app.dependency_overrides[get_redis_runtime] = _fake_redis_runtime
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.post(
                        "/api/v1/admin/killswitch/manual/activate",
                        json={"reason": "abc"},
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()
        assert res.status_code == 422

    async def test_already_active_returns_409(self):
        token = _make_admin_jwt()
        admin = _make_admin()
        gen = _stub_session()
        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
            patch(
                "api.src.routers.admin.killswitch.activate_manual",
                new=AsyncMock(side_effect=KillSwitchAlreadyActive("dup")),
            ),
        ):
            app.dependency_overrides[get_session] = gen
            app.dependency_overrides[get_redis_runtime] = _fake_redis_runtime
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.post(
                        "/api/v1/admin/killswitch/manual/activate",
                        json={"reason": "OpenAI 장애 대응"},
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()
        assert res.status_code == 409
        assert res.json()["code"] == "KILLSWITCH_ALREADY_ACTIVE"

    async def test_activate_success_returns_200(self):
        token = _make_admin_jwt()
        admin = _make_admin()
        gen = _stub_session()
        row = MagicMock()
        row.id = 42
        row.activated_at = datetime.now(timezone.utc)
        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
            patch(
                "api.src.routers.admin.killswitch.activate_manual",
                new=AsyncMock(return_value=row),
            ),
            patch(
                "api.src.routers.admin.killswitch.publish_killswitch_event",
                new=AsyncMock(),
            ),
        ):
            app.dependency_overrides[get_session] = gen
            app.dependency_overrides[get_redis_runtime] = _fake_redis_runtime
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.post(
                        "/api/v1/admin/killswitch/manual/activate",
                        json={"reason": "OpenAI 장애 대응 — 11/24 14:00 KST 응답 지연"},
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()
        assert res.status_code == 200
        body = res.json()
        assert body["id"] == 42
        assert body["mode"] == "manual_total"
        assert body["active"] is True


@pytest.mark.asyncio
class TestKillswitchDeactivate:
    async def test_not_active_returns_409(self):
        token = _make_admin_jwt()
        admin = _make_admin()
        gen = _stub_session()
        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
            patch(
                "api.src.routers.admin.killswitch.deactivate_manual",
                new=AsyncMock(side_effect=KillSwitchNotActive("none")),
            ),
        ):
            app.dependency_overrides[get_session] = gen
            app.dependency_overrides[get_redis_runtime] = _fake_redis_runtime
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.post(
                        "/api/v1/admin/killswitch/manual/deactivate",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()
        assert res.status_code == 409
        assert res.json()["code"] == "KILLSWITCH_NOT_ACTIVE"

    async def test_deactivate_enqueue_failure_returns_503_with_state_id(self):
        """broker 장애로 send_task가 실패하면 503 + killswitch_state_id를 반환한다.
        해제는 이미 DB에 commit됐으므로 운영자가 requeue-extension으로 복구 가능하다.
        """
        token = _make_admin_jwt()
        admin = _make_admin()
        gen = _stub_session()
        now = datetime.now(timezone.utc)
        result = DeactivationResult(
            killswitch_state_id=42,
            activated_at=now - timedelta(hours=2),
            deactivated_at=now,
            duration_seconds=7200,
        )
        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
            patch(
                "api.src.routers.admin.killswitch.deactivate_manual",
                new=AsyncMock(return_value=result),
            ),
            patch(
                "api.src.workers.celery_app.celery_app.send_task",
                side_effect=Exception("broker connection refused"),
            ),
        ):
            app.dependency_overrides[get_session] = gen
            app.dependency_overrides[get_redis_runtime] = _fake_redis_runtime
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.post(
                        "/api/v1/admin/killswitch/manual/deactivate",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()
        assert res.status_code == 503
        body = res.json()
        assert body["code"] == "EXTENSION_ENQUEUE_FAILED"
        # 커스텀 예외 핸들러가 code/message 외 필드를 details에 중첩함 (main.py §416)
        assert body["details"]["killswitch_state_id"] == 42

    async def test_deactivate_success_enqueues_celery_task(self):
        token = _make_admin_jwt()
        admin = _make_admin()
        gen = _stub_session()
        now = datetime.now(timezone.utc)
        result = DeactivationResult(
            killswitch_state_id=42,
            activated_at=now - timedelta(hours=2),
            deactivated_at=now,
            duration_seconds=7200,
        )
        celery_task = MagicMock()
        celery_task.id = "celery-task-id-abc"
        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
            patch(
                "api.src.routers.admin.killswitch.deactivate_manual",
                new=AsyncMock(return_value=result),
            ),
            patch(
                "api.src.workers.celery_app.celery_app.send_task",
                return_value=celery_task,
            ) as send_task_mock,
            patch(
                "api.src.routers.admin.killswitch.publish_killswitch_event",
                new=AsyncMock(),
            ),
        ):
            app.dependency_overrides[get_session] = gen
            app.dependency_overrides[get_redis_runtime] = _fake_redis_runtime
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.post(
                        "/api/v1/admin/killswitch/manual/deactivate",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()
        assert res.status_code == 200
        body = res.json()
        assert body["id"] == 42
        assert body["duration_seconds"] == 7200
        assert body["extension_task_id"] == "celery-task-id-abc"
        send_task_mock.assert_called_once()
        args, kwargs = send_task_mock.call_args
        assert args[0] == "billing.extend_subscriptions_for_killswitch_duration"
        assert kwargs.get("args") == [42]


@pytest.mark.asyncio
class TestKillswitchRequeueExtension:
    async def test_requeue_extension_state_not_found_returns_404(self):
        token = _make_admin_jwt()
        admin = _make_admin()

        session = MagicMock()
        session.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=None)
        ))
        session.commit = AsyncMock()

        async def gen():
            yield session

        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
            app.dependency_overrides[get_session] = gen
            app.dependency_overrides[get_redis_runtime] = _fake_redis_runtime
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.post(
                        "/api/v1/admin/killswitch/manual/requeue-extension/999",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()
        assert res.status_code == 404
        assert res.json()["code"] == "KILLSWITCH_STATE_NOT_FOUND"

    async def test_requeue_extension_success_returns_task_id(self):
        token = _make_admin_jwt()
        admin = _make_admin()

        ks_mock = MagicMock()
        ks_mock.id = 42
        session = MagicMock()
        session.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=ks_mock)
        ))
        session.commit = AsyncMock()

        async def gen():
            yield session

        celery_task = MagicMock()
        celery_task.id = "requeue-task-id-xyz"

        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
            patch(
                "api.src.workers.celery_app.celery_app.send_task",
                return_value=celery_task,
            ) as send_task_mock,
        ):
            app.dependency_overrides[get_session] = gen
            app.dependency_overrides[get_redis_runtime] = _fake_redis_runtime
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.post(
                        "/api/v1/admin/killswitch/manual/requeue-extension/42",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()
        assert res.status_code == 200
        body = res.json()
        assert body["id"] == 42
        assert body["extension_task_id"] == "requeue-task-id-xyz"
        send_task_mock.assert_called_once()
