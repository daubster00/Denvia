"""rag_admin_service 단위 테스트 — Story 8.2 (edit/delete/status)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.src.models.knowledge_upload import (
    STATUS_ACTIVE,
    STATUS_DELETED,
    STATUS_REBUILD_PENDING,
    STATUS_VALIDATED,
    KnowledgeUpload,
)
from api.src.rag_integration.indexer import CategoryGroup, ParseResult
from api.src.schemas.admin.rag import KnowledgeEditResponse, RagStatusResponse


# ──────────────────────────────────────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────────────────────────────────────

VALID_CONTENT = "{보철}\n=크라운=\n크라운은 치아를 덮는 보철물이다.\n"
VALID_BYTES = VALID_CONTENT.encode("utf-8")
VALID_HASH = hashlib.sha256(VALID_BYTES).hexdigest()


def _make_upload(
    upload_id: int = 1,
    content: str = VALID_CONTENT,
    status: str = STATUS_VALIDATED,
    deleted: bool = False,
    file_path: Path | None = None,
) -> KnowledgeUpload:
    raw = content.encode("utf-8")
    u = MagicMock(spec=KnowledgeUpload)
    u.id = upload_id
    u.filename = "test.txt"
    u.size_bytes = len(raw)
    u.chunk_count = 1
    u.category_count = 1
    u.content_hash = hashlib.sha256(raw).hexdigest()
    u.status = status
    u.original_path = str(file_path) if file_path else "/tmp/fake.txt"
    u.deleted_at = None if not deleted else MagicMock()
    u.last_modified_at = MagicMock()
    u.hierarchy_json = []
    return u


def _make_request() -> MagicMock:
    req = MagicMock()
    req.state = MagicMock()
    return req


def _make_db(
    get_return=None,
    execute_scalars=None,
) -> MagicMock:
    db = MagicMock()
    db.get = AsyncMock(return_value=get_return)
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    if execute_scalars is not None:
        results = []
        for v in execute_scalars:
            r = MagicMock()
            r.scalar_one_or_none.return_value = v
            results.append(r)
        db.execute = AsyncMock(side_effect=results)
    else:
        r = MagicMock()
        r.scalar_one_or_none.return_value = None
        r.scalar_one.return_value = 0
        db.execute = AsyncMock(return_value=r)

    return db


def _good_parse() -> ParseResult:
    return ParseResult(
        chunks=[],
        hierarchy=[CategoryGroup(major="보철", minors=["크라운"])],
        failure=None,
        chunk_count=1,
        category_count=1,
    )


# ──────────────────────────────────────────────────────────────────────────────
# get_upload
# ──────────────────────────────────────────────────────────────────────────────

class TestGetUpload:
    @pytest.mark.asyncio
    async def test_정상_조회(self):
        from api.src.services.rag_admin_service import get_upload

        upload = _make_upload()
        db = _make_db(get_return=upload)
        result = await get_upload(1, db)
        assert result.id == 1

    @pytest.mark.asyncio
    async def test_없는_id_404(self):
        from fastapi import HTTPException
        from api.src.services.rag_admin_service import get_upload

        db = _make_db(get_return=None)
        with pytest.raises(HTTPException) as exc_info:
            await get_upload(9999, db)
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail["code"] == "KNOWLEDGE_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_소프트삭제된_레코드_404(self):
        from fastapi import HTTPException
        from api.src.services.rag_admin_service import get_upload

        upload = _make_upload(deleted=True)
        db = _make_db(get_return=upload)
        with pytest.raises(HTTPException) as exc_info:
            await get_upload(1, db)
        assert exc_info.value.status_code == 404


# ──────────────────────────────────────────────────────────────────────────────
# edit_upload
# ──────────────────────────────────────────────────────────────────────────────

class TestEditUpload:
    @pytest.mark.asyncio
    async def test_happy_path_200(self, tmp_path: Path):
        from api.src.services.rag_admin_service import edit_upload

        original_file = tmp_path / "1_test.txt"
        original_file.write_bytes(VALID_BYTES)

        upload = _make_upload(file_path=original_file)
        db = _make_db(get_return=upload, execute_scalars=[None])
        req = _make_request()
        admin = MagicMock()

        with patch(
            "api.src.services.rag_admin_service.dry_run_parse",
            return_value=_good_parse(),
        ):
            result = await edit_upload(req, 1, VALID_CONTENT, admin, db)

        assert isinstance(result, KnowledgeEditResponse)
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dry_run_실패_422(self, tmp_path: Path):
        from fastapi import HTTPException
        from api.src.rag_integration.indexer import ParseFailure, ParseResult
        from api.src.services.rag_admin_service import edit_upload

        original_file = tmp_path / "1_test.txt"
        original_file.write_bytes(VALID_BYTES)

        upload = _make_upload(file_path=original_file)
        db = _make_db(get_return=upload)
        req = _make_request()
        admin = MagicMock()

        bad_parse = ParseResult(
            chunks=[],
            hierarchy=[],
            failure=ParseFailure("no_categories", "헤더 없음"),
            chunk_count=0,
            category_count=0,
        )

        with patch(
            "api.src.services.rag_admin_service.dry_run_parse",
            return_value=bad_parse,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await edit_upload(req, 1, "헤더없는내용", admin, db)

        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["code"] == "UPLOAD_FORMAT_UNPARSEABLE"
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_타파일_중복해시_409(self, tmp_path: Path):
        from fastapi import HTTPException
        from api.src.services.rag_admin_service import edit_upload

        original_file = tmp_path / "1_test.txt"
        original_file.write_bytes(VALID_BYTES)

        upload = _make_upload(file_path=original_file)
        # execute 결과: 타 레코드 중복 있음
        other_upload = MagicMock()
        other_upload.id = 99
        other_upload.filename = "other.txt"
        db = _make_db(get_return=upload, execute_scalars=[other_upload])
        req = _make_request()
        admin = MagicMock()

        with patch(
            "api.src.services.rag_admin_service.dry_run_parse",
            return_value=_good_parse(),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await edit_upload(req, 1, VALID_CONTENT, admin, db)

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "UPLOAD_DUPLICATE"

    @pytest.mark.asyncio
    async def test_원본파일_없음_500(self, tmp_path: Path):
        from fastapi import HTTPException
        from api.src.services.rag_admin_service import edit_upload

        nonexistent = tmp_path / "nonexistent.txt"  # 파일 생성 안 함
        upload = _make_upload(file_path=nonexistent)
        db = _make_db(get_return=upload, execute_scalars=[None])
        req = _make_request()
        admin = MagicMock()

        with patch(
            "api.src.services.rag_admin_service.dry_run_parse",
            return_value=_good_parse(),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await edit_upload(req, 1, VALID_CONTENT, admin, db)

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail["code"] == "KNOWLEDGE_FILE_MISSING"
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_자기자신_해시_중복_아님(self, tmp_path: Path):
        """동일 내용 재전송 시 자기 자신을 제외하므로 409 아님."""
        from api.src.services.rag_admin_service import edit_upload

        original_file = tmp_path / "1_test.txt"
        original_file.write_bytes(VALID_BYTES)

        upload = _make_upload(file_path=original_file)
        # execute 결과: None (자기 자신은 WHERE id != upload_id로 제외됨)
        db = _make_db(get_return=upload, execute_scalars=[None])
        req = _make_request()
        admin = MagicMock()

        with patch(
            "api.src.services.rag_admin_service.dry_run_parse",
            return_value=_good_parse(),
        ):
            result = await edit_upload(req, 1, VALID_CONTENT, admin, db)

        assert isinstance(result, KnowledgeEditResponse)


# ──────────────────────────────────────────────────────────────────────────────
# delete_upload
# ──────────────────────────────────────────────────────────────────────────────

class TestDeleteUpload:
    @pytest.mark.asyncio
    async def test_happy_path_소프트삭제(self, tmp_path: Path):
        from api.src.services.rag_admin_service import delete_upload

        original_file = tmp_path / "1_test.txt"
        original_file.write_bytes(VALID_BYTES)

        upload = _make_upload(file_path=original_file)
        db = _make_db(get_return=upload)
        req = _make_request()
        admin = MagicMock()

        await delete_upload(req, 1, admin, db)

        db.commit.assert_awaited_once()
        assert original_file.exists(), "FS 파일은 소프트 삭제에서 보존되어야 한다"

    @pytest.mark.asyncio
    async def test_validated_삭제_STATUS_DELETED_전환(self):
        """validated 파일 삭제 → STATUS_DELETED (인덱스 반영 전, pending 취소)."""
        from api.src.services.rag_admin_service import delete_upload

        upload = _make_upload(status=STATUS_VALIDATED)
        db = _make_db(get_return=upload)
        req = _make_request()
        admin = MagicMock()

        await delete_upload(req, 1, admin, db)

        assert upload.status == STATUS_DELETED

    @pytest.mark.asyncio
    async def test_active_삭제_STATUS_REBUILD_PENDING_전환(self):
        """active 파일 삭제 → STATUS_REBUILD_PENDING (인덱스 반영 완료, 다음 재빌드 제거 필요)."""
        from api.src.services.rag_admin_service import delete_upload

        upload = _make_upload(status=STATUS_ACTIVE)
        db = _make_db(get_return=upload)
        req = _make_request()
        admin = MagicMock()

        await delete_upload(req, 1, admin, db)

        assert upload.status == STATUS_REBUILD_PENDING

    @pytest.mark.asyncio
    async def test_rebuild_pending_파일_409(self):
        """rebuild_pending 파일 재삭제 시도 → 409 (이미 삭제 처리 중)."""
        from fastapi import HTTPException
        from api.src.services.rag_admin_service import delete_upload

        upload = _make_upload(status=STATUS_REBUILD_PENDING)
        db = _make_db(get_return=upload)
        req = _make_request()
        admin = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await delete_upload(req, 1, admin, db)

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "KNOWLEDGE_ALREADY_DELETED"

    @pytest.mark.asyncio
    async def test_이미_삭제된_레코드_409(self):
        from fastapi import HTTPException
        from api.src.services.rag_admin_service import delete_upload

        upload = _make_upload(status=STATUS_DELETED)
        db = _make_db(get_return=upload)
        req = _make_request()
        admin = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await delete_upload(req, 1, admin, db)

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "KNOWLEDGE_ALREADY_DELETED"

    @pytest.mark.asyncio
    async def test_없는_id_404(self):
        from fastapi import HTTPException
        from api.src.services.rag_admin_service import delete_upload

        db = _make_db(get_return=None)
        req = _make_request()
        admin = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await delete_upload(req, 9999, admin, db)

        assert exc_info.value.status_code == 404


# ──────────────────────────────────────────────────────────────────────────────
# get_rag_status
# ──────────────────────────────────────────────────────────────────────────────

class TestGetRagStatus:
    def _make_status_db(self, pending_count: int):
        """get_rag_status 4회 execute 순서에 맞는 mock DB."""
        no_job = MagicMock()
        no_job.scalar_one_or_none.return_value = None

        count_r = MagicMock()
        count_r.scalar_one.return_value = pending_count

        db = MagicMock()
        db.execute = AsyncMock(side_effect=[no_job, no_job, no_job, count_r])
        return db

    @pytest.mark.asyncio
    async def test_validated_deleted_카운트(self):
        from api.src.services.rag_admin_service import get_rag_status

        db = self._make_status_db(pending_count=3)
        result = await get_rag_status(db)

        assert result.pending_changes_count == 3
        assert result.last_rebuild_at is None
        assert result.last_rebuild_status is None

    @pytest.mark.asyncio
    async def test_active_레코드_제외(self):
        """active 상태 레코드는 카운트에서 제외 — SQL WHERE 조건으로 처리."""
        from api.src.services.rag_admin_service import get_rag_status

        db = self._make_status_db(pending_count=0)
        result = await get_rag_status(db)
        assert result.pending_changes_count == 0

    @pytest.mark.asyncio
    async def test_rebuild_pending_카운트_포함(self):
        """rebuild_pending(active→삭제) 파일은 pending count에 포함."""
        from api.src.services.rag_admin_service import get_rag_status

        # rebuild_pending 파일 1건이 pending count에 반영됨
        db = self._make_status_db(pending_count=1)
        result = await get_rag_status(db)
        assert result.pending_changes_count == 1

    @pytest.mark.asyncio
    async def test_validated_plus_rebuild_pending_합산(self):
        """validated 신규 파일 + rebuild_pending 삭제 대기 파일이 합산."""
        from api.src.services.rag_admin_service import get_rag_status

        db = self._make_status_db(pending_count=3)
        result = await get_rag_status(db)
        assert result.pending_changes_count == 3
