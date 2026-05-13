"""Story 9.3 — admin/support v2 통합 테스트.

신규/확장 기능:
- POST /admin/support/inquiries/{id}/reply  (Tiptap reply_html)
- GET  /admin/support/counts                (탭 카운트)
- GET  /admin/support/inquiries (q/status_in/from/to)
- PATCH /admin/support/inquiries/{id} (force=False 시 409)
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
from api.src.schemas.admin.support import (
    InquiryDetailResponse,
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


def _stub_session():
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()

    async def gen():
        yield session

    return gen, session


def _make_detail(
    inquiry_id: int = 7,
    status: str = "resolved",
    subscription_status: str = "pro",
) -> InquiryDetailResponse:
    return InquiryDetailResponse(
        id=inquiry_id,
        user_id=10,
        user_email="user@example.com",
        user_phone="01012345678",
        subject="결제 환불",
        body="문의 본문",
        status=status,
        created_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        resolved_at=datetime(2026, 5, 2, tzinfo=timezone.utc),
        user_segment="doctor",
        user_subscription_status=subscription_status,
        user_created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        recent_qa=[],
        replies=[],
    )


@pytest.mark.asyncio
class TestSupportCounts:
    async def test_counts_endpoint_returns_open_and_pending(self):
        token = _make_admin_jwt()
        admin = _make_admin()
        gen, _ = _stub_session()
        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
            patch(
                "api.src.routers.admin.support.admin_support_service.count_open_inquiries",
                new=AsyncMock(return_value=12),
            ),
            patch(
                "api.src.routers.admin.support.admin_refund_service.count_pending",
                new=AsyncMock(return_value=3),
            ),
        ):
            app.dependency_overrides[get_session] = gen
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.get(
                        "/api/v1/admin/support/counts",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()
        assert res.status_code == 200
        body = res.json()
        assert body["open_inquiries"] == 12
        assert body["pending_refunds"] == 3
        assert res.headers.get("Cache-Control") == "no-store"


@pytest.mark.asyncio
class TestSupportListExtended:
    async def _call(self, qs: str = ""):
        token = _make_admin_jwt()
        admin = _make_admin()
        gen, _ = _stub_session()
        response = InquiryListResponse(items=[], page=1, per_page=50, total=0)
        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
            patch(
                "api.src.routers.admin.support.admin_support_service.list_inquiries",
                new=AsyncMock(return_value=response),
            ) as svc,
        ):
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
        return res, svc

    async def test_status_in_csv_passes_through(self):
        res, svc = await self._call("?status_in=open,in_progress")
        assert res.status_code == 200
        kwargs = svc.call_args.kwargs
        assert kwargs["status_in"] == {"open", "in_progress"}

    async def test_invalid_status_in_returns_422(self):
        res, _ = await self._call("?status_in=open,bogus")
        assert res.status_code == 422

    async def test_q_param_passes_through(self):
        res, svc = await self._call("?q=환불")
        assert res.status_code == 200
        assert svc.call_args.kwargs["q"] == "환불"

    async def test_per_page_invalid_returns_422(self):
        res, _ = await self._call("?per_page=37")
        assert res.status_code == 422

    async def test_per_page_50_accepted(self):
        res, _ = await self._call("?per_page=50")
        assert res.status_code == 200

    async def test_response_has_no_store(self):
        res, _ = await self._call()
        assert res.status_code == 200
        assert res.headers.get("Cache-Control") == "no-store"


@pytest.mark.asyncio
class TestPatchForceFlow:
    async def _patch(self, payload: dict):
        token = _make_admin_jwt()
        admin = _make_admin()
        gen, _ = _stub_session()
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
            app.dependency_overrides[get_session] = gen
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.patch(
                        "/api/v1/admin/support/inquiries/7",
                        json=payload,
                        cookies={
                            "denvia_admin_session": token,
                            "denvia_admin_csrf": "csrf-test",
                        },
                        headers={"X-CSRF-Token": "csrf-test"},
                    )
            finally:
                app.dependency_overrides.clear()
        return res

    async def test_revert_without_force_returns_409(self):
        async def raise_revert(*_a, **_kw):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "INQUIRY_STATUS_REVERT_REQUIRES_CONFIRMATION",
                    "message": "완료된 문의를 재개하려면 확인이 필요합니다.",
                    "current_status": "resolved",
                    "requested_status": "open",
                },
            )

        with patch(
            "api.src.routers.admin.support.admin_support_service.update_inquiry",
            new=AsyncMock(side_effect=raise_revert),
        ):
            res = await self._patch({"status": "open"})
        assert res.status_code == 409
        body = res.json()
        assert body["code"] == "INQUIRY_STATUS_REVERT_REQUIRES_CONFIRMATION"

    async def test_force_true_succeeds(self):
        with patch(
            "api.src.routers.admin.support.admin_support_service.update_inquiry",
            new=AsyncMock(return_value=_make_detail(status="open")),
        ) as svc:
            res = await self._patch({"status": "open", "force": True})
        assert res.status_code == 200
        # service가 force=True를 받았는지 검증
        call_args = svc.call_args
        payload_arg = call_args.args[3]  # request, db, inquiry_id, payload
        assert payload_arg.force is True


@pytest.mark.asyncio
class TestPostReply:
    async def _post(self, inquiry_id: int, payload: dict):
        token = _make_admin_jwt()
        admin = _make_admin()
        gen, _ = _stub_session()
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
            app.dependency_overrides[get_session] = gen
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.post(
                        f"/api/v1/admin/support/inquiries/{inquiry_id}/reply",
                        json=payload,
                        cookies={
                            "denvia_admin_session": token,
                            "denvia_admin_csrf": "csrf-test",
                        },
                        headers={"X-CSRF-Token": "csrf-test"},
                    )
            finally:
                app.dependency_overrides.clear()
        return res

    async def test_reply_returns_201(self):
        with patch(
            "api.src.routers.admin.support.admin_support_service.create_reply",
            new=AsyncMock(return_value=_make_detail()),
        ):
            res = await self._post(7, {"reply_html": "<p>해결되었습니다.</p>"})
        assert res.status_code == 201
        body = res.json()
        assert body["inquiry"]["id"] == 7

    async def test_reply_404_when_missing(self):
        with patch(
            "api.src.routers.admin.support.admin_support_service.create_reply",
            new=AsyncMock(return_value=None),
        ):
            res = await self._post(999, {"reply_html": "<p>응답</p>"})
        assert res.status_code == 404

    async def test_reply_empty_html_returns_422(self):
        # FastAPI/Pydantic validation: min_length=1
        res = await self._post(7, {"reply_html": ""})
        assert res.status_code == 422

    async def test_reply_oversize_html_returns_422(self):
        big = "<p>" + ("x" * 25000) + "</p>"
        res = await self._post(7, {"reply_html": big})
        assert res.status_code == 422


@pytest.mark.asyncio
class TestInquiryDetailSubscriptionStatus:
    """GET /admin/support/inquiries/{id} — Pro 사용자 구독 상태가 'pro' 로 그대로 내려가야 함.

    이전엔 schema 가 'active' 만 허용해 'pro' 가 'free' 로 깎여 내려갔다 → 9.3 코드리뷰 지적.
    """

    async def _get(self, inquiry_id: int):
        token = _make_admin_jwt()
        admin = _make_admin()
        gen, _ = _stub_session()
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
            app.dependency_overrides[get_session] = gen
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    return await client.get(
                        f"/api/v1/admin/support/inquiries/{inquiry_id}",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()

    async def test_pro_user_subscription_status_passthrough(self):
        with patch(
            "api.src.routers.admin.support.admin_support_service.get_inquiry",
            new=AsyncMock(return_value=_make_detail(subscription_status="pro")),
        ):
            res = await self._get(7)
        assert res.status_code == 200
        body = res.json()
        assert body["user_subscription_status"] == "pro"

    async def test_blocked_user_subscription_status_passthrough(self):
        with patch(
            "api.src.routers.admin.support.admin_support_service.get_inquiry",
            new=AsyncMock(return_value=_make_detail(subscription_status="blocked")),
        ):
            res = await self._get(7)
        assert res.status_code == 200
        assert res.json()["user_subscription_status"] == "blocked"


@pytest.mark.asyncio
class TestReplyEditDelete:
    """PATCH /inquiries/{id}/replies/{reply_id} 및 DELETE — 답변 수정/삭제."""

    async def _patch(self, inquiry_id: int, reply_id: int, payload: dict):
        token = _make_admin_jwt()
        admin = _make_admin()
        gen, _ = _stub_session()
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
            app.dependency_overrides[get_session] = gen
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.patch(
                        f"/api/v1/admin/support/inquiries/{inquiry_id}/replies/{reply_id}",
                        json=payload,
                        cookies={
                            "denvia_admin_session": token,
                            "denvia_admin_csrf": "csrf-test",
                        },
                        headers={"X-CSRF-Token": "csrf-test"},
                    )
            finally:
                app.dependency_overrides.clear()
        return res

    async def _delete(self, inquiry_id: int, reply_id: int):
        token = _make_admin_jwt()
        admin = _make_admin()
        gen, _ = _stub_session()
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
            app.dependency_overrides[get_session] = gen
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.delete(
                        f"/api/v1/admin/support/inquiries/{inquiry_id}/replies/{reply_id}",
                        cookies={
                            "denvia_admin_session": token,
                            "denvia_admin_csrf": "csrf-test",
                        },
                        headers={"X-CSRF-Token": "csrf-test"},
                    )
            finally:
                app.dependency_overrides.clear()
        return res

    async def test_edit_reply_returns_200(self):
        with patch(
            "api.src.routers.admin.support.admin_support_service.update_reply",
            new=AsyncMock(return_value=_make_detail()),
        ) as svc:
            res = await self._patch(7, 42, {"reply_html": "<p>수정된 답변</p>"})
        assert res.status_code == 200
        body = res.json()
        assert body["id"] == 7
        # 서비스에 inquiry_id, reply_id 전달 확인
        call_args = svc.call_args
        assert call_args.args[2] == 7  # inquiry_id
        assert call_args.args[3] == 42  # reply_id

    async def test_edit_reply_404_when_missing(self):
        with patch(
            "api.src.routers.admin.support.admin_support_service.update_reply",
            new=AsyncMock(return_value=None),
        ):
            res = await self._patch(7, 999, {"reply_html": "<p>없음</p>"})
        assert res.status_code == 404
        body = res.json()
        assert body["code"] == "INQUIRY_REPLY_NOT_FOUND"

    async def test_edit_reply_empty_html_returns_422(self):
        res = await self._patch(7, 42, {"reply_html": ""})
        assert res.status_code == 422

    async def test_edit_reply_oversize_returns_422(self):
        big = "<p>" + ("x" * 25000) + "</p>"
        res = await self._patch(7, 42, {"reply_html": big})
        assert res.status_code == 422

    async def test_delete_reply_returns_200(self):
        with patch(
            "api.src.routers.admin.support.admin_support_service.delete_reply",
            new=AsyncMock(return_value=_make_detail()),
        ) as svc:
            res = await self._delete(7, 42)
        assert res.status_code == 200
        body = res.json()
        assert body["id"] == 7
        call_args = svc.call_args
        assert call_args.args[2] == 7
        assert call_args.args[3] == 42

    async def test_delete_reply_404_when_missing(self):
        with patch(
            "api.src.routers.admin.support.admin_support_service.delete_reply",
            new=AsyncMock(return_value=None),
        ):
            res = await self._delete(7, 999)
        assert res.status_code == 404
        body = res.json()
        assert body["code"] == "INQUIRY_REPLY_NOT_FOUND"
