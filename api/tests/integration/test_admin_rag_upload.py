"""Admin RAG 지식 업로드 통합 테스트 — Story 8.1 (AC-3 ~ AC-10)."""

from __future__ import annotations

import hashlib
import io
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest
from httpx import ASGITransport, AsyncClient

from api.src.main import app
from api.src.models.base import get_session
from api.src.models.knowledge_upload import KnowledgeUpload, STATUS_VALIDATED
from api.src.settings import settings


# ──────────────────────────────────────────────────────────────────────────────
# 픽스처 헬퍼
# ──────────────────────────────────────────────────────────────────────────────

_next_user_id = 1000  # 각 테스트마다 다른 user_id 사용 → rate limit 키 충돌 방지


def _make_jwt(role: str = "admin", sub_status: str = "free") -> tuple[str, int]:
    """(token, user_id) 쌍 반환 — user_id가 rate limit 키."""
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
            "sub_status": sub_status,
            "exp": int(time.time()) + 3600,
        }
    token = pyjwt.encode(payload, settings.denvia_jwt_secret, algorithm=settings.denvia_jwt_algorithm)
    return token, uid


def _admin_user_mock(user_id: int = 99):
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


def _normal_user_mock(user_id: int = 1):
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


VALID_TXT = "{보철}\n=크라운=\n크라운은 치아를 덮는 보철물이다.\n=브릿지=\n결손 치아 양옆 치아를 지대치로 활용.\n".encode("utf-8")


def _make_upload_db_session(
    existing_upload: KnowledgeUpload | None = None,
):
    """업로드 엔드포인트용 DB 세션 mock.

    호출 순서: (1) dup_check scalar_one_or_none, (2) flush, (3) commit
    """
    scalar_result_dup = MagicMock()
    scalar_result_dup.scalar_one_or_none.return_value = existing_upload

    session = MagicMock()
    session.execute = AsyncMock(return_value=scalar_result_dup)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    async def _gen():
        yield session

    return _gen, session


def _make_list_db_session(total: int = 0, items: list = ()):
    """목록 조회 엔드포인트용 DB 세션 mock.

    호출 순서: (1) count scalar_one, (2) items scalars().all()
    """
    call_count = 0

    scalar_count = MagicMock()
    scalar_count.scalar_one.return_value = total

    scalar_items = MagicMock()
    scalar_items.scalars.return_value.all.return_value = list(items)

    async def _execute(q):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return scalar_count
        return scalar_items

    session = MagicMock()
    session.execute = AsyncMock(side_effect=_execute)

    async def _gen():
        yield session

    return _gen, session


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


def _assert_no_audit(audit_logs: list) -> None:
    from api.src.models.audit_log import AuditLog
    audit_entries = [obj for obj in audit_logs if isinstance(obj, AuditLog)]
    assert len(audit_entries) == 0, f"4xx 응답임에도 audit_log INSERT 발생: {audit_entries}"


# ──────────────────────────────────────────────────────────────────────────────
# 업로드 성공 경로 (AC-6)
# ──────────────────────────────────────────────────────────────────────────────

class TestUploadHappyPath:
    async def test_201_성공_응답(self, tmp_path: Path):
        token, uid = _make_jwt()
        admin = _admin_user_mock(uid)
        db_gen, session = _make_upload_db_session()
        audit_logs: list = []

        original_add = session.add

        def _add(obj):
            if isinstance(obj, KnowledgeUpload):
                obj.id = 123
            original_add(obj)

        session.add = _add

        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
            patch("api.src.services.rag_admin_service.UPLOAD_DIR", tmp_path),
            patch("api.src.middleware.audit.async_session_factory", side_effect=lambda: _make_audit_ctx(audit_logs)),
        ):
            app.dependency_overrides[get_session] = db_gen
            try:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.post(
                        "/api/v1/admin/rag/knowledge/upload",
                        cookies={"denvia_admin_session": token},
                        files={"file": ("치과지식.txt", io.BytesIO(VALID_TXT), "text/plain")},
                    )
            finally:
                app.dependency_overrides.pop(get_session, None)

        assert res.status_code == 201
        body = res.json()
        assert body["chunk_count"] == 2
        assert body["category_count"] == 1
        assert len(body["hierarchy_preview"]) == 1
        assert body["hierarchy_preview"][0]["major"] == "보철"  # 보철
        assert body["filename"] == "치과지식.txt"  # 치과지식.txt

    async def test_DB_행_INSERT_확인(self, tmp_path: Path):
        token, uid = _make_jwt()
        admin = _admin_user_mock(uid)
        db_gen, session = _make_upload_db_session()
        captured: list = []

        original_add = session.add

        def _add(obj):
            if isinstance(obj, KnowledgeUpload):
                obj.id = 1
            captured.append(obj)
            original_add(obj)

        session.add = _add

        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
            patch("api.src.services.rag_admin_service.UPLOAD_DIR", tmp_path),
            patch("api.src.middleware.audit.async_session_factory", side_effect=lambda: _make_audit_ctx([])),
        ):
            app.dependency_overrides[get_session] = db_gen
            try:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    await client.post(
                        "/api/v1/admin/rag/knowledge/upload",
                        cookies={"denvia_admin_session": token},
                        files={"file": ("test.txt", io.BytesIO(VALID_TXT), "text/plain")},
                    )
            finally:
                app.dependency_overrides.pop(get_session, None)

        knowledge_rows = [obj for obj in captured if isinstance(obj, KnowledgeUpload)]
        assert len(knowledge_rows) == 1
        assert knowledge_rows[0].status == STATUS_VALIDATED
        assert knowledge_rows[0].chunk_count == 2

    async def test_감사로그_INSERT_확인(self, tmp_path: Path):
        token, uid = _make_jwt()
        admin = _admin_user_mock(uid)
        db_gen, session = _make_upload_db_session()
        audit_logs: list = []

        original_add = session.add

        def _add(obj):
            if isinstance(obj, KnowledgeUpload):
                obj.id = 55
            original_add(obj)

        session.add = _add

        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
            patch("api.src.services.rag_admin_service.UPLOAD_DIR", tmp_path),
            patch("api.src.middleware.audit.async_session_factory", side_effect=lambda: _make_audit_ctx(audit_logs)),
        ):
            app.dependency_overrides[get_session] = db_gen
            try:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    await client.post(
                        "/api/v1/admin/rag/knowledge/upload",
                        cookies={"denvia_admin_session": token},
                        files={"file": ("test.txt", io.BytesIO(VALID_TXT), "text/plain")},
                    )
            finally:
                app.dependency_overrides.pop(get_session, None)

        from api.src.models.audit_log import AuditLog
        audit_entries = [obj for obj in audit_logs if isinstance(obj, AuditLog)]
        assert len(audit_entries) == 1
        entry = audit_entries[0]
        assert entry.action == "rag.upload"
        assert entry.target_type == "knowledge_upload"
        assert entry.target_id == 55
        assert entry.diff_json is not None
        assert "chunk_count" in entry.diff_json


# ──────────────────────────────────────────────────────────────────────────────
# 1차 검증 실패 (AC-3)
# ──────────────────────────────────────────────────────────────────────────────

class TestUploadValidationFailures:
    async def _upload(self, content: bytes, filename: str = "test.txt", content_type: str = "text/plain"):
        token, uid = _make_jwt()
        admin = _admin_user_mock(uid)
        db_gen, _ = _make_upload_db_session()
        audit_logs: list = []

        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
            patch("api.src.middleware.audit.async_session_factory", side_effect=lambda: _make_audit_ctx(audit_logs)),
        ):
            app.dependency_overrides[get_session] = db_gen
            try:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.post(
                        "/api/v1/admin/rag/knowledge/upload",
                        cookies={"denvia_admin_session": token},
                        files={"file": (filename, io.BytesIO(content), content_type)},
                    )
            finally:
                app.dependency_overrides.pop(get_session, None)

        return res, audit_logs

    async def test_11MB_파일_422(self):
        big = b"a" * (11 * 1024 * 1024)
        res, audit_logs = await self._upload(big)

        assert res.status_code == 422
        assert res.json()["code"] == "UPLOAD_TOO_LARGE"
        _assert_no_audit(audit_logs)

    async def test_pdf_mime_422(self):
        res, audit_logs = await self._upload(b"fake pdf", content_type="application/pdf")

        assert res.status_code == 422
        assert res.json()["code"] == "UPLOAD_MIME_INVALID"
        _assert_no_audit(audit_logs)

    async def test_docx_확장자_422(self):
        res, audit_logs = await self._upload(b"docx content", filename="doc.docx")

        assert res.status_code == 422
        assert res.json()["code"] == "UPLOAD_EXT_INVALID"
        _assert_no_audit(audit_logs)

    async def test_cp949_인코딩_422(self):
        cp949_bytes = "한글CP949".encode("cp949")  # 한글CP949
        res, audit_logs = await self._upload(cp949_bytes)

        assert res.status_code == 422
        assert res.json()["code"] == "UPLOAD_ENCODING_INVALID"
        _assert_no_audit(audit_logs)

    async def test_비관리자_403(self):
        token, uid = _make_jwt(role="user")
        user = _normal_user_mock(uid)

        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post(
                    "/api/v1/admin/rag/knowledge/upload",
                    cookies={"denvia_admin_session": token},
                    files={"file": ("test.txt", io.BytesIO(VALID_TXT), "text/plain")},
                )

        assert res.status_code == 401
        assert res.json()["code"] == "ADMIN_AUTH_REQUIRED"


# ──────────────────────────────────────────────────────────────────────────────
# dry-run 실패 (AC-4)
# ──────────────────────────────────────────────────────────────────────────────

class TestUploadDryRunFailure:
    async def test_헤더_없는_파일_422(self, tmp_path: Path):
        token, uid = _make_jwt()
        admin = _admin_user_mock(uid)
        db_gen, _ = _make_upload_db_session()
        audit_logs: list = []
        no_header_content = "This is plain text without any category headers.\n".encode("utf-8")

        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
            patch("api.src.services.rag_admin_service.UPLOAD_DIR", tmp_path),
            patch("api.src.middleware.audit.async_session_factory", side_effect=lambda: _make_audit_ctx(audit_logs)),
        ):
            app.dependency_overrides[get_session] = db_gen
            try:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.post(
                        "/api/v1/admin/rag/knowledge/upload",
                        cookies={"denvia_admin_session": token},
                        files={"file": ("noheader.txt", io.BytesIO(no_header_content), "text/plain")},
                    )
            finally:
                app.dependency_overrides.pop(get_session, None)

        assert res.status_code == 422
        body = res.json()
        assert body["code"] == "UPLOAD_FORMAT_UNPARSEABLE"
        assert "reason" in body.get("details", {})
        _assert_no_audit(audit_logs)


# ──────────────────────────────────────────────────────────────────────────────
# 중복 검출 (AC-7)
# ──────────────────────────────────────────────────────────────────────────────

class TestUploadDuplicate:
    async def test_동일_해시_409(self, tmp_path: Path):
        token, uid = _make_jwt()
        admin = _admin_user_mock(uid)
        audit_logs: list = []

        existing = MagicMock(spec=KnowledgeUpload)
        existing.id = 99
        existing.filename = "existing.txt"
        existing.deleted_at = None

        db_gen, _ = _make_upload_db_session(existing_upload=existing)

        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)),
            patch("api.src.services.rag_admin_service.UPLOAD_DIR", tmp_path),
            patch("api.src.middleware.audit.async_session_factory", side_effect=lambda: _make_audit_ctx(audit_logs)),
        ):
            app.dependency_overrides[get_session] = db_gen
            try:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.post(
                        "/api/v1/admin/rag/knowledge/upload",
                        cookies={"denvia_admin_session": token},
                        files={"file": ("duplicate.txt", io.BytesIO(VALID_TXT), "text/plain")},
                    )
            finally:
                app.dependency_overrides.pop(get_session, None)

        assert res.status_code == 409
        body = res.json()
        assert body["code"] == "UPLOAD_DUPLICATE"
        assert body["details"]["existing_upload_id"] == 99
        assert body["details"]["existing_filename"] == "existing.txt"
        _assert_no_audit(audit_logs)


# ──────────────────────────────────────────────────────────────────────────────
# 목록 조회 (AC-10)
# ──────────────────────────────────────────────────────────────────────────────

class TestKnowledgeListEndpoint:
    async def _get_list(self, token: str, uid: int, page: int = 1, per_page: int = 20, items=(), total: int = 0):
        admin = _admin_user_mock(uid)
        db_gen, _ = _make_list_db_session(total=total, items=items)

        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=admin)):
            app.dependency_overrides[get_session] = db_gen
            try:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.get(
                        f"/api/v1/admin/rag/knowledge?page={page}&per_page={per_page}",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.pop(get_session, None)

        return res

    async def test_빈_목록_200(self):
        token, uid = _make_jwt()
        res = await self._get_list(token, uid, total=0)

        assert res.status_code == 200
        body = res.json()
        assert body["items"] == []
        assert body["total"] == 0
        assert body["page"] == 1

    async def test_비관리자_403(self):
        token, uid = _make_jwt(role="user")
        user = _normal_user_mock(uid)

        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get(
                    "/api/v1/admin/rag/knowledge",
                    cookies={"denvia_admin_session": token},
                )

        assert res.status_code == 401

    async def test_pagination_필드_존재(self):
        token, uid = _make_jwt()
        res = await self._get_list(token, uid, page=2, per_page=5, total=25)

        assert res.status_code == 200
        body = res.json()
        assert body["page"] == 2
        assert body["per_page"] == 5
        assert body["total"] == 25
