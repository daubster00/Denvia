"""Admin RBAC 통합 테스트 — require_admin + audit-logs 엔드포인트 검증."""

import time
import pytest
import jwt as pyjwt
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch

from api.src.main import app
from api.src.settings import settings
from api.src.models.base import get_session


def _make_jwt(user_id: int = 1, role: str = "user", sub_status: str = "free") -> str:
    """일반 사이트 세션 JWT (denvia_session)."""
    if role == "admin":
        payload = {
            "sub": str(user_id),
            "aud": "denvia-admin",
            "exp": int(time.time()) + 3600,
        }
    else:
        payload = {
            "sub": str(user_id),
            "role": role,
            "sub_status": sub_status,
            "exp": int(time.time()) + 3600,
        }
    return pyjwt.encode(payload, settings.denvia_jwt_secret, algorithm=settings.denvia_jwt_algorithm)


def _make_admin_jwt(user_id: int = 99) -> str:
    """관리자 콘솔용 JWT (denvia_admin_session, aud=denvia-admin)."""
    payload = {
        "sub": str(user_id),
        "aud": "denvia-admin",
        "exp": int(time.time()) + 3600,
    }
    return pyjwt.encode(payload, settings.denvia_jwt_secret, algorithm=settings.denvia_jwt_algorithm)


def _make_user(role: str = "user"):
    user = MagicMock()
    user.id = 1
    user.email = "test@denvia.com"
    user.role = role
    user.subscription_status = "free"
    user.segment = None
    user.years_of_experience = None
    user.withdrawn_at = None
    user.must_reset_password = False
    return user


async def _mock_empty_db():
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = 0
    mock_result.scalars.return_value.all.return_value = []
    session = MagicMock()
    session.execute = AsyncMock(return_value=mock_result)
    yield session


class TestAdminAuditLogsEndpoint:
    async def test_비인증_401(self):
        """쿠키 없음 → 401."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/admin/audit-logs")
        assert res.status_code == 401

    async def test_일반_세션쿠키만_있으면_401(self):
        """일반 denvia_session 쿠키만으로는 admin 엔드포인트 통과 불가 → 401 ADMIN_AUTH_REQUIRED."""
        token = _make_jwt(role="user")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get(
                "/api/v1/admin/audit-logs",
                cookies={"denvia_session": token},
            )
        assert res.status_code == 401
        assert res.json()["code"] == "ADMIN_AUTH_REQUIRED"

    async def test_관리자_200_pagination_구조(self):
        """admin 쿠키 + DB role==admin → 200 + {items, page, per_page, total} 구조."""
        token = _make_admin_jwt(user_id=99)
        user = _make_user(role="admin")

        app.dependency_overrides[get_session] = _mock_empty_db
        try:
            with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.get(
                        "/api/v1/admin/audit-logs",
                        cookies={"denvia_admin_session": token},
                    )
        finally:
            app.dependency_overrides.pop(get_session, None)

        assert res.status_code == 200
        body = res.json()
        assert set(body.keys()) >= {"items", "page", "per_page", "total"}
        assert body["items"] == []
        assert body["total"] == 0

    async def test_action_filter_파라미터_수용(self):
        """action_filter 쿼리 파라미터 정상 처리."""
        token = _make_admin_jwt(user_id=99)
        user = _make_user(role="admin")

        app.dependency_overrides[get_session] = _mock_empty_db
        try:
            with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.get(
                        "/api/v1/admin/audit-logs?action_filter=rag",
                        cookies={"denvia_admin_session": token},
                    )
        finally:
            app.dependency_overrides.pop(get_session, None)

        assert res.status_code == 200
