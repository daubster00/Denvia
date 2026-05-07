"""admin /admin/support/inquiries 통합 테스트.

require_admin 가드, 목록·상세·PATCH 흐름을 HTTP 레이어에서 검증한다.
admin_users 테스트 패턴을 그대로 차용.
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
from api.src.schemas.admin.support import (
    InquiryDetailResponse,
    InquiryListItem,
    InquiryListResponse,
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


def _stub_session_dependency():
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()

    async def gen():
        yield session

    return gen


def _make_list_item(inquiry_id: int = 1, status: str = "open") -> InquiryListItem:
    return InquiryListItem(
        id=inquiry_id,
        user_id=10,
        user_email="user@example.com",
        subject="결제 환불 문의",
        status=status,
        created_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        resolved_at=None,
    )


def _make_detail(inquiry_id: int = 1, status: str = "open") -> InquiryDetailResponse:
    return InquiryDetailResponse(
        id=inquiry_id,
        user_id=10,
        user_email="user@example.com",
        user_phone="01012345678",
        subject="결제 환불 문의",
        body="환불 절차가 궁금합니다.",
        status=status,
        created_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        resolved_at=None,
        # Story 9.3 신규 필드
        user_segment=None,
        user_subscription_status="active",
        user_created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        recent_qa=[],
        replies=[],
    )


@pytest.mark.asyncio
class TestAdminSupportAuth:
    async def test_unauthenticated_returns_401(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.get("/api/v1/admin/support/inquiries")
        assert res.status_code == 401


@pytest.mark.asyncio
class TestAdminSupportList:
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
                        f"/api/v1/admin/support/inquiries{qs}",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()
        return res

    async def test_list_returns_200_with_default_pagination(self):
        response = InquiryListResponse(
            items=[_make_list_item()], page=1, per_page=20, total=1
        )
        with patch(
            "api.src.routers.admin.support.admin_support_service.list_inquiries",
            new=AsyncMock(return_value=response),
        ):
            res = await self._call()
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == 1

    async def test_list_with_status_filter_passes_through(self):
        response = InquiryListResponse(items=[], page=1, per_page=20, total=0)
        with patch(
            "api.src.routers.admin.support.admin_support_service.list_inquiries",
            new=AsyncMock(return_value=response),
        ) as service_mock:
            res = await self._call("?status=resolved")
        assert res.status_code == 200
        assert service_mock.call_args.kwargs.get("status") == "resolved"

    async def test_list_rejects_invalid_status(self):
        res = await self._call("?status=banana")
        assert res.status_code == 422


@pytest.mark.asyncio
class TestAdminSupportDetail:
    async def _call(self, inquiry_id: int) -> object:
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
                        f"/api/v1/admin/support/inquiries/{inquiry_id}",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()
        return res

    async def test_detail_returns_200(self):
        with patch(
            "api.src.routers.admin.support.admin_support_service.get_inquiry",
            new=AsyncMock(return_value=_make_detail()),
        ):
            res = await self._call(1)
        assert res.status_code == 200
        body = res.json()
        assert body["id"] == 1
        assert body["body"] == "환불 절차가 궁금합니다."

    async def test_detail_returns_404_when_missing(self):
        with patch(
            "api.src.routers.admin.support.admin_support_service.get_inquiry",
            new=AsyncMock(return_value=None),
        ):
            res = await self._call(999)
        assert res.status_code == 404


@pytest.mark.asyncio
class TestAdminSupportPatch:
    async def _call(self, inquiry_id: int, payload: dict) -> object:
        token = _make_admin_jwt()
        admin = _make_admin()
        gen = _stub_session_dependency()
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
            app.dependency_overrides[get_session] = gen
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.patch(
                        f"/api/v1/admin/support/inquiries/{inquiry_id}",
                        cookies={"denvia_admin_session": token},
                        json=payload,
                    )
            finally:
                app.dependency_overrides.clear()
        return res

    async def test_patch_status_only(self):
        with patch(
            "api.src.routers.admin.support.admin_support_service.update_inquiry",
            new=AsyncMock(return_value=_make_detail(status="in_progress")),
        ) as service_mock:
            res = await self._call(1, {"status": "in_progress"})
        assert res.status_code == 200
        assert service_mock.await_count == 1
        assert res.json()["status"] == "in_progress"

    async def test_patch_with_reply_message(self):
        with patch(
            "api.src.routers.admin.support.admin_support_service.update_inquiry",
            new=AsyncMock(return_value=_make_detail(status="resolved")),
        ) as service_mock:
            res = await self._call(1, {"reply_message": "안녕하세요, 환불은 마이페이지에서 신청 가능합니다."})
        assert res.status_code == 200
        assert service_mock.await_count == 1
        assert res.json()["status"] == "resolved"

    async def test_patch_no_op_returns_422(self):
        res = await self._call(1, {})
        assert res.status_code == 422

    async def test_patch_returns_404_when_missing(self):
        with patch(
            "api.src.routers.admin.support.admin_support_service.update_inquiry",
            new=AsyncMock(return_value=None),
        ):
            res = await self._call(999, {"status": "resolved"})
        assert res.status_code == 404
