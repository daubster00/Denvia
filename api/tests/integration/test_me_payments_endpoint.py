"""GET /api/v1/me/payments 통합 테스트 — Story 4.4 (AC-3, AC-9).

ASGI 스택으로 라우터를 호출해 인증 가드 + per_page 422 + 9필드 응답 정합 검증.
DB는 _stub_session()으로 SELECT 결과만 모킹.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from api.src.deps.auth import get_current_user
from api.src.main import app
from api.src.models.base import get_session
from api.src.models.user import User


def _make_user(
    user_id: int = 1,
    email: str = "user@example.com",
) -> MagicMock:
    u = MagicMock(spec=User)
    u.id = user_id
    u.email = email
    return u


def _row(
    payment_id: int,
    *,
    charged_at: datetime | None,
    amount_krw: int = 9900,
    provider_order_id: str = "sub-1-2026-04-30",
    status: str = "success",
    sub_started_at: datetime | None = None,
    sub_period_end: datetime | None = None,
    bk_card_last4: str | None = "1234",
    bk_card_company: str | None = "현대",
):
    r = MagicMock()
    r.id = payment_id
    r.charged_at = charged_at
    r.amount_krw = amount_krw
    r.provider_order_id = provider_order_id
    r.status = status
    r.sub_started_at = sub_started_at
    r.sub_period_end = sub_period_end
    r.bk_card_last4 = bk_card_last4
    r.bk_card_company = bk_card_company
    return r


def _stub_session(*, total: int = 0, rows: list | None = None):
    rows = rows or []

    count_result = MagicMock()
    count_result.scalar_one = MagicMock(return_value=total)

    select_result = MagicMock()
    select_result.all = MagicMock(return_value=rows)

    session = MagicMock()
    session.execute = AsyncMock(side_effect=[count_result, select_result])
    session.commit = AsyncMock()

    async def gen():
        yield session

    return gen


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
class TestMyPaymentsEndpoint:
    async def test_unauth_returns_401(self):
        """쿠키 없음 → 401 (Depends(get_current_user) 자동 처리)."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.get("/api/v1/me/payments")
        assert res.status_code == 401
        assert res.json()["code"] == "AUTH_NOT_AUTHENTICATED"

    async def test_invalid_per_page_returns_422(self):
        """per_page=15 → 422 INVALID_PARAM."""
        user = _make_user()
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = _stub_session()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.get("/api/v1/me/payments?page=1&per_page=15")

        assert res.status_code == 422
        body = res.json()
        # api/src/main.py _http_exception_handler가 detail dict를 평탄화한다.
        assert body["code"] == "INVALID_PARAM"

    async def test_invalid_page_zero_returns_422(self):
        """page=0 → FastAPI Query(ge=1) 자동 422."""
        user = _make_user()
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = _stub_session()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.get("/api/v1/me/payments?page=0&per_page=20")

        assert res.status_code == 422

    async def test_empty_history_returns_zero_total(self):
        """결제 내역 0건 응답 — items=[], total=0."""
        user = _make_user()
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = _stub_session(total=0, rows=[])

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.get("/api/v1/me/payments")

        assert res.status_code == 200
        body = res.json()
        assert body["items"] == []
        assert body["page"] == 1
        assert body["per_page"] == 20
        assert body["total"] == 0

    async def test_one_row_full_payload_9_fields(self):
        """1건 응답 — items[0] 9필드 정합 (AR27 flat)."""
        user = _make_user(user_id=42, email="user42@example.com")
        charged = datetime(2026, 4, 30, 5, 23, 11, tzinfo=timezone.utc)
        sub_start = datetime(2026, 4, 30, 0, 0, 0, tzinfo=timezone.utc)
        sub_end = datetime(2026, 5, 29, 23, 59, 59, tzinfo=timezone.utc)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_session] = _stub_session(
            total=1,
            rows=[
                _row(
                    123,
                    charged_at=charged,
                    sub_started_at=sub_start,
                    sub_period_end=sub_end,
                    provider_order_id="sub-42-2026-04-30",
                )
            ],
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.get("/api/v1/me/payments?page=1&per_page=20")

        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 1
        assert body["page"] == 1
        assert body["per_page"] == 20
        assert len(body["items"]) == 1

        item = body["items"][0]
        # AR27 flat 응답 키 set 정합
        assert set(item.keys()) == {
            "payment_id",
            "charged_at",
            "subscription_period_start",
            "subscription_period_end",
            "buyer_email",
            "card_last4",
            "card_company",
            "amount_krw",
            "provider_order_id",
            "status",
        }
        assert item["payment_id"] == 123
        assert item["buyer_email"] == "user42@example.com"
        assert item["amount_krw"] == 9900
        assert item["status"] == "success"
        assert item["card_last4"] == "1234"
        assert item["card_company"] == "현대"
