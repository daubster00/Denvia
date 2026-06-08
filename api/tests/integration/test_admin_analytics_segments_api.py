"""Story 6.4 — Admin 가입유형 통계 API 통합 테스트 (AC-1, AC-12)."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest
from httpx import ASGITransport, AsyncClient

from api.src.main import app
from api.src.models.base import get_session
from api.src.services.analytics_service import ExperienceRow, SegmentRow
from api.src.settings import settings


def _make_admin_jwt(user_id: int = 99) -> str:
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
    user.id = 99
    user.email = "admin@denvia.local"
    user.role = "admin"
    user.subscription_status = "free"
    user.segment = None
    user.withdrawn_at = None
    user.must_reset_password = False
    user.current_session_id = None
    user.admin_grade = "master"
    return user


def _stub_session_dependency():
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()

    async def gen():
        yield session

    return gen


def _make_stats_payload(
    *,
    by_segment: list[SegmentRow] | None = None,
    by_experience: list[ExperienceRow] | None = None,
    total: int = 0,
    include_withdrawn: bool = False,
    include_blocked: bool = False,
) -> dict:
    segs = by_segment if by_segment is not None else [
        SegmentRow(segment="doctor", count=0, active_count=0, pro_count=0),
        SegmentRow(segment="hygienist", count=0, active_count=0, pro_count=0),
        SegmentRow(segment="student_other", count=0, active_count=0, pro_count=0),
    ]
    exps = by_experience if by_experience is not None else [
        ExperienceRow(segment=seg, years_bucket=b, count=0)
        for seg in ("doctor", "hygienist")
        for b in ("0-2", "3-5", "6-10", "11-20", "20+")
    ]
    return {
        "applied_filters": {
            "include_withdrawn": include_withdrawn,
            "include_blocked": include_blocked,
        },
        "total": total,
        "by_segment": segs,
        "by_experience": exps,
    }


@pytest.mark.asyncio
class TestSegmentsEndpointAuth:
    async def test_unauth_returns_401(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.get("/api/v1/admin/analytics/segments")
        assert res.status_code == 401

    async def test_user_role_returns_401(self):
        token = _make_user_jwt()
        regular = _make_admin()
        regular.role = "user"
        with patch(
            "api.src.deps.auth.get_user_by_id",
            new=AsyncMock(return_value=regular),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                res = await client.get(
                    "/api/v1/admin/analytics/segments",
                    cookies={"denvia_admin_session": token},
                )
        assert res.status_code == 401


@pytest.mark.asyncio
class TestSegmentsEndpoint:
    async def _call(self, qs: str = ""):
        token = _make_admin_jwt()
        admin = _make_admin()
        gen = _stub_session_dependency()
        with patch(
            "api.src.deps.auth.get_user_by_id",
            new=AsyncMock(return_value=admin),
        ):
            app.dependency_overrides[get_session] = gen
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    res = await client.get(
                        f"/api/v1/admin/analytics/segments{qs}",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()
        return res

    async def test_basic_distribution(self):
        payload = _make_stats_payload(
            by_segment=[
                SegmentRow(segment="doctor", count=3, active_count=3, pro_count=1),
                SegmentRow(segment="hygienist", count=1, active_count=1, pro_count=0),
                SegmentRow(
                    segment="student_other", count=1, active_count=1, pro_count=0
                ),
            ],
            by_experience=[
                ExperienceRow(segment="doctor", years_bucket="3-5", count=2),
                ExperienceRow(segment="doctor", years_bucket="6-10", count=1),
            ]
            + [
                ExperienceRow(segment="doctor", years_bucket=b, count=0)
                for b in ("0-2", "11-20", "20+")
            ]
            + [
                ExperienceRow(segment="hygienist", years_bucket=b, count=0)
                for b in ("0-2", "3-5", "6-10", "11-20", "20+")
            ],
            total=5,
        )
        with patch(
            "api.src.routers.admin.analytics.get_segment_stats",
            new=AsyncMock(return_value=payload),
        ):
            res = await self._call()
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 5
        assert len(body["by_segment"]) == 3
        assert body["by_segment"][0]["segment"] == "doctor"
        assert body["by_segment"][0]["count"] == 3
        assert body["by_segment"][0]["pro_count"] == 1
        assert body["applied_filters"] == {
            "include_withdrawn": False,
            "include_blocked": False,
        }

    async def test_default_excludes_withdrawn_and_blocked(self):
        payload = _make_stats_payload(total=2)
        called_kwargs: dict = {}

        async def fake(_db, **kwargs):
            called_kwargs.update(kwargs)
            return payload

        with patch(
            "api.src.routers.admin.analytics.get_segment_stats",
            new=fake,
        ):
            res = await self._call()
        assert res.status_code == 200
        assert called_kwargs == {
            "include_withdrawn": False,
            "include_blocked": False,
        }

    async def test_include_withdrawn_true(self):
        payload = _make_stats_payload(total=10, include_withdrawn=True)
        called_kwargs: dict = {}

        async def fake(_db, **kwargs):
            called_kwargs.update(kwargs)
            return payload

        with patch(
            "api.src.routers.admin.analytics.get_segment_stats",
            new=fake,
        ):
            res = await self._call("?include_withdrawn=true")
        assert res.status_code == 200
        assert called_kwargs["include_withdrawn"] is True
        assert res.json()["applied_filters"]["include_withdrawn"] is True

    async def test_include_blocked_true(self):
        payload = _make_stats_payload(total=8, include_blocked=True)
        called_kwargs: dict = {}

        async def fake(_db, **kwargs):
            called_kwargs.update(kwargs)
            return payload

        with patch(
            "api.src.routers.admin.analytics.get_segment_stats",
            new=fake,
        ):
            res = await self._call("?include_blocked=true")
        assert res.status_code == 200
        assert called_kwargs["include_blocked"] is True
        assert res.json()["applied_filters"]["include_blocked"] is True

    async def test_no_store_header(self):
        payload = _make_stats_payload()
        with patch(
            "api.src.routers.admin.analytics.get_segment_stats",
            new=AsyncMock(return_value=payload),
        ):
            res = await self._call()
        assert res.headers.get("Cache-Control") == "no-store"

    async def test_canonical_segment_keys_only(self):
        """응답에는 doctor/hygienist/student_other만 등장한다."""
        payload = _make_stats_payload(total=1)
        with patch(
            "api.src.routers.admin.analytics.get_segment_stats",
            new=AsyncMock(return_value=payload),
        ):
            res = await self._call()
        assert res.status_code == 200
        body = res.json()
        for row in body["by_segment"]:
            assert row["segment"] in ("doctor", "hygienist", "student_other")
