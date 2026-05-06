"""Story 6.2 — admin /admin/audit-logs action_in / target_id / email JOIN 테스트.

본 테스트는 Story 6.2에서 추가된 신규 query 파라미터와 응답 필드를 검증한다.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest
from httpx import ASGITransport, AsyncClient

from api.src.main import app
from api.src.models.base import get_session
from api.src.settings import settings


def _make_admin_jwt() -> str:
    payload = {
        "sub": "1",
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


def _make_audit_row(
    *,
    id_: int,
    actor_user_id: int,
    target_id: int | None,
    action: str = "user.permission_edit",
    diff: dict | None = None,
) -> MagicMock:
    log = MagicMock()
    log.id = id_
    log.actor_user_id = actor_user_id
    log.action = action
    log.target_type = "user" if target_id is not None else None
    log.target_id = target_id
    log.diff_json = diff
    log.ip = "127.0.0.1"
    log.ua = "pytest"
    log.trace_id = uuid.uuid4()
    log.created_at = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)
    return log


def _make_email_row(user_id: int, email: str) -> MagicMock:
    row = MagicMock()
    row.id = user_id
    row.email = email
    return row


@pytest.mark.asyncio
class TestAuditLogsExtended:
    async def _call(self, qs: str = ""):
        token = _make_admin_jwt()
        admin = _make_admin()

        # Mock execute results: count(scalar_one) → list(scalars().all()) → email JOIN(.all())
        log1 = _make_audit_row(
            id_=10,
            actor_user_id=1,
            target_id=42,
            action="user.permission_edit",
            diff={
                "before": {"daily_quota_override": None},
                "after": {"daily_quota_override": 50},
            },
        )
        log2 = _make_audit_row(
            id_=11,
            actor_user_id=1,
            target_id=42,
            action="user.block_auto_expired",
            diff={
                "before": {"subscription_status": "blocked"},
                "after": {"subscription_status": "free"},
            },
        )
        emails = [
            _make_email_row(1, "admin@denvia.local"),
            _make_email_row(42, "target@example.com"),
        ]

        count_result = MagicMock()
        count_result.scalar_one = MagicMock(return_value=2)

        items_result = MagicMock()
        items_result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[log1, log2]))
        )

        email_result = MagicMock()
        email_result.all = MagicMock(return_value=emails)

        session = MagicMock()
        session.execute = AsyncMock(side_effect=[count_result, items_result, email_result])

        async def gen():
            yield session

        with patch(
            "api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)
        ):
            app.dependency_overrides[get_session] = gen
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.get(
                        f"/api/v1/admin/audit-logs{qs}",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()
        return res

    async def test_response_includes_diff_and_email_fields(self):
        res = await self._call("?action_in=user.permission_edit,user.block_auto_expired&target_id=42")
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 2
        items = body["items"]
        assert len(items) == 2
        assert items[0]["actor_email"] == "admin@denvia.local"
        assert items[0]["target_email"] == "target@example.com"
        assert items[0]["diff_json"]["after"]["daily_quota_override"] == 50

    async def test_action_in_single_value(self):
        res = await self._call("?action_in=user.permission_edit")
        assert res.status_code == 200

    async def test_target_id_filter(self):
        res = await self._call("?target_id=42")
        assert res.status_code == 200

    async def test_legacy_action_filter_still_works(self):
        res = await self._call("?action_filter=user")
        assert res.status_code == 200

    # Story 6.3 — user.speed_override 단일 액션 필터 회귀
    async def test_action_in_user_speed_override(self):
        """Story 6.3 — action_in=user.speed_override 단일 필터 동작 확인."""
        token = _make_admin_jwt()
        admin = _make_admin()

        log_speed = _make_audit_row(
            id_=20,
            actor_user_id=1,
            target_id=42,
            action="user.speed_override",
            diff={
                "before": {"free_delay_override": None},
                "after": {"free_delay_override": 1.5},
            },
        )
        emails = [
            _make_email_row(1, "admin@denvia.local"),
            _make_email_row(42, "target@example.com"),
        ]

        count_result = MagicMock()
        count_result.scalar_one = MagicMock(return_value=1)
        items_result = MagicMock()
        items_result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[log_speed]))
        )
        email_result = MagicMock()
        email_result.all = MagicMock(return_value=emails)

        session = MagicMock()
        session.execute = AsyncMock(
            side_effect=[count_result, items_result, email_result]
        )

        async def gen():
            yield session

        with patch(
            "api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)
        ):
            app.dependency_overrides[get_session] = gen
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.get(
                        "/api/v1/admin/audit-logs?action_in=user.speed_override&target_id=42",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()

        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 1
        assert body["items"][0]["action"] == "user.speed_override"
        assert body["items"][0]["diff_json"]["after"]["free_delay_override"] == 1.5
