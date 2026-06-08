"""Admin 질문 분석 API 통합 테스트.

검증:
- 관리자 인증 가드 (401)
- 기본 unit=day 응답 구조
- sort 파라미터(latest/tokens/email) 전달
- 페이지·필터 파라미터 전달
- 엑셀 export 컨텐츠 타입·헤더
"""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest
from httpx import ASGITransport, AsyncClient

from api.src.main import app
from api.src.models.base import get_session
from api.src.services.analytics_service import QuestionsBucket, QuestionsSummary
from api.src.settings import settings


def _make_admin_jwt(user_id: int = 1) -> str:
    payload = {
        "sub": str(user_id),
        "aud": "denvia-admin",
        "exp": int(time.time()) + 3600,
    }
    return pyjwt.encode(
        payload,
        settings.denvia_jwt_secret,
        algorithm=settings.denvia_jwt_algorithm,
    )


def _make_user_jwt() -> str:
    payload = {
        "sub": "1",
        "role": "user",
        "sub_status": "free",
        "exp": int(time.time()) + 3600,
    }
    return pyjwt.encode(
        payload,
        settings.denvia_jwt_secret,
        algorithm=settings.denvia_jwt_algorithm,
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


def _stub_session():
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()

    async def gen():
        yield session

    return gen


_DEFAULT_SUMMARY = QuestionsSummary(
    buckets=[
        QuestionsBucket(bucket_start=date(2026, 5, 24), count=10),
        QuestionsBucket(bucket_start=date(2026, 5, 25), count=15),
        QuestionsBucket(bucket_start=date(2026, 5, 26), count=8),
    ],
    from_=date(2026, 4, 26),
    to=date(2026, 5, 26),
    total_count=33,
)

_DEFAULT_ITEMS = [
    {
        "qa_log_id": 1001,
        "question_text": "임플란트 보험청구 절차는?",
        "answer_text": "임플란트는 …",
        "input_tokens": 120,
        "output_tokens": 480,
        "total_tokens": 600,
        "cost_usd": "0.002400",
        "status": "complete",
        "user_id": 42,
        "email": "user@denvia.test",
        "segment": "doctor",
        "created_at": "2026-05-26T10:23:00+09:00",
    },
    {
        "qa_log_id": 1002,
        "question_text": "스케일링 본인부담금 계산법?",
        "answer_text": "스케일링 본인부담금은 …",
        "input_tokens": 90,
        "output_tokens": 250,
        "total_tokens": 340,
        "cost_usd": "0.001000",
        "status": "complete",
        "user_id": 43,
        "email": "hygienist@denvia.test",
        "segment": "hygienist",
        "created_at": "2026-05-26T09:10:00+09:00",
    },
]


def _patches(
    *,
    summary: QuestionsSummary | None = None,
    items: list[dict] | None = None,
    total: int = 33,
):
    summary = summary or _DEFAULT_SUMMARY
    items = items if items is not None else _DEFAULT_ITEMS
    return [
        patch(
            "api.src.routers.admin.analytics.get_questions_summary",
            new=AsyncMock(return_value=summary),
        ),
        patch(
            "api.src.routers.admin.analytics.get_questions_items_total",
            new=AsyncMock(return_value=total),
        ),
        patch(
            "api.src.routers.admin.analytics.get_questions_items",
            new=AsyncMock(return_value=items),
        ),
    ]


async def _call(qs: str = "", patches_list=None):
    token = _make_admin_jwt()
    admin = _make_admin()
    gen = _stub_session()
    patches_list = patches_list or _patches()
    with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
        app.dependency_overrides[get_session] = gen
        for p in patches_list:
            p.start()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                res = await client.get(
                    f"/api/v1/admin/analytics/questions{qs}",
                    cookies={"denvia_admin_session": token},
                )
        finally:
            for p in patches_list:
                p.stop()
            app.dependency_overrides.clear()
    return res


@pytest.mark.asyncio
class TestQuestionsEndpointAuth:
    async def test_questions_requires_session_401(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.get("/api/v1/admin/analytics/questions")
        assert res.status_code == 401

    async def test_questions_rejects_non_admin(self):
        token = _make_user_jwt()
        regular = _make_admin()
        regular.role = "user"
        with patch(
            "api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=regular)
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                res = await client.get(
                    "/api/v1/admin/analytics/questions",
                    cookies={"denvia_admin_session": token},
                )
        assert res.status_code == 401


@pytest.mark.asyncio
class TestQuestionsEndpoint:
    async def test_default_returns_day_unit_with_buckets_and_items(self):
        res = await _call()
        assert res.status_code == 200
        data = res.json()
        assert data["unit"] == "day"
        assert data["sort"] == "latest"
        assert data["total_count"] == 33
        assert len(data["buckets"]) == 3
        # 버킷은 ISO 날짜 + count 키
        assert data["buckets"][0]["bucket_start"] == "2026-05-24"
        assert data["buckets"][0]["count"] == 10
        # items 직렬화
        assert len(data["items"]) == 2
        first = data["items"][0]
        assert first["qa_log_id"] == 1001
        assert first["total_tokens"] == 600
        assert first["email"] == "user@denvia.test"
        assert first["segment"] == "doctor"
        assert data["page"] == 1
        assert data["per_page"] == 50
        assert data["total"] == 33

    async def test_sort_tokens_passthrough(self):
        captured: dict[str, object] = {}

        async def fake_items(*args, **kwargs):
            # 4번째 positional argument == sort
            captured["sort"] = args[3]
            return _DEFAULT_ITEMS

        patches_list = _patches()
        patches_list[2] = patch(
            "api.src.routers.admin.analytics.get_questions_items",
            new=AsyncMock(side_effect=fake_items),
        )
        res = await _call("?sort=tokens", patches_list=patches_list)
        assert res.status_code == 200
        assert res.json()["sort"] == "tokens"
        assert captured["sort"] == "tokens"

    async def test_sort_email_passthrough(self):
        res = await _call("?sort=email")
        assert res.status_code == 200
        assert res.json()["sort"] == "email"

    async def test_unit_year_accepted(self):
        res = await _call("?unit=year")
        assert res.status_code == 200
        assert res.json()["unit"] == "year"

    async def test_invalid_unit_rejected(self):
        res = await _call("?unit=fortnight")
        assert res.status_code == 422

    async def test_pagination_params(self):
        captured: dict[str, object] = {}

        async def fake_items(*args, **kwargs):
            captured["page"] = args[4]
            captured["per_page"] = args[5]
            return []

        patches_list = _patches(items=[])
        patches_list[2] = patch(
            "api.src.routers.admin.analytics.get_questions_items",
            new=AsyncMock(side_effect=fake_items),
        )
        res = await _call("?page=3&per_page=20", patches_list=patches_list)
        assert res.status_code == 200
        assert captured["page"] == 3
        assert captured["per_page"] == 20


@pytest.mark.asyncio
class TestQuestionsExport:
    async def test_export_returns_xlsx_with_disposition(self):
        token = _make_admin_jwt()
        admin = _make_admin()
        gen = _stub_session()

        patches_list = [
            patch(
                "api.src.routers.admin.analytics.get_questions_summary",
                new=AsyncMock(return_value=_DEFAULT_SUMMARY),
            ),
            patch(
                "api.src.routers.admin.analytics.get_questions_export_rows",
                new=AsyncMock(
                    return_value=(
                        [
                            {
                                "qa_log_id": 1001,
                                "question_text": "Q1",
                                "answer_text": "A1",
                                "input_tokens": 1,
                                "output_tokens": 2,
                                "total_tokens": 3,
                                "cost_usd": "0.000010",
                                "status": "complete",
                                "user_id": 42,
                                "email": "u@denvia.test",
                                "segment": "doctor",
                                "created_at_kst": "2026-05-26 10:23:00",
                            }
                        ],
                        False,
                    )
                ),
            ),
        ]

        with patch(
            "api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)
        ):
            app.dependency_overrides[get_session] = gen
            for p in patches_list:
                p.start()
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.get(
                        "/api/v1/admin/analytics/questions/export?unit=day&sort=latest",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                for p in patches_list:
                    p.stop()
                app.dependency_overrides.clear()

        assert res.status_code == 200
        assert (
            res.headers["content-type"]
            == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert "attachment" in res.headers["content-disposition"]
        assert "questions_" in res.headers["content-disposition"]
        # XLSX magic bytes (zip)
        assert res.content[:2] == b"PK"
