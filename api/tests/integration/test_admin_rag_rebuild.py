"""Admin RAG 재빌드 통합 테스트 — Story 8.3."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest
from httpx import ASGITransport, AsyncClient

from api.src.main import app
from api.src.models.base import get_session
from api.src.models.rebuild_job import (
    ACTIVE_STATUSES,
    RebuildJob,
    STATUS_CANCELED,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_SUCCESS,
)
from api.src.settings import settings


# ──────────────────────────────────────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────────────────────────────────────

_next_user_id = 3000


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


def _make_rebuild_job(
    job_id: int,
    admin_id: int,
    status: str = STATUS_QUEUED,
    celery_task_id: str = "celery-task-abc",
    target_slot: str = "b",
) -> RebuildJob:
    from datetime import datetime, timezone

    job = RebuildJob(
        id=job_id,
        triggered_by_admin_id=admin_id,
        celery_task_id=celery_task_id,
        status=status,
        progress_percent=0,
        target_slot=target_slot,
        created_at=datetime.now(tz=timezone.utc),
    )
    return job


def _make_audit_noop():
    """audit middleware DB 호출을 no-op으로 대체."""
    class FakeCtx:
        async def __aenter__(self):
            s = MagicMock()
            s.add = MagicMock()
            s.commit = AsyncMock()
            return s

        async def __aexit__(self, *a):
            pass

    return FakeCtx()


def _session_override(mock_db):
    """async generator function을 반환 — FastAPI가 generator dep로 인식하도록."""
    async def _gen():
        yield mock_db
    return _gen


# ──────────────────────────────────────────────────────────────────────────────
# 테스트 — POST /rebuild
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_trigger_rebuild_happy():
    """POST /rebuild → 202 + job_id + target_slot."""
    token, uid = _make_jwt("admin")
    admin = _admin_user_mock(uid)

    mock_result = MagicMock()
    mock_result.job_id = 1
    mock_result.target_slot = "b"

    mock_db = AsyncMock()

    with (
        patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
        patch(
            "api.src.services.rag_admin_service.trigger_rebuild",
            AsyncMock(return_value=mock_result),
        ),
        patch(
            "api.src.middleware.audit.async_session_factory",
            side_effect=lambda: _make_audit_noop(),
        ),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            app.dependency_overrides[get_session] = _session_override(mock_db)
            try:
                resp = await client.post(
                    "/api/v1/admin/rag/rebuild",
                    cookies={"denvia_admin_session": token},
                )
            finally:
                app.dependency_overrides.clear()

    assert resp.status_code == 202
    body = resp.json()
    assert body["job_id"] == 1
    assert body["target_slot"] == "b"


@pytest.mark.asyncio
async def test_trigger_rebuild_conflict():
    """POST /rebuild — 진행 중 job 있으면 409."""
    token, uid = _make_jwt("admin")
    admin = _admin_user_mock(uid)

    existing_job = _make_rebuild_job(job_id=99, admin_id=uid, status="running")

    mock_db = AsyncMock()
    mock_exec_result = MagicMock()
    mock_exec_result.scalar_one_or_none = MagicMock(return_value=existing_job)
    mock_db.execute = AsyncMock(return_value=mock_exec_result)

    with (
        patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
        patch("api.utils.faiss_swap.get_current_slot", return_value="a"),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            app.dependency_overrides[get_session] = _session_override(mock_db)
            try:
                resp = await client.post(
                    "/api/v1/admin/rag/rebuild",
                    cookies={"denvia_admin_session": token},
                )
            finally:
                app.dependency_overrides.clear()

    assert resp.status_code == 409
    body = resp.json()
    assert body["code"] == "REBUILD_ALREADY_IN_PROGRESS"


@pytest.mark.asyncio
async def test_trigger_rebuild_non_admin_403():
    """비관리자가 POST /rebuild → 401."""
    token, uid = _make_jwt("user")
    user = _normal_user_mock(uid)

    with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/admin/rag/rebuild",
                cookies={"denvia_admin_session": token},
            )

    assert resp.status_code == 401


# ──────────────────────────────────────────────────────────────────────────────
# 테스트 — POST /rebuild/{job_id}/cancel
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancel_rebuild_happy():
    """POST /rebuild/{id}/cancel → 200 + status=canceled."""
    token, uid = _make_jwt("admin")
    admin = _admin_user_mock(uid)

    job = _make_rebuild_job(job_id=5, admin_id=uid, status="queued")

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=job)
    mock_db.commit = AsyncMock()

    with (
        patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
        patch("api.src.workers.celery_app.celery_app") as mock_celery_app,
        patch(
            "api.src.middleware.audit.async_session_factory",
            side_effect=lambda: _make_audit_noop(),
        ),
    ):
        mock_celery_app.control.revoke = MagicMock()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            app.dependency_overrides[get_session] = _session_override(mock_db)
            try:
                resp = await client.post(
                    "/api/v1/admin/rag/rebuild/5/cancel",
                    cookies={"denvia_admin_session": token},
                )
            finally:
                app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == STATUS_CANCELED


@pytest.mark.asyncio
async def test_cancel_rebuild_not_found():
    """POST /rebuild/9999/cancel → 404."""
    token, uid = _make_jwt("admin")
    admin = _admin_user_mock(uid)

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=None)

    with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            app.dependency_overrides[get_session] = _session_override(mock_db)
            try:
                resp = await client.post(
                    "/api/v1/admin/rag/rebuild/9999/cancel",
                    cookies={"denvia_admin_session": token},
                )
            finally:
                app.dependency_overrides.clear()

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cancel_rebuild_non_admin_403():
    """비관리자가 POST /rebuild/1/cancel → 401."""
    token, uid = _make_jwt("user")
    user = _normal_user_mock(uid)

    with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/admin/rag/rebuild/1/cancel",
                cookies={"denvia_admin_session": token},
            )

    assert resp.status_code == 401


# ──────────────────────────────────────────────────────────────────────────────
# 테스트 — GET /rebuild/{job_id}
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_rebuild_job_happy():
    """GET /rebuild/{id} → 200 + 전체 필드."""
    from datetime import datetime, timezone

    token, uid = _make_jwt("admin")
    admin = _admin_user_mock(uid)

    job = _make_rebuild_job(job_id=7, admin_id=uid)
    job.stage = "embedding"
    job.started_at = datetime.now(tz=timezone.utc)
    job.finished_at = None
    job.swapped_at = None
    job.chunk_count_after = None
    job.error_message = None

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=job)

    with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            app.dependency_overrides[get_session] = _session_override(mock_db)
            try:
                resp = await client.get(
                    "/api/v1/admin/rag/rebuild/7",
                    cookies={"denvia_admin_session": token},
                )
            finally:
                app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == 7
    assert body["target_slot"] == "b"


# ──────────────────────────────────────────────────────────────────────────────
# 테스트 — GET /status (active_rebuild / last_rebuild 반영)
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rag_status_with_active_rebuild():
    """GET /status → active_rebuild 비 null."""
    from datetime import datetime, timezone

    token, uid = _make_jwt("admin")
    admin = _admin_user_mock(uid)

    active_job = _make_rebuild_job(job_id=10, admin_id=uid, status="running")
    active_job.progress_percent = 45
    active_job.stage = "embedding"
    active_job.created_at = datetime.now(tz=timezone.utc)

    mock_scalar_results = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),   # last_success
        MagicMock(scalar_one_or_none=MagicMock(return_value=active_job)),  # last_job
        MagicMock(scalar_one_or_none=MagicMock(return_value=active_job)),  # active_job
        MagicMock(scalar_one=MagicMock(return_value=3)),               # pending count
    ]
    call_count = [0]

    async def _mock_execute(*args, **kwargs):
        idx = call_count[0]
        call_count[0] += 1
        return mock_scalar_results[idx % len(mock_scalar_results)]

    mock_db = AsyncMock()
    mock_db.execute = _mock_execute

    with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            app.dependency_overrides[get_session] = _session_override(mock_db)
            try:
                resp = await client.get(
                    "/api/v1/admin/rag/status",
                    cookies={"denvia_admin_session": token},
                )
            finally:
                app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["active_rebuild"] is not None
    assert body["active_rebuild"]["job_id"] == 10


@pytest.mark.asyncio
async def test_rag_status_with_last_success():
    """GET /status → last_rebuild_at, last_rebuild_status 반환."""
    from datetime import datetime, timezone

    token, uid = _make_jwt("admin")
    admin = _admin_user_mock(uid)

    swapped_at = datetime(2026, 4, 28, 12, 0, 0, tzinfo=timezone.utc)
    success_job = _make_rebuild_job(job_id=3, admin_id=uid, status=STATUS_SUCCESS)
    success_job.swapped_at = swapped_at
    success_job.created_at = swapped_at

    mock_scalar_results = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=success_job)),  # last_success
        MagicMock(scalar_one_or_none=MagicMock(return_value=success_job)),  # last_job
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),         # active_job
        MagicMock(scalar_one=MagicMock(return_value=0)),                    # pending count
    ]
    call_count = [0]

    async def _mock_execute(*args, **kwargs):
        idx = call_count[0]
        call_count[0] += 1
        return mock_scalar_results[idx % len(mock_scalar_results)]

    mock_db = AsyncMock()
    mock_db.execute = _mock_execute

    with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            app.dependency_overrides[get_session] = _session_override(mock_db)
            try:
                resp = await client.get(
                    "/api/v1/admin/rag/status",
                    cookies={"denvia_admin_session": token},
                )
            finally:
                app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["last_rebuild_status"] == STATUS_SUCCESS
    assert body["last_rebuild_at"] is not None
    assert body["active_rebuild"] is None


# ──────────────────────────────────────────────────────────────────────────────
# 테스트 — cancel_rebuild terminal status 거부
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("terminal_status", [STATUS_SUCCESS, STATUS_FAILED, STATUS_CANCELED])
async def test_cancel_rebuild_terminal_status_409(terminal_status):
    """이미 종료된 job(success/failed/canceled)은 취소 불가 → 409 REBUILD_NOT_CANCELABLE."""
    token, uid = _make_jwt("admin")
    admin = _admin_user_mock(uid)

    job = _make_rebuild_job(job_id=5, admin_id=uid, status=terminal_status)

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=job)

    with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            app.dependency_overrides[get_session] = _session_override(mock_db)
            try:
                resp = await client.post(
                    "/api/v1/admin/rag/rebuild/5/cancel",
                    cookies={"denvia_admin_session": token},
                )
            finally:
                app.dependency_overrides.clear()

    assert resp.status_code == 409
    body = resp.json()
    assert body["code"] == "REBUILD_NOT_CANCELABLE"
    assert body["details"]["current_status"] == terminal_status


# ──────────────────────────────────────────────────────────────────────────────
# 테스트 — trigger_rebuild IntegrityError → 409
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_trigger_rebuild_commit_integrity_error_409():
    """trigger_rebuild: commit 중 IntegrityError(partial unique index race) → 409."""
    from sqlalchemy.exc import IntegrityError as SAIntegrityError
    from fastapi import HTTPException
    from api.src.services.rag_admin_service import trigger_rebuild

    admin = _admin_user_mock(3999)
    request = MagicMock()
    request.state = MagicMock()

    existing_job = MagicMock()
    existing_job.id = 77

    # 첫 번째 execute: active job 없음 (fast-path 통과)
    mock_exec_none = MagicMock()
    mock_exec_none.scalar_one_or_none = MagicMock(return_value=None)
    # 두 번째 execute: rollback 후 active job 조회
    mock_exec_existing = MagicMock()
    mock_exec_existing.scalar_one_or_none = MagicMock(return_value=existing_job)

    _calls = [0]

    async def _execute(*a, **kw):
        n = _calls[0]
        _calls[0] += 1
        return mock_exec_none if n == 0 else mock_exec_existing

    mock_db = AsyncMock()
    mock_db.execute = _execute
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock(side_effect=SAIntegrityError("uq_rebuild_one_active", {}, None))
    mock_db.rollback = AsyncMock()

    mock_status = MagicMock()
    mock_status.pending_changes_count = 1

    with (
        patch("api.utils.faiss_swap.get_current_slot", return_value="a"),
        patch(
            "api.src.services.rag_admin_service.get_rag_status",
            AsyncMock(return_value=mock_status),
        ),
        patch("api.src.settings.settings") as mock_settings,
    ):
        mock_settings.faiss_current_path = "data/faiss/current"
        mock_settings.faiss_index_a_path = "data/faiss/index_a"
        mock_settings.faiss_index_b_path = "data/faiss/index_b"

        with pytest.raises(HTTPException) as exc_info:
            await trigger_rebuild(request, admin, mock_db)

    assert exc_info.value.status_code == 409
    detail = exc_info.value.detail
    assert detail["code"] == "REBUILD_ALREADY_IN_PROGRESS"
    assert detail["active_job_id"] == 77
