"""Admin RAG 동의어 사전 통합 테스트 — Story 8.5.

권한·검색·CRUD·CSV 라운드트립을 라우터 레벨에서 검증한다.
서비스 레이어는 mock으로 격리(prompts.py 통합 테스트 패턴과 동일).
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest
from httpx import ASGITransport, AsyncClient

from api.src.main import app
from api.src.models.base import get_session
from api.src.settings import settings


_next_user_id = 8500


def _make_jwt(role: str = "admin") -> tuple[str, int]:
    global _next_user_id
    _next_user_id += 1
    uid = _next_user_id
    if role == "admin":
        payload = {
            "sub": str(uid),
            "aud": "denvia-admin",
            "exp": int(time.time()) + 3600,
        }
    else:
        payload = {
            "sub": str(uid),
            "role": role,
            "sub_status": "free",
            "exp": int(time.time()) + 3600,
        }
    token = pyjwt.encode(
        payload, settings.denvia_jwt_secret, algorithm=settings.denvia_jwt_algorithm
    )
    return token, uid


def _admin_user_mock(user_id: int):
    user = MagicMock()
    user.id = user_id
    user.email = "admin@denvia.local"
    user.role = "admin"
    user.subscription_status = "free"
    user.segment = None
    user.years_of_experience = None
    user.withdrawn_at = None
    user.must_reset_password = False
    return user


def _normal_user_mock(user_id: int):
    user = MagicMock()
    user.id = user_id
    user.email = "user@denvia.com"
    user.role = "user"
    user.subscription_status = "free"
    user.segment = None
    user.years_of_experience = None
    user.withdrawn_at = None
    user.must_reset_password = False
    return user


def _make_audit_ctx():
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    class FakeCtx:
        async def __aenter__(self_inner):
            return session

        async def __aexit__(self_inner, *a):
            pass

    return FakeCtx()


def _simple_session_gen():
    session = MagicMock()
    session.execute = AsyncMock(return_value=MagicMock())
    session.commit = AsyncMock()

    async def _gen():
        yield session

    return _gen


def _list_response_factory(groups: list[dict], total: int, page: int = 1, size: int = 20):
    from api.src.schemas.admin.synonyms import (
        SynonymGroupRead,
        SynonymListResponse,
    )

    return SynonymListResponse(
        groups=[
            SynonymGroupRead(
                id=g["id"],
                canonical_term=g["canonical_term"],
                synonyms=g.get("synonyms", []),
                updated_at=g.get(
                    "updated_at", datetime(2026, 5, 12, tzinfo=timezone.utc)
                ),
            )
            for g in groups
        ],
        total=total,
        page=page,
        size=size,
    )


# ──────────────────────────────────────────────────────────────────────────────
# GET /admin/rag/synonyms — 권한·검색
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_synonyms_returns_200_with_groups():
    token, uid = _make_jwt("admin")
    admin = _admin_user_mock(uid)

    expected = _list_response_factory(
        [
            {"id": 1, "canonical_term": "광중합기", "synonyms": ["큐링기", "큐어링"]},
            {"id": 2, "canonical_term": "공단검진", "synonyms": ["국가검진"]},
        ],
        total=2,
    )

    with (
        patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
        patch(
            "api.src.services.synonym_service.list_groups",
            new=AsyncMock(return_value=expected),
        ),
        patch(
            "api.src.middleware.audit.async_session_factory",
            side_effect=lambda: _make_audit_ctx(),
        ),
    ):
        app.dependency_overrides[get_session] = _simple_session_gen()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                res = await client.get(
                    "/api/v1/admin/rag/synonyms",
                    cookies={"denvia_admin_session": token},
                )
        finally:
            app.dependency_overrides.pop(get_session, None)

    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 2
    assert len(body["groups"]) == 2
    assert body["groups"][0]["canonical_term"] == "광중합기"
    assert res.headers.get("Cache-Control") == "no-store"


@pytest.mark.asyncio
async def test_list_synonyms_non_admin_returns_401():
    token, uid = _make_jwt("user")
    user = _normal_user_mock(uid)

    with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)):
        app.dependency_overrides[get_session] = _simple_session_gen()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                res = await client.get(
                    "/api/v1/admin/rag/synonyms",
                    cookies={"denvia_admin_session": token},
                )
        finally:
            app.dependency_overrides.pop(get_session, None)

    assert res.status_code == 401


@pytest.mark.asyncio
async def test_list_synonyms_size_over_100_returns_422():
    token, uid = _make_jwt("admin")
    admin = _admin_user_mock(uid)

    with (
        patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
        patch(
            "api.src.middleware.audit.async_session_factory",
            side_effect=lambda: _make_audit_ctx(),
        ),
    ):
        app.dependency_overrides[get_session] = _simple_session_gen()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                res = await client.get(
                    "/api/v1/admin/rag/synonyms?size=999",
                    cookies={"denvia_admin_session": token},
                )
        finally:
            app.dependency_overrides.pop(get_session, None)

    assert res.status_code == 422


# ──────────────────────────────────────────────────────────────────────────────
# POST /admin/rag/synonyms — 생성
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_synonym_returns_201():
    token, uid = _make_jwt("admin")
    admin = _admin_user_mock(uid)

    fake_row = MagicMock()
    fake_row.id = 999
    fake_row.canonical_term = "광중합기"
    fake_row.synonyms = ["큐링기", "큐어링"]
    fake_row.updated_at = datetime(2026, 5, 12, tzinfo=timezone.utc)

    with (
        patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
        patch(
            "api.src.services.synonym_service.create_group",
            new=AsyncMock(return_value=fake_row),
        ),
        patch(
            "api.src.middleware.audit.async_session_factory",
            side_effect=lambda: _make_audit_ctx(),
        ),
    ):
        app.dependency_overrides[get_session] = _simple_session_gen()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                res = await client.post(
                    "/api/v1/admin/rag/synonyms",
                    json={"canonical_term": "광중합기", "synonyms": ["큐링기", "큐어링"]},
                    cookies={"denvia_admin_session": token},
                )
        finally:
            app.dependency_overrides.pop(get_session, None)

    assert res.status_code == 201
    body = res.json()
    assert body["canonical_term"] == "광중합기"
    assert body["synonyms"] == ["큐링기", "큐어링"]


@pytest.mark.asyncio
async def test_create_synonym_conflict_returns_409():
    token, uid = _make_jwt("admin")
    admin = _admin_user_mock(uid)

    from fastapi import HTTPException

    with (
        patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
        patch(
            "api.src.services.synonym_service.create_group",
            new=AsyncMock(
                side_effect=HTTPException(
                    status_code=409,
                    detail={
                        "code": "SYNONYM_CONFLICT",
                        "message": "이미 존재",
                        "conflicting_group_id": 12,
                        "conflicting_term": "광중합기",
                    },
                )
            ),
        ),
        patch(
            "api.src.middleware.audit.async_session_factory",
            side_effect=lambda: _make_audit_ctx(),
        ),
    ):
        app.dependency_overrides[get_session] = _simple_session_gen()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                res = await client.post(
                    "/api/v1/admin/rag/synonyms",
                    json={"canonical_term": "광중합기", "synonyms": []},
                    cookies={"denvia_admin_session": token},
                )
        finally:
            app.dependency_overrides.pop(get_session, None)

    assert res.status_code == 409
    body = res.json()
    assert body["code"] == "SYNONYM_CONFLICT"


@pytest.mark.asyncio
async def test_create_synonym_empty_canonical_returns_422():
    token, uid = _make_jwt("admin")
    admin = _admin_user_mock(uid)

    with (
        patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
        patch(
            "api.src.middleware.audit.async_session_factory",
            side_effect=lambda: _make_audit_ctx(),
        ),
    ):
        app.dependency_overrides[get_session] = _simple_session_gen()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                res = await client.post(
                    "/api/v1/admin/rag/synonyms",
                    json={"canonical_term": "   ", "synonyms": []},
                    cookies={"denvia_admin_session": token},
                )
        finally:
            app.dependency_overrides.pop(get_session, None)

    assert res.status_code == 422


# ──────────────────────────────────────────────────────────────────────────────
# PUT / DELETE
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_synonym_not_found_returns_404():
    token, uid = _make_jwt("admin")
    admin = _admin_user_mock(uid)

    from fastapi import HTTPException

    with (
        patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
        patch(
            "api.src.services.synonym_service.update_group",
            new=AsyncMock(
                side_effect=HTTPException(
                    status_code=404, detail={"code": "SYNONYM_GROUP_NOT_FOUND"}
                )
            ),
        ),
        patch(
            "api.src.middleware.audit.async_session_factory",
            side_effect=lambda: _make_audit_ctx(),
        ),
    ):
        app.dependency_overrides[get_session] = _simple_session_gen()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                res = await client.put(
                    "/api/v1/admin/rag/synonyms/99999",
                    json={"canonical_term": "X", "synonyms": []},
                    cookies={"denvia_admin_session": token},
                )
        finally:
            app.dependency_overrides.pop(get_session, None)

    assert res.status_code == 404
    assert res.json()["code"] == "SYNONYM_GROUP_NOT_FOUND"


@pytest.mark.asyncio
async def test_delete_synonym_returns_204():
    token, uid = _make_jwt("admin")
    admin = _admin_user_mock(uid)

    with (
        patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
        patch(
            "api.src.services.synonym_service.delete_group",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "api.src.middleware.audit.async_session_factory",
            side_effect=lambda: _make_audit_ctx(),
        ),
    ):
        app.dependency_overrides[get_session] = _simple_session_gen()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                res = await client.delete(
                    "/api/v1/admin/rag/synonyms/1",
                    cookies={"denvia_admin_session": token},
                )
        finally:
            app.dependency_overrides.pop(get_session, None)

    assert res.status_code == 204


# ──────────────────────────────────────────────────────────────────────────────
# CSV export / import
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_export_csv_returns_attachment_with_bom():
    token, uid = _make_jwt("admin")
    admin = _admin_user_mock(uid)

    body_bytes = "﻿canonical_term,synonyms\n광중합기,큐링기\n".encode("utf-8")

    with (
        patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
        patch(
            "api.src.services.synonym_service.export_csv",
            new=AsyncMock(return_value=body_bytes),
        ),
        patch(
            "api.src.middleware.audit.async_session_factory",
            side_effect=lambda: _make_audit_ctx(),
        ),
    ):
        app.dependency_overrides[get_session] = _simple_session_gen()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                res = await client.get(
                    "/api/v1/admin/rag/synonyms/export",
                    cookies={"denvia_admin_session": token},
                )
        finally:
            app.dependency_overrides.pop(get_session, None)

    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert "attachment" in res.headers["content-disposition"]
    assert res.content.startswith(b"\xef\xbb\xbf")


@pytest.mark.asyncio
async def test_import_csv_dry_run_returns_summary():
    token, uid = _make_jwt("admin")
    admin = _admin_user_mock(uid)

    from api.src.schemas.admin.synonyms import ImportPreviewResponse, ImportSummary

    expected = ImportPreviewResponse(
        summary=ImportSummary(to_create=1, to_update=0, conflicts=0, invalid=0, unchanged=0),
        conflicts=[],
        invalid=[],
    )

    with (
        patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
        patch(
            "api.src.services.synonym_service.import_csv",
            new=AsyncMock(return_value=expected),
        ),
        patch(
            "api.src.middleware.audit.async_session_factory",
            side_effect=lambda: _make_audit_ctx(),
        ),
    ):
        app.dependency_overrides[get_session] = _simple_session_gen()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                files = {
                    "file": (
                        "syn.csv",
                        "canonical_term,synonyms\n새대표,동의1|동의2\n".encode("utf-8"),
                        "text/csv",
                    )
                }
                res = await client.post(
                    "/api/v1/admin/rag/synonyms/import?dry_run=true",
                    files=files,
                    cookies={"denvia_admin_session": token},
                )
        finally:
            app.dependency_overrides.pop(get_session, None)

    assert res.status_code == 200
    body = res.json()
    assert body["summary"]["to_create"] == 1
    assert body["summary"]["conflicts"] == 0


@pytest.mark.asyncio
async def test_import_csv_apply_with_conflicts_returns_409():
    token, uid = _make_jwt("admin")
    admin = _admin_user_mock(uid)

    from fastapi import HTTPException

    with (
        patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
        patch(
            "api.src.services.synonym_service.import_csv",
            new=AsyncMock(
                side_effect=HTTPException(
                    status_code=409,
                    detail={
                        "code": "IMPORT_HAS_CONFLICTS",
                        "message": "CSV에 충돌이 있습니다.",
                        "summary": {
                            "to_create": 0,
                            "to_update": 0,
                            "conflicts": 1,
                            "invalid": 0,
                            "unchanged": 0,
                        },
                        "conflicts": [
                            {"row": 2, "canonical_term": "광중합기", "reason": "이미 존재"}
                        ],
                    },
                )
            ),
        ),
        patch(
            "api.src.middleware.audit.async_session_factory",
            side_effect=lambda: _make_audit_ctx(),
        ),
    ):
        app.dependency_overrides[get_session] = _simple_session_gen()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                files = {
                    "file": (
                        "syn.csv",
                        "canonical_term,synonyms\n광중합기,큐링기\n".encode("utf-8"),
                        "text/csv",
                    )
                }
                res = await client.post(
                    "/api/v1/admin/rag/synonyms/import?dry_run=false",
                    files=files,
                    cookies={"denvia_admin_session": token},
                )
        finally:
            app.dependency_overrides.pop(get_session, None)

    assert res.status_code == 409
    body = res.json()
    assert body["code"] == "IMPORT_HAS_CONFLICTS"


@pytest.mark.asyncio
async def test_synonyms_route_unauth_returns_401():
    """비로그인 호출 → 401."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/admin/rag/synonyms")
    assert res.status_code == 401
