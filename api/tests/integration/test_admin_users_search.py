"""Story 6.1 — admin /admin/users 통합 테스트 (TestClient + 의존성 mock).

본 테스트는 require_admin 가드, 필터 검증, 페이지네이션 422, 카드 4자리 분기,
404 NOT_FOUND 분기를 HTTP 레이어에서 검증한다.
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
from api.src.schemas.admin.users import (
    SubscriptionSummary,
    UserDetailResponse,
    UserSearchItem,
    UserSearchListResponse,
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
    user.current_session_id = None
    user.admin_grade = "master"
    return user


def _stub_session_dependency():
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()

    async def gen():
        yield session

    return gen


def _make_search_item(
    user_id: int = 1,
    email: str = "user@example.com",
    subscription_status: str = "free",
) -> UserSearchItem:
    return UserSearchItem(
        user_id=user_id,
        email=email,
        phone="01012345678",
        segment="doctor",
        years_of_experience=5,
        subscription_status=subscription_status,
        is_blocked=(subscription_status == "blocked"),
        block_until=None,
        daily_quota_override=None,
        created_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        last_login_at=None,
        withdrawn_at=None,
        pro_since=None,
        card_last4=None,
        card_company=None,
    )


@pytest.mark.asyncio
class TestAdminUsersAuth:
    async def test_unauthenticated_returns_401(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.get("/api/v1/admin/users")
        assert res.status_code == 401


@pytest.mark.asyncio
class TestAdminUsersList:
    async def _call(self, qs: str = "") -> object:
        token = _make_admin_jwt()
        admin = _make_admin()
        gen = _stub_session_dependency()
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
            app.dependency_overrides[get_session] = gen
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.get(
                        f"/api/v1/admin/users{qs}",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()
        return res

    async def test_list_returns_200_with_default_pagination(self):
        items = [_make_search_item(user_id=1)]
        response = UserSearchListResponse(
            items=items, page=1, per_page=20, total=1
        )
        with patch(
            "api.src.routers.admin.users.admin_user_service.search_users",
            new=AsyncMock(return_value=response),
        ):
            res = await self._call()
        assert res.status_code == 200
        body = res.json()
        assert body["page"] == 1
        assert body["per_page"] == 20
        assert body["total"] == 1
        assert len(body["items"]) == 1
        assert body["items"][0]["user_id"] == 1

    async def test_list_with_q_param_passes_through(self):
        items = [_make_search_item(email="abc@naver.com")]
        response = UserSearchListResponse(
            items=items, page=1, per_page=20, total=1
        )
        with patch(
            "api.src.routers.admin.users.admin_user_service.search_users",
            new=AsyncMock(return_value=response),
        ) as service_mock:
            res = await self._call("?q=naver")
        assert res.status_code == 200
        # service에 q='naver'가 전달됐는지 확인
        kwargs = service_mock.call_args.kwargs
        assert kwargs.get("q") == "naver"

    async def test_list_with_segment_filter(self):
        response = UserSearchListResponse(items=[], page=1, per_page=20, total=0)
        with patch(
            "api.src.routers.admin.users.admin_user_service.search_users",
            new=AsyncMock(return_value=response),
        ) as service_mock:
            res = await self._call("?segment=doctor")
        assert res.status_code == 200
        assert service_mock.call_args.kwargs.get("segment") == "doctor"

    async def test_list_with_blocked_true_filter(self):
        response = UserSearchListResponse(items=[], page=1, per_page=20, total=0)
        with patch(
            "api.src.routers.admin.users.admin_user_service.search_users",
            new=AsyncMock(return_value=response),
        ) as service_mock:
            res = await self._call("?blocked=true")
        assert res.status_code == 200
        assert service_mock.call_args.kwargs.get("blocked") is True

    async def test_list_with_combined_filters(self):
        response = UserSearchListResponse(items=[], page=1, per_page=20, total=0)
        with patch(
            "api.src.routers.admin.users.admin_user_service.search_users",
            new=AsyncMock(return_value=response),
        ) as service_mock:
            res = await self._call("?q=test&segment=doctor&subscription_status=pro")
        assert res.status_code == 200
        kwargs = service_mock.call_args.kwargs
        assert kwargs.get("q") == "test"
        assert kwargs.get("segment") == "doctor"
        assert kwargs.get("subscription_status") == "pro"

    async def test_list_per_page_over_max_returns_422(self):
        res = await self._call("?per_page=200")
        assert res.status_code == 422

    async def test_list_per_page_zero_returns_422(self):
        res = await self._call("?per_page=0")
        assert res.status_code == 422

    async def test_list_q_4digit_card_match(self):
        item = _make_search_item(user_id=42)
        item = item.model_copy(update={"card_last4": "1234", "card_company": "신한"})
        response = UserSearchListResponse(
            items=[item], page=1, per_page=20, total=1
        )
        with patch(
            "api.src.routers.admin.users.admin_user_service.search_users",
            new=AsyncMock(return_value=response),
        ):
            res = await self._call("?q=1234")
        assert res.status_code == 200
        body = res.json()
        assert body["items"][0]["card_last4"] == "1234"

    async def test_list_invalid_segment_enum_returns_422(self):
        res = await self._call("?segment=invalid_value")
        assert res.status_code == 422


@pytest.mark.asyncio
class TestAdminUserDetail:
    async def _call(self, user_id: int) -> object:
        token = _make_admin_jwt()
        admin = _make_admin()
        gen = _stub_session_dependency()
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
            app.dependency_overrides[get_session] = gen
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.get(
                        f"/api/v1/admin/users/{user_id}",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()
        return res

    async def test_detail_returns_200_for_existing_user(self):
        item = _make_search_item(user_id=1, subscription_status="pro")
        response = UserDetailResponse(
            user=item,
            subscription_summary=SubscriptionSummary(
                current_status="pro",
                billing_key_active=True,
                card_last4="1234",
                card_company="신한",
                subscription_started_at=None,
                next_charge_at=None,
            ),
            recent_qa=[],
            recent_anomaly_events=[],
        )
        with patch(
            "api.src.routers.admin.users.admin_user_service.get_user_detail",
            new=AsyncMock(return_value=response),
        ):
            res = await self._call(1)
        assert res.status_code == 200
        body = res.json()
        assert body["user"]["user_id"] == 1
        assert body["subscription_summary"]["billing_key_active"] is True

    async def test_detail_404_for_missing_user(self):
        from fastapi import HTTPException

        with patch(
            "api.src.routers.admin.users.admin_user_service.get_user_detail",
            new=AsyncMock(
                side_effect=HTTPException(
                    status_code=404,
                    detail={
                        "code": "ADMIN_USER_NOT_FOUND",
                        "message": "사용자를 찾을 수 없습니다.",
                    },
                )
            ),
        ):
            res = await self._call(99999)
        assert res.status_code == 404
        body = res.json()
        assert body["code"] == "ADMIN_USER_NOT_FOUND"
