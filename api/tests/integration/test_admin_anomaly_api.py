"""Story 6.5 — Admin /api/v1/admin/anomaly 통합 테스트.

본 테스트는 require_admin 가드, payload 검증, 422/404/409 분기를 HTTP 레이어에서 검증한다.
서비스 레이어는 mock으로 단순화 — 실제 서비스 분기는 unit 테스트가 커버.
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


def _make_non_admin():
    user = MagicMock()
    user.id = 5
    user.email = "user@example.com"
    user.role = "user"
    user.subscription_status = "free"
    user.segment = None
    user.withdrawn_at = None
    user.must_reset_password = False
    return user


def _stub_session_dependency():
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.get = AsyncMock()

    async def gen():
        yield session

    return gen


def _make_event(status="new"):
    return {
        "id": 1,
        "type": "rapid_questions",
        "target_user_id": 7,
        "target_user_email_masked": "u**@example.com",
        "ip": "1.2.3.4",
        "ua": "ua",
        "details": {"count_in_window": 3},
        "status": status,
        "reviewed_by_admin_id": None,
        "reviewed_at": None,
        "created_at": datetime(2026, 5, 1, tzinfo=timezone.utc),
    }


@pytest.mark.asyncio
class TestAdminAnomalyListAuth:
    async def test_no_cookie_returns_401(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.get("/api/v1/admin/anomaly")
        assert res.status_code == 401

    async def test_non_admin_returns_401(self):
        token = _make_admin_jwt(user_id=5)
        non_admin = _make_non_admin()
        gen = _stub_session_dependency()
        with patch(
            "api.src.deps.auth.get_user_by_id",
            new=AsyncMock(return_value=non_admin),
        ):
            app.dependency_overrides[get_session] = gen
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.get(
                        "/api/v1/admin/anomaly",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()
        assert res.status_code == 401


@pytest.mark.asyncio
class TestAdminAnomalyList:
    async def _call(self, params: dict | None = None):
        token = _make_admin_jwt()
        admin = _make_admin()
        gen = _stub_session_dependency()
        with patch(
            "api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)
        ):
            app.dependency_overrides[get_session] = gen
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.get(
                        "/api/v1/admin/anomaly",
                        params=params or {},
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()
        return res

    async def test_default_returns_200_with_pagination(self):
        with patch(
            "api.src.routers.admin.anomaly.anomaly_service.list_anomaly_events",
            new=AsyncMock(
                return_value={
                    "items": [_make_event()],
                    "page": 1,
                    "per_page": 20,
                    "total": 1,
                }
            ),
        ) as svc:
            res = await self._call()
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 1
        assert body["items"][0]["type"] == "rapid_questions"
        svc.assert_awaited_once()

    async def test_type_in_filter_passes_through(self):
        with patch(
            "api.src.routers.admin.anomaly.anomaly_service.list_anomaly_events",
            new=AsyncMock(
                return_value={"items": [], "page": 1, "per_page": 20, "total": 0}
            ),
        ) as svc:
            res = await self._call(
                {"type_in": "login_brute_force,rapid_questions"}
            )
        assert res.status_code == 200
        # type_in 파싱 검증
        kwargs = svc.call_args.kwargs
        assert kwargs["type_in"] == ["login_brute_force", "rapid_questions"]

    async def test_invalid_type_returns_422(self):
        res = await self._call({"type_in": "bad_value"})
        assert res.status_code == 422
        assert res.json()["code"] == "ANOMALY_FILTER_INVALID_VALUE"

    async def test_invalid_status_returns_422(self):
        res = await self._call({"status_in": "not_a_status"})
        assert res.status_code == 422

    async def test_pagination_params(self):
        with patch(
            "api.src.routers.admin.anomaly.anomaly_service.list_anomaly_events",
            new=AsyncMock(
                return_value={"items": [], "page": 3, "per_page": 50, "total": 0}
            ),
        ) as svc:
            res = await self._call({"page": 3, "per_page": 50})
        assert res.status_code == 200
        kwargs = svc.call_args.kwargs
        assert kwargs["page"] == 3
        assert kwargs["per_page"] == 50


@pytest.mark.asyncio
class TestAdminAnomalyPatch:
    async def _call(self, anomaly_id: int, body: dict):
        token = _make_admin_jwt()
        admin = _make_admin()
        gen = _stub_session_dependency()
        with patch(
            "api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)
        ):
            app.dependency_overrides[get_session] = gen
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.patch(
                        f"/api/v1/admin/anomaly/{anomaly_id}",
                        json=body,
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()
        return res

    async def test_mark_reviewed_success(self):
        with patch(
            "api.src.routers.admin.anomaly.anomaly_service.mark_anomaly_reviewed",
            new=AsyncMock(return_value=_make_event(status="reviewed")),
        ) as svc:
            res = await self._call(1, {"status": "reviewed"})
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "reviewed"
        svc.assert_awaited_once()

    async def test_mark_actioned_status_rejected_422(self):
        # 'actioned' 직접 전이는 schema에서 거부됨
        res = await self._call(1, {"status": "actioned"})
        assert res.status_code == 422

    async def test_invalid_status_value_422(self):
        res = await self._call(1, {"status": "garbage"})
        assert res.status_code == 422

    async def test_not_found_404(self):
        with patch(
            "api.src.routers.admin.anomaly.anomaly_service.mark_anomaly_reviewed",
            new=AsyncMock(
                side_effect=HTTPException(
                    status_code=404,
                    detail={
                        "code": "ANOMALY_NOT_FOUND",
                        "message": "이상 이벤트를 찾을 수 없습니다.",
                    },
                )
            ),
        ):
            res = await self._call(999, {"status": "reviewed"})
        assert res.status_code == 404
        assert res.json()["code"] == "ANOMALY_NOT_FOUND"

    async def test_already_actioned_409(self):
        with patch(
            "api.src.routers.admin.anomaly.anomaly_service.mark_anomaly_reviewed",
            new=AsyncMock(
                side_effect=HTTPException(
                    status_code=409,
                    detail={
                        "code": "ANOMALY_ALREADY_ACTIONED",
                        "message": "이미 차단 액션이 적용된 이벤트입니다.",
                    },
                )
            ),
        ):
            res = await self._call(1, {"status": "reviewed"})
        assert res.status_code == 409
        assert res.json()["code"] == "ANOMALY_ALREADY_ACTIONED"
