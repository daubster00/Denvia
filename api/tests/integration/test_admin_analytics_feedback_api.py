"""Admin 피드백 분석 API 통합 테스트 — Story 5.4 (AC-1, AC-2, AC-11)."""

from __future__ import annotations

import time
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest
from httpx import ASGITransport, AsyncClient

from api.src.main import app
from api.src.models.base import get_session
from api.src.settings import settings


def _make_jwt(role: str = "admin") -> str:
    if role == "admin":
        payload = {
            "sub": "1",
            "aud": "denvia-admin",
            "exp": int(time.time()) + 3600,
        }
    else:
        payload = {
            "sub": "1",
            "role": role,
            "sub_status": "free",
            "exp": int(time.time()) + 3600,
        }
    return pyjwt.encode(
        payload,
        settings.denvia_jwt_secret,
        algorithm=settings.denvia_jwt_algorithm,
    )


def _make_admin_jwt(user_id: int = 99) -> str:
    """관리자 콘솔용 JWT (denvia_admin_session, aud=denvia-admin)."""
    payload = {
        "sub": str(user_id),
        "aud": "denvia-admin",
        "exp": int(time.time()) + 3600,
    }
    return pyjwt.encode(payload, settings.denvia_jwt_secret, algorithm=settings.denvia_jwt_algorithm)


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

    async def gen():
        yield session

    return gen


_DEFAULT_SUMMARY = {"good_count": 120, "bad_count": 34, "good_ratio": 0.779}
_DEFAULT_SERIES = [
    {"bucket_start": "2026-03-01", "good": 40, "bad": 12},
    {"bucket_start": "2026-04-01", "good": 55, "bad": 8},
]
_DEFAULT_ITEMS = [
    {
        "qa_log_id": 1001,
        "question_text": "임플란트 보철물 선택 기준은?",
        "answer_text": "임플란트 보철물은 …",
        "rating": "good",
        "segment": "doctor",
        "user_id": 42,
        "email": "doctor@denvia.test",
        "created_at": "2026-04-15T10:23:00+09:00",
    }
]


def _patch_service(
    summary=None,
    series=None,
    items=None,
    total=1,
):
    summary = summary or _DEFAULT_SUMMARY
    series = series or _DEFAULT_SERIES
    items = items or _DEFAULT_ITEMS
    return [
        patch(
            "api.src.routers.admin.analytics.get_feedback_summary",
            new=AsyncMock(return_value=summary),
        ),
        patch(
            "api.src.routers.admin.analytics.get_feedback_series",
            new=AsyncMock(return_value=series),
        ),
        patch(
            "api.src.routers.admin.analytics.get_feedback_items_total",
            new=AsyncMock(return_value=total),
        ),
        patch(
            "api.src.routers.admin.analytics.get_feedback_items",
            new=AsyncMock(return_value=items),
        ),
    ]


@pytest.mark.asyncio
class TestFeedbackEndpointAuth:
    async def test_feedback_requires_admin_unauth_401(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/v1/admin/analytics/feedback")
        assert res.status_code == 401

    async def test_feedback_requires_admin(self):
        """일반 user는 401."""
        token = _make_jwt(role="user")
        regular = _make_admin()
        regular.role = "user"
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=regular)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get(
                    "/api/v1/admin/analytics/feedback",
                    cookies={"denvia_admin_session": token},
                )
        assert res.status_code == 401


@pytest.mark.asyncio
class TestFeedbackEndpoint:
    async def _call(self, qs: str = ""):
        token = _make_admin_jwt()
        admin = _make_admin()
        gen = _stub_session()
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
            app.dependency_overrides[get_session] = gen
            with _patch_service()[0], _patch_service()[1], _patch_service()[2], _patch_service()[3]:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.get(
                        f"/api/v1/admin/analytics/feedback{qs}",
                        cookies={"denvia_admin_session": token},
                    )
            app.dependency_overrides.clear()
        return res

    async def _call_with_patches(self, patches, qs: str = ""):
        token = _make_admin_jwt()
        admin = _make_admin()
        gen = _stub_session()
        ctx = patches
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
            app.dependency_overrides[get_session] = gen
            for p in ctx:
                p.start()
            try:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.get(
                        f"/api/v1/admin/analytics/feedback{qs}",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                for p in ctx:
                    p.stop()
                app.dependency_overrides.clear()
        return res

    async def test_feedback_default_month_range(self):
        """기본 unit=month 반환 구조 검증."""
        patches = [
            patch("api.src.routers.admin.analytics.get_feedback_summary", new=AsyncMock(return_value=_DEFAULT_SUMMARY)),
            patch("api.src.routers.admin.analytics.get_feedback_series", new=AsyncMock(return_value=_DEFAULT_SERIES)),
            patch("api.src.routers.admin.analytics.get_feedback_items_total", new=AsyncMock(return_value=154)),
            patch("api.src.routers.admin.analytics.get_feedback_items", new=AsyncMock(return_value=_DEFAULT_ITEMS)),
        ]
        res = await self._call_with_patches(patches)
        assert res.status_code == 200
        data = res.json()
        assert data["unit"] == "month"
        assert "from" in data and "to" in data
        assert data["summary"]["good_count"] == 120
        assert data["summary"]["bad_count"] == 34
        assert data["summary"]["good_ratio"] == 0.779
        assert len(data["series"]) == 2
        assert len(data["items"]) == 1
        assert data["total"] == 154

    async def test_feedback_rating_filter_good(self):
        """rating_filter=good 파라미터 전달 확인."""
        items_good = [{"qa_log_id": 1, "question_text": "Q", "answer_text": "A", "rating": "good", "segment": None, "user_id": None, "email": None, "created_at": "2026-04-01T10:00:00+09:00"}]
        patches = [
            patch("api.src.routers.admin.analytics.get_feedback_summary", new=AsyncMock(return_value=_DEFAULT_SUMMARY)),
            patch("api.src.routers.admin.analytics.get_feedback_series", new=AsyncMock(return_value=[])),
            patch("api.src.routers.admin.analytics.get_feedback_items_total", new=AsyncMock(return_value=1)),
            patch("api.src.routers.admin.analytics.get_feedback_items", new=AsyncMock(return_value=items_good)),
        ]
        res = await self._call_with_patches(patches, "?rating_filter=good")
        assert res.status_code == 200
        data = res.json()
        assert data["rating_filter"] == "good"
        assert all(item["rating"] == "good" for item in data["items"])

    async def test_feedback_rating_filter_bad(self):
        items_bad = [{"qa_log_id": 2, "question_text": "Q", "answer_text": "A", "rating": "bad", "segment": None, "user_id": None, "email": None, "created_at": "2026-04-01T10:00:00+09:00"}]
        patches = [
            patch("api.src.routers.admin.analytics.get_feedback_summary", new=AsyncMock(return_value=_DEFAULT_SUMMARY)),
            patch("api.src.routers.admin.analytics.get_feedback_series", new=AsyncMock(return_value=[])),
            patch("api.src.routers.admin.analytics.get_feedback_items_total", new=AsyncMock(return_value=1)),
            patch("api.src.routers.admin.analytics.get_feedback_items", new=AsyncMock(return_value=items_bad)),
        ]
        res = await self._call_with_patches(patches, "?rating_filter=bad")
        assert res.status_code == 200
        assert res.json()["rating_filter"] == "bad"

    async def test_feedback_q_keyword_ilike(self):
        """q=키워드 파라미터가 정상 처리됨."""
        patches = [
            patch("api.src.routers.admin.analytics.get_feedback_summary", new=AsyncMock(return_value=_DEFAULT_SUMMARY)),
            patch("api.src.routers.admin.analytics.get_feedback_series", new=AsyncMock(return_value=[])),
            patch("api.src.routers.admin.analytics.get_feedback_items_total", new=AsyncMock(return_value=0)),
            patch("api.src.routers.admin.analytics.get_feedback_items", new=AsyncMock(return_value=[])),
        ]
        res = await self._call_with_patches(patches, "?q=임플란트")
        assert res.status_code == 200

    async def test_feedback_anonymous_user_included(self):
        """user_id=NULL 행(segment=None) items 포함."""
        anon_item = {"qa_log_id": 999, "question_text": "Q", "answer_text": None, "rating": "bad", "segment": None, "user_id": None, "email": None, "created_at": "2026-04-01T10:00:00+09:00"}
        patches = [
            patch("api.src.routers.admin.analytics.get_feedback_summary", new=AsyncMock(return_value=_DEFAULT_SUMMARY)),
            patch("api.src.routers.admin.analytics.get_feedback_series", new=AsyncMock(return_value=[])),
            patch("api.src.routers.admin.analytics.get_feedback_items_total", new=AsyncMock(return_value=1)),
            patch("api.src.routers.admin.analytics.get_feedback_items", new=AsyncMock(return_value=[anon_item])),
        ]
        res = await self._call_with_patches(patches)
        assert res.status_code == 200
        items = res.json()["items"]
        assert items[0]["segment"] is None

    async def test_feedback_good_ratio_calculation(self):
        """good_ratio 소수점 3자리."""
        summary = {"good_count": 2, "bad_count": 1, "good_ratio": 0.667}
        patches = [
            patch("api.src.routers.admin.analytics.get_feedback_summary", new=AsyncMock(return_value=summary)),
            patch("api.src.routers.admin.analytics.get_feedback_series", new=AsyncMock(return_value=[])),
            patch("api.src.routers.admin.analytics.get_feedback_items_total", new=AsyncMock(return_value=0)),
            patch("api.src.routers.admin.analytics.get_feedback_items", new=AsyncMock(return_value=[])),
        ]
        res = await self._call_with_patches(patches)
        assert res.status_code == 200
        ratio = res.json()["summary"]["good_ratio"]
        assert ratio == 0.667

    async def test_feedback_series_empty_buckets_zero(self):
        """빈 버킷은 good=0, bad=0."""
        series = [{"bucket_start": "2026-04-01", "good": 0, "bad": 0}]
        patches = [
            patch("api.src.routers.admin.analytics.get_feedback_summary", new=AsyncMock(return_value={"good_count": 0, "bad_count": 0, "good_ratio": None})),
            patch("api.src.routers.admin.analytics.get_feedback_series", new=AsyncMock(return_value=series)),
            patch("api.src.routers.admin.analytics.get_feedback_items_total", new=AsyncMock(return_value=0)),
            patch("api.src.routers.admin.analytics.get_feedback_items", new=AsyncMock(return_value=[])),
        ]
        res = await self._call_with_patches(patches)
        assert res.status_code == 200
        s = res.json()["series"][0]
        assert s["good"] == 0
        assert s["bad"] == 0

    async def test_feedback_pagination(self):
        """page/per_page 파라미터."""
        patches = [
            patch("api.src.routers.admin.analytics.get_feedback_summary", new=AsyncMock(return_value=_DEFAULT_SUMMARY)),
            patch("api.src.routers.admin.analytics.get_feedback_series", new=AsyncMock(return_value=[])),
            patch("api.src.routers.admin.analytics.get_feedback_items_total", new=AsyncMock(return_value=100)),
            patch("api.src.routers.admin.analytics.get_feedback_items", new=AsyncMock(return_value=[])),
        ]
        res = await self._call_with_patches(patches, "?page=2&per_page=10")
        assert res.status_code == 200
        data = res.json()
        assert data["page"] == 2
        assert data["per_page"] == 10

    async def test_feedback_per_page_max_200(self):
        """per_page=201 시 422."""
        token = _make_admin_jwt()
        admin = _make_admin()
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get(
                    "/api/v1/admin/analytics/feedback?per_page=201",
                    cookies={"denvia_admin_session": token},
                )
        assert res.status_code == 422

    async def test_feedback_no_store_header(self):
        """Cache-Control: no-store 헤더."""
        patches = [
            patch("api.src.routers.admin.analytics.get_feedback_summary", new=AsyncMock(return_value=_DEFAULT_SUMMARY)),
            patch("api.src.routers.admin.analytics.get_feedback_series", new=AsyncMock(return_value=[])),
            patch("api.src.routers.admin.analytics.get_feedback_items_total", new=AsyncMock(return_value=0)),
            patch("api.src.routers.admin.analytics.get_feedback_items", new=AsyncMock(return_value=[])),
        ]
        res = await self._call_with_patches(patches)
        assert res.status_code == 200
        assert res.headers.get("cache-control") == "no-store"


@pytest.mark.asyncio
class TestFeedbackExport:
    async def test_feedback_export_xlsx(self):
        """xlsx Content-Type + filename 헤더."""
        rows = [
            {
                "qa_log_id": 1,
                "question_text": "Q1",
                "answer_text": "A1",
                "rating": "good",
                "segment": "doctor",
                "user_id": 42,
                "email": "doctor@denvia.test",
                "created_at_kst": "2026-04-15 10:23:00",
            }
        ]
        token = _make_admin_jwt()
        admin = _make_admin()
        gen = _stub_session()
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
            app.dependency_overrides[get_session] = gen
            with patch(
                "api.src.routers.admin.analytics.get_feedback_export_rows",
                new=AsyncMock(return_value=(rows, False)),
            ):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.get(
                        "/api/v1/admin/analytics/feedback/export",
                        cookies={"denvia_admin_session": token},
                    )
            app.dependency_overrides.clear()
        assert res.status_code == 200
        ct = res.headers.get("content-type", "")
        assert "spreadsheetml" in ct
        cd = res.headers.get("content-disposition", "")
        assert "feedback_" in cd
        assert ".xlsx" in cd

    async def test_feedback_export_requires_admin(self):
        token = _make_jwt(role="user")
        regular = _make_admin()
        regular.role = "user"
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=regular)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get(
                    "/api/v1/admin/analytics/feedback/export",
                    cookies={"denvia_admin_session": token},
                )
        assert res.status_code == 401


@pytest.mark.asyncio
class TestFeedbackDetailEndpoint:
    """GET /admin/analytics/feedback/{qa_log_id} — Drawer 상세보기 + top-k."""

    def _row(
        self,
        *,
        qa_log_id: int = 1001,
        retrieved_docs=None,
        normalized_query: str | None = "임플란트 보철물 종류",
        rule_matched: bool = False,
        answer_text: str | None = "임플란트 보철물은 …",
        status: str | None = "ok",
    ):
        from datetime import datetime, timezone, timedelta

        row = MagicMock()
        row.id = qa_log_id
        row.question_text = "임플란트 보철물 선택 기준은?"
        row.normalized_query = normalized_query
        row.retrieved_docs = retrieved_docs
        row.answer_text = answer_text
        row.rule_matched = rule_matched
        row.status = status
        kst = timezone(timedelta(hours=9))
        row.created_at = datetime(2026, 4, 15, 10, 23, tzinfo=kst)
        return row

    async def _call(self, *, qa_log_id: int, row):
        token = _make_admin_jwt()
        admin = _make_admin()
        session = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=row)
        session.execute = AsyncMock(return_value=result)

        async def gen():
            yield session

        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
            app.dependency_overrides[get_session] = gen
            try:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.get(
                        f"/api/v1/admin/analytics/feedback/{qa_log_id}",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()
        return res

    async def test_detail_returns_retrieved_docs_topk(self):
        """top-k 검색 문서 + 동의어 치환 쿼리 응답."""
        docs = [
            {"page_content": "크라운은 단일 치아 보철물입니다.", "metadata": {"source": "doc-a.pdf", "page": 12}},
            {"page_content": "브릿지는 결손 치아를 지지합니다.", "metadata": {"source": "doc-b.pdf"}},
        ]
        row = self._row(retrieved_docs=docs)
        res = await self._call(qa_log_id=1001, row=row)
        assert res.status_code == 200
        data = res.json()
        assert data["qa_log_id"] == 1001
        assert data["normalized_query"] == "임플란트 보철물 종류"
        assert len(data["retrieved_docs"]) == 2
        assert data["retrieved_docs"][0]["page_content"].startswith("크라운")
        assert data["retrieved_docs"][0]["metadata"]["source"] == "doc-a.pdf"
        assert data["rule_matched"] is False
        assert res.headers.get("cache-control") == "no-store"

    async def test_detail_404_when_missing(self):
        res = await self._call(qa_log_id=99999, row=None)
        assert res.status_code == 404
        assert res.json()["detail"]["code"] == "ADMIN_FEEDBACK_QA_LOG_NOT_FOUND"

    async def test_detail_rule_matched_empty_docs(self):
        """rule_matched=True 경로는 retrieved_docs=[]로 응답."""
        row = self._row(retrieved_docs=None, rule_matched=True, normalized_query=None)
        res = await self._call(qa_log_id=1002, row=row)
        assert res.status_code == 200
        data = res.json()
        assert data["rule_matched"] is True
        assert data["retrieved_docs"] == []

    async def test_detail_skips_non_dict_doc_entries(self):
        """JSONB 손상 케이스: dict가 아닌 항목은 무시."""
        docs = [
            {"page_content": "정상 문서", "metadata": {"source": "ok.pdf"}},
            "이건 문자열인데 잘못 저장됨",
            123,
        ]
        row = self._row(retrieved_docs=docs)
        res = await self._call(qa_log_id=1003, row=row)
        assert res.status_code == 200
        assert len(res.json()["retrieved_docs"]) == 1

    async def test_detail_requires_admin(self):
        token = _make_jwt(role="user")
        regular = _make_admin()
        regular.role = "user"
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=regular)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get(
                    "/api/v1/admin/analytics/feedback/1001",
                    cookies={"denvia_admin_session": token},
                )
        assert res.status_code == 401

    async def test_detail_does_not_shadow_export_route(self):
        """라우트 등록 순서: /feedback/export 가 /feedback/{qa_log_id} 보다 우선해야 함."""
        token = _make_admin_jwt()
        admin = _make_admin()
        gen = _stub_session()
        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
            app.dependency_overrides[get_session] = gen
            with patch(
                "api.src.routers.admin.analytics.get_feedback_export_rows",
                new=AsyncMock(return_value=([], False)),
            ):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.get(
                        "/api/v1/admin/analytics/feedback/export",
                        cookies={"denvia_admin_session": token},
                    )
            app.dependency_overrides.clear()
        assert res.status_code == 200
        assert "spreadsheetml" in res.headers.get("content-type", "")
