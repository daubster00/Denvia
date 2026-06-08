"""Story 10.5 — `/admin/grade-permissions` 통합 테스트.

검증 항목:
- GET: master/operator 모두 200, sub_operator 403
- PATCH: master/operator 모두 200 (2026-05-28 SSOT — operator 도 매트릭스 수정 가능), sub_operator 403
- PATCH 알 수 없는 page_route → 422 ADMIN_PAGE_ROUTE_UNKNOWN
- PATCH master 등급 부여 시도 → 422 ADMIN_GRADE_NOT_CONFIGURABLE
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest
from httpx import ASGITransport, AsyncClient

from api.src.main import app
from api.src.models.base import get_session
from api.src.settings import settings


def _make_admin_jwt(user_id: int = 1) -> str:
    payload = {
        "sub": str(user_id),
        "aud": "denvia-admin",
        "exp": int(time.time()) + 3600,
    }
    return pyjwt.encode(
        payload, settings.denvia_jwt_secret, algorithm=settings.denvia_jwt_algorithm
    )


def _make_admin(user_id: int = 1, grade: str = "master") -> MagicMock:
    u = MagicMock()
    u.id = user_id
    u.email = f"admin{user_id}@denvia.local"
    u.role = "admin"
    u.subscription_status = "free"
    u.withdrawn_at = None
    u.admin_grade = grade
    u.must_reset_password = False
    u.current_session_id = None
    return u


class _DummySession:
    """get_session override — execute/flush/commit 무력화.

    admin_grades 테이블 조회는 (operator, sub_operator) 2건을 흉내내고,
    admin_grade_page_permissions 테이블 조회는 빈 결과로 fallback해서
    엔드포인트가 ADMIN_PAGE_ROUTES × configurable 등급 매트릭스를 합성하도록 둔다.
    """

    def __init__(self):
        self.commit = AsyncMock()
        self.flush = AsyncMock()

    @staticmethod
    def _fake_grade_row(code: str, label: str):
        row = MagicMock()
        row.code = code
        row.label = label
        row.is_builtin = True
        row.created_at = None
        return row

    async def execute(self, stmt, *_a, **_kw):
        stmt_str = str(stmt).lower()
        scalars = MagicMock()
        result = MagicMock()

        if "admin_grades" in stmt_str:
            rows = [
                self._fake_grade_row("operator", "운영자"),
                self._fake_grade_row("sub_operator", "부운영자"),
            ]
            scalars.all = MagicMock(return_value=rows)
            # _validate_grade_configurable 의 select(AdminGrade.code).where(code == X)
            result.scalar_one_or_none = MagicMock(return_value="sub_operator")
        else:
            scalars.all = MagicMock(return_value=[])
            result.scalar_one_or_none = MagicMock(return_value=None)

        result.scalars = MagicMock(return_value=scalars)
        return result


async def _override_session():
    yield _DummySession()


@pytest.fixture
def client():
    app.dependency_overrides[get_session] = _override_session
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://testserver"), transport


# ── GET ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_GET_master_200_rows_returned(client):
    ac, _t = client
    token = _make_admin_jwt(1)
    admin = _make_admin(1, "master")
    with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
        async with ac as c:
            res = await c.get(
                "/api/v1/admin/grade-permissions",
                cookies={"denvia_admin_session": token},
            )
    app.dependency_overrides.clear()
    assert res.status_code == 200, res.text
    body = res.json()
    # 매트릭스 = ADMIN_PAGE_ROUTES × configurable 등급 (operator + sub_operator)
    from api.src.services.admin_grade_permission_service import ADMIN_PAGE_ROUTES

    assert len(body["rows"]) == len(ADMIN_PAGE_ROUTES) * 2
    assert body["grades"] == ["operator", "sub_operator"]


@pytest.mark.asyncio
async def test_GET_operator_200(client):
    ac, _t = client
    token = _make_admin_jwt(2)
    admin = _make_admin(2, "operator")
    with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
        async with ac as c:
            res = await c.get(
                "/api/v1/admin/grade-permissions",
                cookies={"denvia_admin_session": token},
            )
    app.dependency_overrides.clear()
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_GET_sub_operator_403_ADMIN_FORBIDDEN_GRADE(client):
    ac, _t = client
    token = _make_admin_jwt(3)
    admin = _make_admin(3, "sub_operator")
    with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
        async with ac as c:
            res = await c.get(
                "/api/v1/admin/grade-permissions",
                cookies={"denvia_admin_session": token},
            )
    app.dependency_overrides.clear()
    assert res.status_code == 403
    assert res.json()["code"] == "ADMIN_FORBIDDEN_GRADE"


# ── PATCH ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_PATCH_master_200(client):
    ac, _t = client
    token = _make_admin_jwt(1)
    admin = _make_admin(1, "master")
    with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
        async with ac as c:
            res = await c.patch(
                "/api/v1/admin/grade-permissions",
                cookies={"denvia_admin_session": token},
                json={
                    "admin_grade": "sub_operator",
                    "page_route": "/admin/users",
                    "allowed": True,
                },
            )
    app.dependency_overrides.clear()
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["admin_grade"] == "sub_operator"
    assert body["page_route"] == "/admin/users"
    assert body["allowed"] is True


@pytest.mark.asyncio
async def test_PATCH_operator_200(client):
    """operator 도 매트릭스 토글 수정 가능 (2026-05-28 SSOT)."""
    ac, _t = client
    token = _make_admin_jwt(2)
    admin = _make_admin(2, "operator")
    with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
        async with ac as c:
            res = await c.patch(
                "/api/v1/admin/grade-permissions",
                cookies={"denvia_admin_session": token},
                json={
                    "admin_grade": "sub_operator",
                    "page_route": "/admin/users",
                    "allowed": True,
                },
            )
    app.dependency_overrides.clear()
    assert res.status_code == 200
    body = res.json()
    assert body["admin_grade"] == "sub_operator"
    assert body["page_route"] == "/admin/users"
    assert body["allowed"] is True


@pytest.mark.asyncio
async def test_PATCH_unknown_route_422(client):
    ac, _t = client
    token = _make_admin_jwt(1)
    admin = _make_admin(1, "master")
    with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
        async with ac as c:
            res = await c.patch(
                "/api/v1/admin/grade-permissions",
                cookies={"denvia_admin_session": token},
                json={
                    "admin_grade": "operator",
                    "page_route": "/admin/__nope__",
                    "allowed": True,
                },
            )
    app.dependency_overrides.clear()
    assert res.status_code == 422
    assert res.json()["code"] == "ADMIN_PAGE_ROUTE_UNKNOWN"


@pytest.mark.asyncio
async def test_PATCH_master_grade_assignment_422(client):
    ac, _t = client
    token = _make_admin_jwt(1)
    admin = _make_admin(1, "master")
    with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
        async with ac as c:
            # admin_grade='master' 는 Pydantic Literal['operator','sub_operator']에서 422
            res = await c.patch(
                "/api/v1/admin/grade-permissions",
                cookies={"denvia_admin_session": token},
                json={
                    "admin_grade": "master",
                    "page_route": "/admin",
                    "allowed": True,
                },
            )
    app.dependency_overrides.clear()
    assert res.status_code == 422
