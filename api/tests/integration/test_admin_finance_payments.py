"""Story 9.1 — /api/v1/admin/payments/* 통합 테스트.

ASGI 스택으로 라우터를 호출해 인증 가드 / 422 / 200 응답 정합 + 헤더를 검증한다.
finance_service는 mock으로 대체해 DB 의존을 끊는다.
"""

from __future__ import annotations

import io
import time
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import openpyxl
import pytest
from httpx import ASGITransport, AsyncClient

from api.src.main import app
from api.src.models.base import get_session
from api.src.schemas.admin.finance import (
    ErrorCodeSummary,
    PaymentEventDetailResponse,
    PaymentEventItem,
)
from api.src.settings import settings


def _admin_jwt() -> str:
    return pyjwt.encode(
        {"sub": "99", "aud": "denvia-admin", "exp": int(time.time()) + 3600},
        settings.denvia_jwt_secret,
        algorithm=settings.denvia_jwt_algorithm,
    )


def _admin_user() -> MagicMock:
    u = MagicMock()
    u.id = 99
    u.email = "admin@denvia.local"
    u.role = "admin"
    u.subscription_status = "free"
    u.segment = None
    u.withdrawn_at = None
    u.must_reset_password = False
    return u


def _stub_session():
    s = MagicMock()
    s.execute = AsyncMock()
    s.commit = AsyncMock()

    async def gen():
        yield s

    return gen


def _make_item(event_id: int = 1, **kwargs) -> PaymentEventItem:
    base = dict(
        event_id=event_id,
        payment_id=10 + event_id,
        event_type="charge_failed",
        charged_at="2026-05-07T05:23:11+00:00",
        amount_krw=9900,
        user_id=42,
        user_email_masked="u**@example.com",
        card_last4="1234",
        card_company="현대",
        provider_order_id=f"sub-{10 + event_id}-2026-05-07",
        provider_error_code="INVALID_CARD_NUMBER",
        provider_error_message="유효하지 않은 카드번호입니다.",
        status="failed",
    )
    base.update(kwargs)
    return PaymentEventItem(**base)


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
class TestListUnauth:
    async def test_no_cookie_returns_401(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.get("/api/v1/admin/payments/events")
        assert res.status_code == 401


@pytest.mark.asyncio
class TestListAuth:
    async def _call(self, qs: str = ""):
        token = _admin_jwt()
        admin = _admin_user()
        app.dependency_overrides[get_session] = _stub_session()
        with patch(
            "api.src.deps.auth.get_user_by_id",
            new=AsyncMock(return_value=admin),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.get(
                    f"/api/v1/admin/payments/events{qs}",
                    cookies={"denvia_admin_session": token},
                )

    async def test_happy_200_with_no_filters(self):
        with patch(
            "api.src.routers.admin.finance.finance_service.list_payment_events",
            new=AsyncMock(return_value=([_make_item()], 1, None)),
        ):
            res = await self._call()
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 1
        assert body["page"] == 1
        assert body["per_page"] == 50
        assert body["error_code_summary"] is None
        assert body["items"][0]["provider_error_code"] == "INVALID_CARD_NUMBER"
        # Cache-Control no-store
        assert res.headers.get("Cache-Control") == "no-store"

    async def test_invalid_per_page_returns_422(self):
        res = await self._call("?per_page=15")
        assert res.status_code == 422
        assert res.json()["code"] == "INVALID_PARAM"

    async def test_invalid_status_in_returns_422(self):
        res = await self._call("?status_in=success,nonsense")
        assert res.status_code == 422
        assert res.json()["code"] == "INVALID_PARAM"

    async def test_invalid_window_returns_422(self):
        # from > to
        res = await self._call("?from=2026-05-07&to=2026-05-01")
        assert res.status_code == 422
        assert res.json()["code"] == "INVALID_PARAM"

    async def test_status_in_passed_to_service(self):
        captured: dict = {}

        async def fake(db, **kw):
            captured.update(kw)
            return ([_make_item()], 1, None)

        with patch(
            "api.src.routers.admin.finance.finance_service.list_payment_events",
            new=fake,
        ):
            res = await self._call("?status_in=success,failed")
        assert res.status_code == 200
        assert captured["status_in"] == {"success", "failed"}

    async def test_provider_error_code_returns_summary(self):
        with patch(
            "api.src.routers.admin.finance.finance_service.list_payment_events",
            new=AsyncMock(
                return_value=(
                    [_make_item()],
                    1,
                    ErrorCodeSummary(event_count=12, affected_user_count=4),
                )
            ),
        ):
            res = await self._call("?provider_error_code=INVALID_CARD_NUMBER")
        assert res.status_code == 200
        body = res.json()
        assert body["error_code_summary"] == {
            "event_count": 12,
            "affected_user_count": 4,
        }


@pytest.mark.asyncio
class TestSingleEvent:
    async def _call(self, event_id: int):
        token = _admin_jwt()
        admin = _admin_user()
        app.dependency_overrides[get_session] = _stub_session()
        with patch(
            "api.src.deps.auth.get_user_by_id",
            new=AsyncMock(return_value=admin),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.get(
                    f"/api/v1/admin/payments/events/{event_id}",
                    cookies={"denvia_admin_session": token},
                )

    async def test_single_event_200(self):
        item = _make_item(event_id=42)
        detail = PaymentEventDetailResponse(
            **item.model_dump(),
            raw_response_json={"code": "INVALID_CARD_NUMBER", "message": "x"},
        )
        with patch(
            "api.src.routers.admin.finance.finance_service.get_payment_event",
            new=AsyncMock(return_value=detail),
        ):
            res = await self._call(42)
        assert res.status_code == 200
        body = res.json()
        assert body["event_id"] == 42
        assert body["raw_response_json"] == {
            "code": "INVALID_CARD_NUMBER",
            "message": "x",
        }
        assert res.headers.get("Cache-Control") == "no-store"

    async def test_single_event_404(self):
        with patch(
            "api.src.routers.admin.finance.finance_service.get_payment_event",
            new=AsyncMock(return_value=None),
        ):
            res = await self._call(99999)
        assert res.status_code == 404
        assert res.json()["code"] == "EVENT_NOT_FOUND"

    async def test_single_event_returns_refund_reason_for_auto_refund(self):
        # 자동 환불 — refund_reason은 payment_events 폴백에서 채워진다.
        item = _make_item(event_id=79, event_type="refund_requested", status="refunded")
        detail = PaymentEventDetailResponse(
            **item.model_dump(),
            raw_response_json={"reason": "구독 갱신을 실수로 진행했습니다"},
            refund_reason="구독 갱신을 실수로 진행했습니다",
        )
        with patch(
            "api.src.routers.admin.finance.finance_service.get_payment_event",
            new=AsyncMock(return_value=detail),
        ):
            res = await self._call(79)
        assert res.status_code == 200
        body = res.json()
        assert body["refund_reason"] == "구독 갱신을 실수로 진행했습니다"


@pytest.mark.asyncio
class TestExport:
    async def _call(self, qs: str = ""):
        token = _admin_jwt()
        admin = _admin_user()
        app.dependency_overrides[get_session] = _stub_session()
        with patch(
            "api.src.deps.auth.get_user_by_id",
            new=AsyncMock(return_value=admin),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.get(
                    f"/api/v1/admin/payments/events/export{qs}",
                    cookies={"denvia_admin_session": token},
                )

    async def test_export_two_sheets_xlsx(self):
        rows = [
            [1, 11, "charge_failed", "2026-05-07 14:23:11", 9900, 42, "u**@x.com",
             "1234", "현대", "sub-11-2026-05-07", "INVALID_CARD_NUMBER", "msg", "failed"],
        ]
        summary = {
            "기간": "2026-05-01 ~ 2026-05-07",
            "총 이벤트 수": 1,
            "결제 완료": 0,
            "결제 실패": 1,
            "환불 완료": 0,
            "환불 요청": 0,
            "행 제한": 10000,
            "잘림 여부": "아니오",
        }
        with patch(
            "api.src.routers.admin.finance.finance_service.export_payment_events",
            new=AsyncMock(return_value=(rows, False, summary)),
        ):
            res = await self._call("?from=2026-05-01&to=2026-05-07")
        assert res.status_code == 200
        assert (
            res.headers["content-type"]
            == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        disp = res.headers.get("content-disposition", "")
        assert 'filename="payment_events_2026-05-01_2026-05-07.xlsx"' in disp
        assert res.headers.get("Cache-Control") == "no-store"
        assert "X-Truncated" not in res.headers

        wb = openpyxl.load_workbook(io.BytesIO(res.content))
        assert wb.sheetnames == ["Summary", "Detail"]
        det = wb["Detail"]
        det_headers = [c.value for c in det[1]]
        assert det_headers[0] == "event_id"
        assert det[2][0].value == 1

    async def test_export_x_truncated_header(self):
        with patch(
            "api.src.routers.admin.finance.finance_service.export_payment_events",
            new=AsyncMock(return_value=([], True, {"총 이벤트 수": 0})),
        ):
            res = await self._call()
        assert res.status_code == 200
        assert res.headers.get("X-Truncated") == "true"
