"""GET /api/v1/billing/plans 단위 테스트 — Story 3.1."""

import pytest
from unittest.mock import MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.src.models.user import User
from api.src.routers.billing import list_billing_plans, router as _billing_router
from api.src.models.base import get_session


def _make_user(subscription_status: str = "free") -> MagicMock:
    u = MagicMock(spec=User)
    u.id = 1
    u.subscription_status = subscription_status
    u.role = "user"
    u.current_session_id = None
    u.admin_grade = "master"
    return u


@pytest.mark.asyncio
async def test_list_billing_plans_returns_two_plans():
    """GET /billing/plans는 Basic + Pro 2개 플랜을 반환해야 한다."""
    user = _make_user()
    response = await list_billing_plans(_=user)

    assert len(response.plans) == 2


@pytest.mark.asyncio
async def test_list_billing_plans_free_tier():
    """Basic 플랜의 tier, price_krw, is_recommended를 확인한다."""
    user = _make_user()
    response = await list_billing_plans(_=user)

    free_plan = next(p for p in response.plans if p.tier == "free")
    assert free_plan.price_krw == 0
    assert free_plan.is_recommended is False


@pytest.mark.asyncio
async def test_list_billing_plans_pro_tier():
    """Pro 플랜의 tier, is_recommended를 확인한다."""
    user = _make_user()
    response = await list_billing_plans(_=user)

    pro_plan = next(p for p in response.plans if p.tier == "pro")
    assert pro_plan.is_recommended is True
    assert pro_plan.price_krw > 0


@pytest.mark.asyncio
async def test_list_billing_plans_pro_has_period():
    """Pro 플랜은 period(월 표기)를 포함해야 한다."""
    user = _make_user()
    response = await list_billing_plans(_=user)

    pro_plan = next(p for p in response.plans if p.tier == "pro")
    assert pro_plan.period is not None
    assert "월" in pro_plan.period


@pytest.mark.asyncio
async def test_list_billing_plans_each_has_features():
    """모든 플랜은 1개 이상의 features를 포함해야 한다."""
    user = _make_user()
    response = await list_billing_plans(_=user)

    for plan in response.plans:
        assert len(plan.features) >= 1


# ── HTTP 레이어 인증 테스트 ──────────────────────────────────────────────────


@pytest.fixture(scope="module")
def _billing_client():
    """billing 라우터만 포함한 최소 앱 + TestClient. DB 세션만 모킹."""
    mini = FastAPI()
    mini.include_router(_billing_router, prefix="/api/v1")

    async def _mock_db():
        yield MagicMock()

    mini.dependency_overrides[get_session] = _mock_db
    with TestClient(mini, raise_server_exceptions=False) as client:
        yield client


def test_plans_unauthenticated_returns_401(_billing_client):
    """쿠키 없이 GET /api/v1/billing/plans 호출 시 401을 반환해야 한다."""
    response = _billing_client.get("/api/v1/billing/plans")
    assert response.status_code == 401


def test_plans_authenticated_returns_200(_billing_client):
    """인증된 사용자의 GET /api/v1/billing/plans는 200과 plans 목록을 반환해야 한다."""
    from api.src.deps.auth import get_current_user

    mock_user = _make_user()

    async def _mock_auth():
        return mock_user

    _billing_client.app.dependency_overrides[get_current_user] = _mock_auth
    try:
        response = _billing_client.get("/api/v1/billing/plans")
    finally:
        _billing_client.app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    data = response.json()
    assert "plans" in data
    assert len(data["plans"]) == 2
