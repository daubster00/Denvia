"""Admin RAG 모델 파라미터 통합 테스트 — Story 8.4 (AC-4, AC-5, AC-6)."""

from __future__ import annotations

import time
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
    user.current_session_id = None
    user.admin_grade = "master"
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
    user.current_session_id = None
    user.admin_grade = "master"
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
async def test_get_model_params_returns_all_keys():
    """GET /admin/rag/model-params → 200 + {rag_k, rag_temperature, max_tokens}."""
    token, uid = _make_jwt("admin")
    admin = _admin_user_mock(uid)

    from api.src.schemas.admin.prompts import ModelParamsResponse

    with (
        patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
        patch(
            "api.src.services.prompt_config_service.get_model_params",
            new=AsyncMock(return_value=ModelParamsResponse(rag_k=5, rag_temperature=0.0, max_tokens=1024)),
        ),
        patch("api.src.middleware.audit.async_session_factory", side_effect=lambda: _make_audit_ctx()),
    ):
        app.dependency_overrides[get_session] = _simple_session_gen()
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get(
                    "/api/v1/admin/rag/model-params",
                    cookies={"denvia_admin_session": token},
                )
        finally:
            app.dependency_overrides.pop(get_session, None)

    assert res.status_code == 200
    data = res.json()
    assert data["rag_k"] == 5
    assert "rag_temperature" in data
    assert "max_tokens" in data


@pytest.mark.asyncio
async def test_put_model_params_success():
    """PUT /admin/rag/model-params 정상 → 200."""
    token, uid = _make_jwt("admin")
    admin = _admin_user_mock(uid)

    from api.src.schemas.admin.prompts import ModelParamsResponse

    with (
        patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
        patch(
            "api.src.services.prompt_config_service.update_model_params",
            new=AsyncMock(return_value=ModelParamsResponse(rag_k=8, rag_temperature=0.3, max_tokens=2048)),
        ),
        patch("api.src.middleware.audit.async_session_factory", side_effect=lambda: _make_audit_ctx()),
    ):
        app.dependency_overrides[get_session] = _simple_session_gen()
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.put(
                    "/api/v1/admin/rag/model-params",
                    json={"rag_k": 8, "rag_temperature": 0.3, "max_tokens": 2048},
                    cookies={"denvia_admin_session": token},
                )
        finally:
            app.dependency_overrides.pop(get_session, None)

    assert res.status_code == 200
    data = res.json()
    assert data["rag_k"] == 8
    assert data["max_tokens"] == 2048


@pytest.mark.asyncio
async def test_put_model_params_k_too_large_422():
    """PUT {rag_k:25} → 422 MODEL_PARAM_OUT_OF_RANGE."""
    token, uid = _make_jwt("admin")
    admin = _admin_user_mock(uid)

    from fastapi import HTTPException

    with (
        patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
        patch(
            "api.src.services.prompt_config_service.update_model_params",
            new=AsyncMock(
                side_effect=HTTPException(
                    status_code=422,
                    detail={
                        "code": "MODEL_PARAM_OUT_OF_RANGE",
                        "errors": [{"field": "rag_k", "min": 1, "max": 20, "received": 25}],
                    },
                )
            ),
        ),
        patch("api.src.middleware.audit.async_session_factory", side_effect=lambda: _make_audit_ctx()),
    ):
        app.dependency_overrides[get_session] = _simple_session_gen()
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.put(
                    "/api/v1/admin/rag/model-params",
                    json={"rag_k": 25, "rag_temperature": 0.3, "max_tokens": 1024},
                    cookies={"denvia_admin_session": token},
                )
        finally:
            app.dependency_overrides.pop(get_session, None)

    assert res.status_code == 422
    assert res.json()["code"] == "MODEL_PARAM_OUT_OF_RANGE"


@pytest.mark.asyncio
async def test_put_model_params_temperature_too_high_422():
    """PUT {rag_temperature:1.5} → 422."""
    token, uid = _make_jwt("admin")
    admin = _admin_user_mock(uid)

    from fastapi import HTTPException

    with (
        patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
        patch(
            "api.src.services.prompt_config_service.update_model_params",
            new=AsyncMock(
                side_effect=HTTPException(
                    status_code=422,
                    detail={"code": "MODEL_PARAM_OUT_OF_RANGE", "errors": [{"field": "rag_temperature"}]},
                )
            ),
        ),
        patch("api.src.middleware.audit.async_session_factory", side_effect=lambda: _make_audit_ctx()),
    ):
        app.dependency_overrides[get_session] = _simple_session_gen()
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.put(
                    "/api/v1/admin/rag/model-params",
                    json={"rag_k": 5, "rag_temperature": 1.5, "max_tokens": 1024},
                    cookies={"denvia_admin_session": token},
                )
        finally:
            app.dependency_overrides.pop(get_session, None)

    assert res.status_code == 422
    assert res.json()["code"] == "MODEL_PARAM_OUT_OF_RANGE"


@pytest.mark.asyncio
async def test_put_model_params_max_tokens_too_small_422():
    """PUT {max_tokens:100} → 422."""
    token, uid = _make_jwt("admin")
    admin = _admin_user_mock(uid)

    from fastapi import HTTPException

    with (
        patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
        patch(
            "api.src.services.prompt_config_service.update_model_params",
            new=AsyncMock(
                side_effect=HTTPException(
                    status_code=422,
                    detail={"code": "MODEL_PARAM_OUT_OF_RANGE", "errors": [{"field": "max_tokens"}]},
                )
            ),
        ),
        patch("api.src.middleware.audit.async_session_factory", side_effect=lambda: _make_audit_ctx()),
    ):
        app.dependency_overrides[get_session] = _simple_session_gen()
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.put(
                    "/api/v1/admin/rag/model-params",
                    json={"rag_k": 5, "rag_temperature": 0.3, "max_tokens": 100},
                    cookies={"denvia_admin_session": token},
                )
        finally:
            app.dependency_overrides.pop(get_session, None)

    assert res.status_code == 422
    assert res.json()["code"] == "MODEL_PARAM_OUT_OF_RANGE"


@pytest.mark.asyncio
async def test_put_model_params_non_admin_403():
    """PUT /admin/rag/model-params (user JWT) → 401."""
    token, uid = _make_jwt("user")
    user = _normal_user_mock(uid)

    with (
        patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)),
    ):
        app.dependency_overrides[get_session] = _simple_session_gen()
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.put(
                    "/api/v1/admin/rag/model-params",
                    json={"rag_k": 5, "rag_temperature": 0.3, "max_tokens": 1024},
                    cookies={"denvia_admin_session": token},
                )
        finally:
            app.dependency_overrides.pop(get_session, None)

    assert res.status_code == 401


@pytest.mark.asyncio
async def test_get_model_params_non_admin_403():
    """GET /admin/rag/model-params (user JWT) → 401."""
    token, uid = _make_jwt("user")
    user = _normal_user_mock(uid)

    with (
        patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)),
    ):
        app.dependency_overrides[get_session] = _simple_session_gen()
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get(
                    "/api/v1/admin/rag/model-params",
                    cookies={"denvia_admin_session": token},
                )
        finally:
            app.dependency_overrides.pop(get_session, None)

    assert res.status_code == 401
