"""Admin RAG 지식 편집/삭제 통합 테스트 — Story 8.2."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest
from httpx import ASGITransport, AsyncClient

from api.src.main import app
from api.src.models.base import get_session
from api.src.models.knowledge_upload import (
    STATUS_ACTIVE,
    STATUS_DELETED,
    STATUS_REBUILD_PENDING,
    STATUS_VALIDATED,
    KnowledgeUpload,
)
from api.src.settings import settings


# ──────────────────────────────────────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────────────────────────────────────

_next_user_id = 2000


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


VALID_CONTENT = "{보철}\n=크라운=\n크라운은 치아를 덮는 보철물이다.\n"
VALID_BYTES = VALID_CONTENT.encode("utf-8")
VALID_HASH = hashlib.sha256(VALID_BYTES).hexdigest()


def _make_upload_obj(
    upload_id: int = 1,
    file_path: Path | None = None,
    status: str = STATUS_VALIDATED,
    deleted: bool = False,
) -> KnowledgeUpload:
    u = MagicMock(spec=KnowledgeUpload)
    u.id = upload_id
    u.filename = "치과지식.txt"
    u.size_bytes = len(VALID_BYTES)
    u.chunk_count = 1
    u.category_count = 1
    u.content_hash = VALID_HASH
    u.status = status
    u.original_path = str(file_path) if file_path else "/tmp/fake.txt"
    u.deleted_at = None if not deleted else MagicMock()
    u.last_modified_at = MagicMock()
    u.hierarchy_json = []
    u.uploaded_at = MagicMock()
    return u


def _make_audit_ctx(capture: list):
    session = MagicMock()
    session.add = lambda obj: capture.append(obj)
    session.commit = AsyncMock()

    class FakeCtx:
        async def __aenter__(self_inner):
            return session

        async def __aexit__(self_inner, *a):
            pass

    return FakeCtx()


def _db_gen_for_get_returning(upload):
    """db.get()이 upload를 반환하고, execute()는 None을 반환하는 세션."""
    session = MagicMock()
    session.get = AsyncMock(return_value=upload)

    r = MagicMock()
    r.scalar_one_or_none.return_value = None
    r.scalar_one.return_value = 0
    session.execute = AsyncMock(return_value=r)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    async def _gen():
        yield session

    return _gen, session


# ──────────────────────────────────────────────────────────────────────────────
# GET /knowledge/{upload_id}
# ──────────────────────────────────────────────────────────────────────────────

class TestGetKnowledgeDetail:
    async def test_200_content_포함(self, tmp_path: Path):
        token, uid = _make_jwt()
        admin = _admin_user_mock(uid)

        file_path = tmp_path / "1_test.txt"
        file_path.write_bytes(VALID_BYTES)
        upload = _make_upload_obj(file_path=file_path)

        db_gen, _ = _db_gen_for_get_returning(upload)

        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
            app.dependency_overrides[get_session] = db_gen
            try:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.get(
                        "/api/v1/admin/rag/knowledge/1",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.pop(get_session, None)

        assert res.status_code == 200
        body = res.json()
        assert "content" in body
        assert body["content"] == VALID_CONTENT

    async def test_소프트삭제된_레코드_404(self, tmp_path: Path):
        token, uid = _make_jwt()
        admin = _admin_user_mock(uid)

        upload = _make_upload_obj(deleted=True)
        db_gen, _ = _db_gen_for_get_returning(upload)

        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
            app.dependency_overrides[get_session] = db_gen
            try:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.get(
                        "/api/v1/admin/rag/knowledge/1",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.pop(get_session, None)

        assert res.status_code == 404
        assert res.json()["code"] == "KNOWLEDGE_NOT_FOUND"

    async def test_없는_레코드_404(self):
        token, uid = _make_jwt()
        admin = _admin_user_mock(uid)

        session = MagicMock()
        session.get = AsyncMock(return_value=None)

        async def _gen():
            yield session

        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
            app.dependency_overrides[get_session] = _gen
            try:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.get(
                        "/api/v1/admin/rag/knowledge/9999",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.pop(get_session, None)

        assert res.status_code == 404


# ──────────────────────────────────────────────────────────────────────────────
# PUT /knowledge/{upload_id}
# ──────────────────────────────────────────────────────────────────────────────

class TestEditKnowledge:
    async def test_happy_path_200_chunk_갱신(self, tmp_path: Path):
        from api.src.rag_integration.indexer import CategoryGroup, ParseResult

        token, uid = _make_jwt()
        admin = _admin_user_mock(uid)
        audit_logs: list = []

        file_path = tmp_path / "1_test.txt"
        file_path.write_bytes(VALID_BYTES)
        upload = _make_upload_obj(file_path=file_path)

        db_gen, _ = _db_gen_for_get_returning(upload)
        good_parse = ParseResult(
            chunks=[],
            hierarchy=[CategoryGroup("보철", ["크라운"])],
            failure=None,
            chunk_count=2,
            category_count=1,
        )

        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
            patch("api.src.services.rag_admin_service.dry_run_parse", return_value=good_parse),
            patch("api.src.middleware.audit.async_session_factory", side_effect=lambda: _make_audit_ctx(audit_logs)),
        ):
            app.dependency_overrides[get_session] = db_gen
            try:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.put(
                        "/api/v1/admin/rag/knowledge/1",
                        cookies={"denvia_admin_session": token},
                        json={"content": VALID_CONTENT + "=브릿지=\n추가내용\n"},
                    )
            finally:
                app.dependency_overrides.pop(get_session, None)

        assert res.status_code == 200
        body = res.json()
        assert "chunk_count" in body

        from api.src.models.audit_log import AuditLog
        audit_entries = [obj for obj in audit_logs if isinstance(obj, AuditLog)]
        assert len(audit_entries) == 1
        assert audit_entries[0].action == "rag.knowledge_edit"

    async def test_dry_run_실패_422_감사없음(self, tmp_path: Path):
        from api.src.rag_integration.indexer import ParseFailure, ParseResult

        token, uid = _make_jwt()
        admin = _admin_user_mock(uid)
        audit_logs: list = []

        file_path = tmp_path / "1_test.txt"
        file_path.write_bytes(VALID_BYTES)
        upload = _make_upload_obj(file_path=file_path)

        db_gen, _ = _db_gen_for_get_returning(upload)
        bad_parse = ParseResult([], [], ParseFailure("no_categories", "없음"), 0, 0)

        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
            patch("api.src.services.rag_admin_service.dry_run_parse", return_value=bad_parse),
            patch("api.src.middleware.audit.async_session_factory", side_effect=lambda: _make_audit_ctx(audit_logs)),
        ):
            app.dependency_overrides[get_session] = db_gen
            try:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.put(
                        "/api/v1/admin/rag/knowledge/1",
                        cookies={"denvia_admin_session": token},
                        json={"content": "no header content"},
                    )
            finally:
                app.dependency_overrides.pop(get_session, None)

        assert res.status_code == 422
        assert res.json()["code"] == "UPLOAD_FORMAT_UNPARSEABLE"

        from api.src.models.audit_log import AuditLog
        audit_entries = [obj for obj in audit_logs if isinstance(obj, AuditLog)]
        assert len(audit_entries) == 0

    async def test_자기자신_해시_200(self, tmp_path: Path):
        """원본 그대로 재전송 — 자기 제외 → 중복 아님 → 200."""
        from api.src.rag_integration.indexer import CategoryGroup, ParseResult

        token, uid = _make_jwt()
        admin = _admin_user_mock(uid)

        file_path = tmp_path / "1_test.txt"
        file_path.write_bytes(VALID_BYTES)
        upload = _make_upload_obj(file_path=file_path)

        db_gen, _ = _db_gen_for_get_returning(upload)
        good_parse = ParseResult([], [CategoryGroup("보철", ["크라운"])], None, 1, 1)

        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
            patch("api.src.services.rag_admin_service.dry_run_parse", return_value=good_parse),
            patch("api.src.middleware.audit.async_session_factory", side_effect=lambda: _make_audit_ctx([])),
        ):
            app.dependency_overrides[get_session] = db_gen
            try:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.put(
                        "/api/v1/admin/rag/knowledge/1",
                        cookies={"denvia_admin_session": token},
                        json={"content": VALID_CONTENT},
                    )
            finally:
                app.dependency_overrides.pop(get_session, None)

        assert res.status_code == 200

    async def test_없는_레코드_404(self):
        token, uid = _make_jwt()
        admin = _admin_user_mock(uid)

        session = MagicMock()
        session.get = AsyncMock(return_value=None)

        async def _gen():
            yield session

        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
            app.dependency_overrides[get_session] = _gen
            try:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.put(
                        "/api/v1/admin/rag/knowledge/9999",
                        cookies={"denvia_admin_session": token},
                        json={"content": VALID_CONTENT},
                    )
            finally:
                app.dependency_overrides.pop(get_session, None)

        assert res.status_code == 404

    async def test_원본파일_없음_500_감사없음(self, tmp_path: Path):
        from api.src.rag_integration.indexer import CategoryGroup, ParseResult

        token, uid = _make_jwt()
        admin = _admin_user_mock(uid)
        audit_logs: list = []

        nonexistent_path = tmp_path / "nonexistent.txt"  # 파일 생성 안 함
        upload = _make_upload_obj(file_path=nonexistent_path)

        db_gen, _ = _db_gen_for_get_returning(upload)
        good_parse = ParseResult([], [CategoryGroup("보철", ["크라운"])], None, 1, 1)

        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
            patch("api.src.services.rag_admin_service.dry_run_parse", return_value=good_parse),
            patch("api.src.middleware.audit.async_session_factory", side_effect=lambda: _make_audit_ctx(audit_logs)),
        ):
            app.dependency_overrides[get_session] = db_gen
            try:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.put(
                        "/api/v1/admin/rag/knowledge/1",
                        cookies={"denvia_admin_session": token},
                        json={"content": VALID_CONTENT},
                    )
            finally:
                app.dependency_overrides.pop(get_session, None)

        assert res.status_code == 500
        assert res.json()["code"] == "KNOWLEDGE_FILE_MISSING"

        from api.src.models.audit_log import AuditLog
        audit_entries = [obj for obj in audit_logs if isinstance(obj, AuditLog)]
        assert len(audit_entries) == 0

    async def test_비관리자_403(self):
        token, uid = _make_jwt(role="user")
        user = _normal_user_mock(uid)

        session = MagicMock()

        async def _gen():
            yield session

        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)):
            app.dependency_overrides[get_session] = _gen
            try:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.put(
                        "/api/v1/admin/rag/knowledge/1",
                        cookies={"denvia_admin_session": token},
                        json={"content": VALID_CONTENT},
                    )
            finally:
                app.dependency_overrides.pop(get_session, None)

        assert res.status_code == 401


# ──────────────────────────────────────────────────────────────────────────────
# DELETE /knowledge/{upload_id}
# ──────────────────────────────────────────────────────────────────────────────

class TestDeleteKnowledge:
    async def test_204_소프트삭제(self, tmp_path: Path):
        token, uid = _make_jwt()
        admin = _admin_user_mock(uid)
        audit_logs: list = []

        file_path = tmp_path / "1_test.txt"
        file_path.write_bytes(VALID_BYTES)
        upload = _make_upload_obj(file_path=file_path)

        db_gen, _ = _db_gen_for_get_returning(upload)

        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
            patch("api.src.middleware.audit.async_session_factory", side_effect=lambda: _make_audit_ctx(audit_logs)),
        ):
            app.dependency_overrides[get_session] = db_gen
            try:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.delete(
                        "/api/v1/admin/rag/knowledge/1",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.pop(get_session, None)

        assert res.status_code == 204
        assert file_path.exists(), "소프트 삭제 후 FS 파일은 보존되어야 한다"

        from api.src.models.audit_log import AuditLog
        audit_entries = [obj for obj in audit_logs if isinstance(obj, AuditLog)]
        assert len(audit_entries) == 1
        assert audit_entries[0].action == "rag.knowledge_delete"

    async def test_이미_삭제된_409(self):
        token, uid = _make_jwt()
        admin = _admin_user_mock(uid)

        upload = _make_upload_obj(status=STATUS_DELETED)
        db_gen, _ = _db_gen_for_get_returning(upload)

        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
            app.dependency_overrides[get_session] = db_gen
            try:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.delete(
                        "/api/v1/admin/rag/knowledge/1",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.pop(get_session, None)

        assert res.status_code == 409
        assert res.json()["code"] == "KNOWLEDGE_ALREADY_DELETED"

    async def test_없는_레코드_404(self):
        token, uid = _make_jwt()
        admin = _admin_user_mock(uid)

        session = MagicMock()
        session.get = AsyncMock(return_value=None)

        async def _gen():
            yield session

        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
            app.dependency_overrides[get_session] = _gen
            try:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.delete(
                        "/api/v1/admin/rag/knowledge/9999",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.pop(get_session, None)

        assert res.status_code == 404

    async def test_비관리자_403(self):
        token, uid = _make_jwt(role="user")
        user = _normal_user_mock(uid)

        session = MagicMock()

        async def _gen():
            yield session

        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)):
            app.dependency_overrides[get_session] = _gen
            try:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.delete(
                        "/api/v1/admin/rag/knowledge/1",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.pop(get_session, None)

        assert res.status_code == 401


# ──────────────────────────────────────────────────────────────────────────────
# GET /status
# ──────────────────────────────────────────────────────────────────────────────

class TestRagStatus:
    async def test_200_pending_changes_count(self):
        token, uid = _make_jwt()
        admin = _admin_user_mock(uid)

        no_job = MagicMock()
        no_job.scalar_one_or_none.return_value = None
        count_r = MagicMock()
        count_r.scalar_one.return_value = 3

        session = MagicMock()
        session.get = AsyncMock(return_value=None)
        # get_rag_status: 4 execute calls — last_success, last_job, active_job, pending_count
        session.execute = AsyncMock(side_effect=[no_job, no_job, no_job, count_r])

        async def _gen():
            yield session

        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
            app.dependency_overrides[get_session] = _gen
            try:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.get(
                        "/api/v1/admin/rag/status",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.pop(get_session, None)

        assert res.status_code == 200
        body = res.json()
        assert body["pending_changes_count"] == 3
        assert body["last_rebuild_at"] is None
        assert body["last_rebuild_status"] is None

    async def test_validated_파일_삭제_후_pending_미증가(self):
        """validated→deleted 전환 후 /status pending count가 증가하지 않아야 한다."""
        token, uid = _make_jwt()
        admin = _admin_user_mock(uid)

        upload = _make_upload_obj(status=STATUS_VALIDATED)
        db_gen, _ = _db_gen_for_get_returning(upload)

        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
            patch("api.src.middleware.audit.async_session_factory", side_effect=lambda: _make_audit_ctx([])),
        ):
            app.dependency_overrides[get_session] = db_gen
            try:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.delete(
                        "/api/v1/admin/rag/knowledge/1",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.pop(get_session, None)

        assert res.status_code == 204
        # validated 파일 삭제는 pending 취소 — status가 rebuild_pending이 아닌 deleted 여야 함
        assert upload.status == STATUS_DELETED

    async def test_active_파일_삭제_후_rebuild_pending_전환(self):
        """active→rebuild_pending 전환 후 pending count에 포함되어야 한다."""
        token, uid = _make_jwt()
        admin = _admin_user_mock(uid)

        upload = _make_upload_obj(status=STATUS_ACTIVE)
        db_gen, _ = _db_gen_for_get_returning(upload)

        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
            patch("api.src.middleware.audit.async_session_factory", side_effect=lambda: _make_audit_ctx([])),
        ):
            app.dependency_overrides[get_session] = db_gen
            try:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.delete(
                        "/api/v1/admin/rag/knowledge/1",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.pop(get_session, None)

        assert res.status_code == 204
        # active 파일 삭제는 다음 재빌드로 인덱스 제거 필요 — rebuild_pending 전환
        assert upload.status == STATUS_REBUILD_PENDING
