"""Admin RAG 프롬프트 블록 편집 통합 테스트 — Story 8.4 (AC-2, AC-3)."""

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


# ──────────────────────────────────────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────────────────────────────────────

_next_user_id = 8400


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
    token = pyjwt.encode(payload, settings.denvia_jwt_secret, algorithm=settings.denvia_jwt_algorithm)
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


# ──────────────────────────────────────────────────────────────────────────────
# 테스트
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_prompts_returns_5_blocks():
    """GET /admin/rag/prompts → 200 + 5개 blocks."""
    token, uid = _make_jwt("admin")
    admin = _admin_user_mock(uid)

    from api.src.schemas.admin.prompts import PromptBlockResponse, PromptsListResponse

    blocks = [
        PromptBlockResponse(
            block_id=bid,
            trigger_keywords=[],
            content=f"{bid} 내용",
            enabled=True,
            updated_at=datetime(2026, 4, 28, tzinfo=timezone.utc),
        )
        for bid in ["BASE", "치식_위치", "치면_방향", "마취_산정", "브릿지"]
    ]
    expected_response = PromptsListResponse(blocks=blocks)

    with (
        patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
        patch(
            "api.src.services.prompt_config_service.get_prompts",
            new=AsyncMock(return_value=expected_response),
        ),
        patch("api.src.middleware.audit.async_session_factory", side_effect=lambda: _make_audit_ctx()),
    ):
        app.dependency_overrides[get_session] = _simple_session_gen()
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get(
                    "/api/v1/admin/rag/prompts",
                    cookies={"denvia_admin_session": token},
                )
        finally:
            app.dependency_overrides.pop(get_session, None)

    assert res.status_code == 200
    data = res.json()
    assert "blocks" in data
    assert len(data["blocks"]) == 5


@pytest.mark.asyncio
async def test_get_prompts_non_admin_403():
    """GET /admin/rag/prompts (user JWT) → 401."""
    token, uid = _make_jwt("user")
    user = _normal_user_mock(uid)

    with (
        patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)),
    ):
        app.dependency_overrides[get_session] = _simple_session_gen()
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get(
                    "/api/v1/admin/rag/prompts",
                    cookies={"denvia_admin_session": token},
                )
        finally:
            app.dependency_overrides.pop(get_session, None)

    assert res.status_code == 401


@pytest.mark.asyncio
async def test_put_prompt_base_success():
    """PUT /admin/rag/prompts/BASE → 200 + 업데이트된 응답."""
    token, uid = _make_jwt("admin")
    admin = _admin_user_mock(uid)

    from api.src.schemas.admin.prompts import PromptUpdateResponse

    expected_response = PromptUpdateResponse(
        block_id="BASE",
        content="새 내용",
        enabled=True,
        updated_at=datetime(2026, 4, 28, tzinfo=timezone.utc),
    )

    with (
        patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
        patch(
            "api.src.services.prompt_config_service.update_prompt",
            new=AsyncMock(return_value=expected_response),
        ),
        patch("api.src.middleware.audit.async_session_factory", side_effect=lambda: _make_audit_ctx()),
    ):
        app.dependency_overrides[get_session] = _simple_session_gen()
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.put(
                    "/api/v1/admin/rag/prompts/BASE",
                    json={"content": "새 내용", "enabled": True},
                    cookies={"denvia_admin_session": token},
                )
        finally:
            app.dependency_overrides.pop(get_session, None)

    assert res.status_code == 200
    data = res.json()
    assert data["block_id"] == "BASE"
    assert data["content"] == "새 내용"


@pytest.mark.asyncio
async def test_put_prompt_not_found_422():
    """PUT /admin/rag/prompts/없음 → 422 PROMPT_BLOCK_NOT_FOUND."""
    token, uid = _make_jwt("admin")
    admin = _admin_user_mock(uid)

    from fastapi import HTTPException

    with (
        patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
        patch(
            "api.src.services.prompt_config_service.update_prompt",
            new=AsyncMock(
                side_effect=HTTPException(
                    status_code=422,
                    detail={"code": "PROMPT_BLOCK_NOT_FOUND"},
                )
            ),
        ),
        patch("api.src.middleware.audit.async_session_factory", side_effect=lambda: _make_audit_ctx()),
    ):
        app.dependency_overrides[get_session] = _simple_session_gen()
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.put(
                    "/api/v1/admin/rag/prompts/없음",
                    json={"content": "내용", "enabled": True},
                    cookies={"denvia_admin_session": token},
                )
        finally:
            app.dependency_overrides.pop(get_session, None)

    assert res.status_code == 422
    assert res.json()["code"] == "PROMPT_BLOCK_NOT_FOUND"


@pytest.mark.asyncio
async def test_put_prompt_empty_content_422():
    """PUT /admin/rag/prompts/BASE {"content": ""} → 422 (Pydantic min_length)."""
    token, uid = _make_jwt("admin")
    admin = _admin_user_mock(uid)

    with (
        patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
        patch("api.src.middleware.audit.async_session_factory", side_effect=lambda: _make_audit_ctx()),
    ):
        app.dependency_overrides[get_session] = _simple_session_gen()
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.put(
                    "/api/v1/admin/rag/prompts/BASE",
                    json={"content": "", "enabled": True},
                    cookies={"denvia_admin_session": token},
                )
        finally:
            app.dependency_overrides.pop(get_session, None)

    assert res.status_code == 422


@pytest.mark.asyncio
async def test_put_prompt_non_admin_403():
    """PUT /admin/rag/prompts/BASE (user JWT) → 401."""
    token, uid = _make_jwt("user")
    user = _normal_user_mock(uid)

    with (
        patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)),
    ):
        app.dependency_overrides[get_session] = _simple_session_gen()
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.put(
                    "/api/v1/admin/rag/prompts/BASE",
                    json={"content": "내용", "enabled": True},
                    cookies={"denvia_admin_session": token},
                )
        finally:
            app.dependency_overrides.pop(get_session, None)

    assert res.status_code == 401
