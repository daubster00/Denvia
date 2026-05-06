"""Story 6.2 — admin PATCH /admin/users/{id} 통합 테스트.

본 테스트는 require_admin 가드, payload 검증, 422 분기를 HTTP 레이어에서 검증한다.
서비스 레이어는 mock으로 단순화 — 실제 서비스 분기는 unit 테스트가 커버.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest
from httpx import ASGITransport, AsyncClient

from api.src.main import app
from api.src.models.base import get_session
from api.src.schemas.admin.users import UserSearchItem
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
    session.refresh = AsyncMock()

    async def gen():
        yield session

    return gen


def _make_response_item(user_id: int = 2) -> UserSearchItem:
    return UserSearchItem(
        user_id=user_id,
        email="patched@example.com",
        phone="01012345678",
        segment="dentist",
        years_of_experience=5,
        subscription_status="free",
        is_blocked=False,
        block_until=None,
        daily_quota_override=50,
        free_delay_override=None,
        created_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        last_login_at=None,
        withdrawn_at=None,
        pro_since=None,
        card_last4=None,
        card_company=None,
    )


@pytest.mark.asyncio
class TestAdminUsersPatchAuth:
    async def test_no_cookie_returns_401(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.patch(
                "/api/v1/admin/users/2",
                json={"daily_quota_override": 50},
            )
        assert res.status_code == 401

    async def test_non_admin_returns_401(self):
        # require_admin은 role!=admin 사용자도 401 ADMIN_AUTH_REQUIRED로 거부
        token = _make_admin_jwt(user_id=5)  # admin이 아닌 user
        non_admin = _make_non_admin()
        gen = _stub_session_dependency()
        with patch(
            "api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=non_admin)
        ):
            app.dependency_overrides[get_session] = gen
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.patch(
                        "/api/v1/admin/users/2",
                        json={"daily_quota_override": 50},
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()
        assert res.status_code == 401
        assert res.json()["code"] == "ADMIN_AUTH_REQUIRED"


@pytest.mark.asyncio
class TestAdminUsersPatchSuccess:
    async def _call(self, body: dict, target: int = 2):
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
                        f"/api/v1/admin/users/{target}",
                        json=body,
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()
        return res

    async def test_quota_update_returns_200(self):
        with patch(
            "api.src.routers.admin.users.user_service.update_permission",
            new=AsyncMock(return_value=_make_response_item()),
        ) as service_mock:
            res = await self._call({"daily_quota_override": 50})
        assert res.status_code == 200
        body = res.json()
        assert body["user_id"] == 2
        assert body["daily_quota_override"] == 50
        # service에 정상 호출 여부 확인
        service_mock.assert_awaited_once()

    async def test_block_action_returns_200(self):
        with patch(
            "api.src.routers.admin.users.user_service.update_permission",
            new=AsyncMock(return_value=_make_response_item()),
        ):
            res = await self._call(
                {
                    "block_action": {
                        "duration_hours": 24,
                        "reason": "테스트 차단",
                    }
                }
            )
        assert res.status_code == 200


@pytest.mark.asyncio
class TestAdminUsersPatchValidation:
    async def _call(self, body: dict):
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
                        "/api/v1/admin/users/2",
                        json=body,
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()
        return res

    async def test_empty_body_returns_422(self):
        # 모든 필드가 None — schema validator가 422 반환
        res = await self._call({})
        assert res.status_code == 422

    async def test_quota_out_of_range_returns_422(self):
        res = await self._call({"daily_quota_override": 99999})
        assert res.status_code == 422

    async def test_quota_zero_returns_422(self):
        res = await self._call({"daily_quota_override": 0})
        assert res.status_code == 422

    async def test_block_duration_too_large_returns_422(self):
        res = await self._call(
            {"block_action": {"duration_hours": 999999, "reason": "x"}}
        )
        assert res.status_code == 422

    async def test_block_reason_too_long_returns_422(self):
        res = await self._call(
            {"block_action": {"duration_hours": 24, "reason": "x" * 201}}
        )
        assert res.status_code == 422

    async def test_block_reason_empty_returns_422(self):
        res = await self._call(
            {"block_action": {"duration_hours": 24, "reason": ""}}
        )
        assert res.status_code == 422


@pytest.mark.asyncio
class TestAdminUsersPatchServiceErrors:
    async def _call_with_service_error(self, status_code: int, code: str, message: str):
        from fastapi import HTTPException
        token = _make_admin_jwt()
        admin = _make_admin()
        gen = _stub_session_dependency()
        with patch(
            "api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)
        ):
            app.dependency_overrides[get_session] = gen
            try:
                with patch(
                    "api.src.routers.admin.users.user_service.update_permission",
                    new=AsyncMock(
                        side_effect=HTTPException(
                            status_code=status_code,
                            detail={"code": code, "message": message},
                        )
                    ),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as client:
                        res = await client.patch(
                            "/api/v1/admin/users/999",
                            json={"daily_quota_override": 50},
                            cookies={"denvia_admin_session": token},
                        )
            finally:
                app.dependency_overrides.clear()
        return res

    async def test_user_not_found_returns_404(self):
        res = await self._call_with_service_error(
            404, "ADMIN_USER_NOT_FOUND", "사용자를 찾을 수 없습니다."
        )
        assert res.status_code == 404
        assert res.json()["code"] == "ADMIN_USER_NOT_FOUND"

    async def test_block_conflict_returns_422(self):
        res = await self._call_with_service_error(
            422,
            "BLOCK_ACTION_CONFLICT",
            "차단과 차단 해제는 동시에 수행할 수 없습니다.",
        )
        assert res.status_code == 422
        assert res.json()["code"] == "BLOCK_ACTION_CONFLICT"

    async def test_pro_grant_confirmation_required_returns_422(self):
        res = await self._call_with_service_error(
            422,
            "PRO_GRANT_CONFIRMATION_REQUIRED",
            "결제 없이 Pro 권한을 부여하려면 확인이 필요합니다.",
        )
        assert res.status_code == 422
        assert res.json()["code"] == "PRO_GRANT_CONFIRMATION_REQUIRED"

    async def test_withdrawn_user_returns_422(self):
        res = await self._call_with_service_error(
            422, "USER_ALREADY_WITHDRAWN", "탈퇴한 사용자는 수정할 수 없습니다."
        )
        assert res.status_code == 422
        assert res.json()["code"] == "USER_ALREADY_WITHDRAWN"


# ── Story 6.3 — speed override PATCH 통합 ─────────────────────────────────────


@pytest.mark.asyncio
class TestAdminUsersPatchSpeed:
    """Story 6.3 — free_delay_override 단독·묶음·clear·422 4 케이스."""

    async def _call(self, body: dict, target: int = 2):
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
                        f"/api/v1/admin/users/{target}",
                        json=body,
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()
        return res

    async def test_speed_set_returns_200(self):
        with patch(
            "api.src.routers.admin.users.user_service.update_permission",
            new=AsyncMock(return_value=_make_response_item()),
        ) as service_mock:
            res = await self._call({"free_delay_override": 1.5})
        assert res.status_code == 200
        service_mock.assert_awaited_once()

    async def test_speed_clear_returns_200(self):
        with patch(
            "api.src.routers.admin.users.user_service.update_permission",
            new=AsyncMock(return_value=_make_response_item()),
        ):
            res = await self._call({"free_delay_override_clear": True})
        assert res.status_code == 200

    async def test_speed_above_30_returns_422_at_pydantic(self):
        # Pydantic ge=0.0/le=30.0 — service 호출 전에 거부
        res = await self._call({"free_delay_override": 31.0})
        assert res.status_code == 422

    async def test_speed_below_zero_returns_422_at_pydantic(self):
        res = await self._call({"free_delay_override": -0.5})
        assert res.status_code == 422

    async def test_speed_conflict_set_and_clear_returns_422(self):
        from fastapi import HTTPException

        token = _make_admin_jwt()
        admin = _make_admin()
        gen = _stub_session_dependency()
        with patch(
            "api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)
        ):
            app.dependency_overrides[get_session] = gen
            try:
                with patch(
                    "api.src.routers.admin.users.user_service.update_permission",
                    new=AsyncMock(
                        side_effect=HTTPException(
                            status_code=422,
                            detail={
                                "code": "SPEED_OVERRIDE_CONFLICT",
                                "message": "응답 속도 설정과 초기화는 동시에 수행할 수 없습니다.",
                            },
                        )
                    ),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as client:
                        res = await client.patch(
                            "/api/v1/admin/users/2",
                            json={
                                "free_delay_override": 2.0,
                                "free_delay_override_clear": True,
                            },
                            cookies={"denvia_admin_session": token},
                        )
            finally:
                app.dependency_overrides.clear()
        assert res.status_code == 422
        assert res.json()["code"] == "SPEED_OVERRIDE_CONFLICT"
