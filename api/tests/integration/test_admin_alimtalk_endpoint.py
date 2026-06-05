"""Story 4.6 — `/api/v1/admin/alimtalk/*` 통합 스모크 테스트.

목적:
- 라우터가 main.app 에 정상 등재되는지 검증 (route 등록 누락 회귀 방지).
- 인증 미통과 시 401 (실제 백엔드 dev DB 헬스체크가 SSOT — 본 파일은 빠른 회귀 가드).

전체 권한 분기 + 발송 흐름 검증은 라이브 헬스체크(curl)로 갈음한다.
(memory feedback_pytest_full_run_nukes_dev_db — 풀 마이그·DB 광범위 테스트 회피)
"""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from api.src.main import app


class TestAlimtalkRouterRegistration:
    """라우터 등재 회귀 가드."""

    def test_summary_route_registered(self):
        paths = {r.path for r in app.routes if hasattr(r, "path")}
        assert "/api/v1/admin/alimtalk/summary" in paths

    def test_logs_route_registered(self):
        paths = {r.path for r in app.routes if hasattr(r, "path")}
        assert "/api/v1/admin/alimtalk/logs" in paths

    def test_test_recipient_route_registered(self):
        paths = {r.path for r in app.routes if hasattr(r, "path")}
        assert "/api/v1/admin/alimtalk/test-recipient" in paths

    def test_test_send_route_registered(self):
        paths = {r.path for r in app.routes if hasattr(r, "path")}
        assert "/api/v1/admin/alimtalk/test-send" in paths


class TestAlimtalkUnauthenticated:
    """미인증 시 401 — 권한 가드 회귀 확인."""

    async def test_summary_no_cookie_401(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.get("/api/v1/admin/alimtalk/summary")
        assert res.status_code == 401

    async def test_test_recipient_no_cookie_401(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.get("/api/v1/admin/alimtalk/test-recipient")
        assert res.status_code == 401

    async def test_test_send_no_cookie_401(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.post(
                "/api/v1/admin/alimtalk/test-send",
                json={"template_code": "billing.first_charge_success"},
            )
        assert res.status_code == 401

    async def test_put_test_recipient_no_cookie_401(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.put(
                "/api/v1/admin/alimtalk/test-recipient",
                json={"phone": "01012341234"},
            )
        assert res.status_code == 401

    async def test_logs_no_cookie_401(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.get(
                "/api/v1/admin/alimtalk/logs?template_code=billing.first_charge_success"
            )
        assert res.status_code == 401
