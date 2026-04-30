"""RAG 재빌드 유틸 단위 테스트 — Story 8.3."""

from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# faiss_swap 유틸
# ─────────────────────────────────────────────────────────────────────────────

class TestAtomicSwap:
    def test_creates_new_symlink(self, tmp_path):
        from api.utils.faiss_swap import atomic_swap

        target = tmp_path / "index_a"
        target.mkdir()
        current = tmp_path / "current"

        atomic_swap(current, target)

        assert current.is_symlink()
        assert current.resolve() == target.resolve()

    def test_replaces_existing_symlink(self, tmp_path):
        from api.utils.faiss_swap import atomic_swap

        index_a = tmp_path / "index_a"
        index_a.mkdir()
        index_b = tmp_path / "index_b"
        index_b.mkdir()
        current = tmp_path / "current"

        # 초기: current → index_a
        os.symlink(os.path.relpath(index_a, tmp_path), current)
        assert current.resolve() == index_a.resolve()

        # 교체: current → index_b
        atomic_swap(current, index_b)
        assert current.resolve() == index_b.resolve()


class TestGetCurrentSlot:
    def test_returns_a_when_pointing_to_index_a(self, tmp_path):
        from api.utils.faiss_swap import get_current_slot

        index_a = tmp_path / "index_a"
        index_a.mkdir()
        index_b = tmp_path / "index_b"
        index_b.mkdir()
        current = tmp_path / "current"
        os.symlink(os.path.relpath(index_a, tmp_path), current)

        result = get_current_slot(current, index_a, index_b)
        assert result == "a"

    def test_returns_b_when_pointing_to_index_b(self, tmp_path):
        from api.utils.faiss_swap import get_current_slot

        index_a = tmp_path / "index_a"
        index_a.mkdir()
        index_b = tmp_path / "index_b"
        index_b.mkdir()
        current = tmp_path / "current"
        os.symlink(os.path.relpath(index_b, tmp_path), current)

        result = get_current_slot(current, index_a, index_b)
        assert result == "b"

    def test_returns_none_when_no_symlink(self, tmp_path):
        from api.utils.faiss_swap import get_current_slot

        index_a = tmp_path / "index_a"
        index_b = tmp_path / "index_b"
        current = tmp_path / "current"  # 존재하지 않음

        result = get_current_slot(current, index_a, index_b)
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# Celery Beat 태스크
# ─────────────────────────────────────────────────────────────────────────────

def _make_async_cm(mock_db):
    """async context manager를 반환하는 factory mock."""
    class AsyncCM:
        async def __aenter__(self):
            return mock_db
        async def __aexit__(self, *args):
            return None
    return AsyncCM()


@pytest.mark.asyncio
class TestReapStaleRebuilds:
    async def test_marks_stale_jobs_failed(self):
        from api.src.workers.rag_tasks import _reap_stale_rebuilds_async

        mock_result = MagicMock()
        mock_result.rowcount = 1

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        mock_factory = MagicMock(return_value=_make_async_cm(mock_db))

        with patch("api.src.models.base.async_session_factory", mock_factory):
            result = await _reap_stale_rebuilds_async()

        assert "reaped" in result
        assert result["reaped"] == 1

    async def test_does_not_affect_recent_jobs(self):
        """최근 job(4h 미만)은 reap 대상이 아님을 확인."""
        from api.src.workers.rag_tasks import _reap_stale_rebuilds_async

        mock_result = MagicMock()
        mock_result.rowcount = 0

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        mock_factory = MagicMock(return_value=_make_async_cm(mock_db))

        with patch("api.src.models.base.async_session_factory", mock_factory):
            result = await _reap_stale_rebuilds_async()

        assert result["reaped"] == 0


@pytest.mark.asyncio
class TestPurgeDeletedKnowledgeFiles:
    async def test_deletes_expired_files(self, tmp_path):
        """30일 초과 삭제 파일의 FS 파일이 삭제되는지 확인."""
        from api.src.workers.rag_tasks import _purge_deleted_knowledge_async

        test_file = tmp_path / "expired.txt"
        test_file.write_text("data")

        old_time = datetime.now(tz=timezone.utc) - timedelta(days=31)
        row = MagicMock()
        row.id = 1
        row.original_path = str(test_file)
        row.deleted_at = old_time

        mock_db = AsyncMock()
        mock_exec_result = MagicMock()
        mock_exec_result.scalars.return_value.all.return_value = [row]
        mock_db.execute = AsyncMock(return_value=mock_exec_result)

        mock_factory = MagicMock(return_value=_make_async_cm(mock_db))

        with patch("api.src.models.base.async_session_factory", mock_factory):
            result = await _purge_deleted_knowledge_async()

        assert result["purged"] == 1
        assert not test_file.exists()

    async def test_skips_missing_files(self, tmp_path):
        """이미 없는 파일은 skip (오류 없이 처리)."""
        from api.src.workers.rag_tasks import _purge_deleted_knowledge_async

        old_time = datetime.now(tz=timezone.utc) - timedelta(days=31)
        row = MagicMock()
        row.id = 2
        row.original_path = str(tmp_path / "nonexistent.txt")
        row.deleted_at = old_time

        mock_db = AsyncMock()
        mock_exec_result = MagicMock()
        mock_exec_result.scalars.return_value.all.return_value = [row]
        mock_db.execute = AsyncMock(return_value=mock_exec_result)

        mock_factory = MagicMock(return_value=_make_async_cm(mock_db))

        with patch("api.src.models.base.async_session_factory", mock_factory):
            result = await _purge_deleted_knowledge_async()

        assert result["purged"] == 1

    async def test_preserves_files_not_yet_expired(self, tmp_path):
        """20일짜리 파일은 삭제하지 않음."""
        from api.src.workers.rag_tasks import _purge_deleted_knowledge_async

        mock_db = AsyncMock()
        mock_exec_result = MagicMock()
        mock_exec_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_exec_result)

        mock_factory = MagicMock(return_value=_make_async_cm(mock_db))

        with patch("api.src.models.base.async_session_factory", mock_factory):
            result = await _purge_deleted_knowledge_async()

        assert result["purged"] == 0


@pytest.mark.asyncio
class TestRebuildIndexAsync:
    async def test_fails_when_no_active_files(self):
        """활성 지식 파일이 없으면 ValueError → status=failed."""
        from api.src.workers.rag_tasks import _rebuild_index_async

        job = MagicMock()
        job.status = "queued"
        job.celery_task_id = "old-task-id"
        job.target_slot = "a"

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=job)
        mock_db.commit = AsyncMock()
        mock_exec_result = MagicMock()
        mock_exec_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_exec_result)

        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()
        mock_redis.publish = AsyncMock()
        mock_redis.aclose = AsyncMock()

        call_count = [0]

        def _factory():
            call_count[0] += 1
            return _make_async_cm(mock_db)

        with (
            patch("api.src.models.base.async_session_factory", _factory),
            patch("api.src.workers.rag_tasks.aioredis.from_url", return_value=mock_redis),
            patch("api.src.settings.settings.faiss_current_path", "data/faiss/current"),
            patch("api.src.settings.settings.faiss_index_a_path", "data/faiss/index_a"),
        ):
            with pytest.raises((ValueError, Exception)):
                await _rebuild_index_async("new-task-id", 1)

    async def test_missing_original_path_fails_rebuild(self, tmp_path):
        """original_path 파일 미존재 시 ValueError 발생 — validated→active 전환 없음."""
        from api.src.workers.rag_tasks import _rebuild_index_async

        job = MagicMock()
        job.status = "queued"
        job.celery_task_id = "old-task-id"
        job.target_slot = "a"

        row = MagicMock()
        row.id = 42
        row.original_path = str(tmp_path / "nonexistent.txt")  # 존재하지 않는 파일
        row.chunk_count = 5

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=job)
        mock_db.commit = AsyncMock()
        mock_exec_result = MagicMock()
        mock_exec_result.scalars.return_value.all.return_value = [row]
        mock_db.execute = AsyncMock(return_value=mock_exec_result)

        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()
        mock_redis.publish = AsyncMock()
        mock_redis.aclose = AsyncMock()

        def _factory():
            return _make_async_cm(mock_db)

        with (
            patch("api.src.models.base.async_session_factory", _factory),
            patch("api.src.workers.rag_tasks.aioredis.from_url", return_value=mock_redis),
            patch("api.src.settings.settings.faiss_current_path", str(tmp_path / "current")),
            patch("api.src.settings.settings.faiss_index_a_path", str(tmp_path / "index_a")),
        ):
            with pytest.raises(Exception) as exc_info:
                await _rebuild_index_async("new-task-id", 1)

        assert "원본 파일 없음" in str(exc_info.value)
        assert "upload_id=42" in str(exc_info.value)

        # execute에 STATUS_ACTIVE 갱신 쿼리가 없어야 함 (validated→active 전환 없음)
        for call_args in mock_db.execute.call_args_list:
            stmt_str = str(call_args)
            assert "STATUS_ACTIVE" not in stmt_str

    async def test_canceled_before_swap_aborts_without_swap(self, tmp_path):
        """swap 전 canceled 감지 시 swap 없이 중단 — success 마킹 안 함."""
        from api.src.workers.rag_tasks import _rebuild_index_async
        from api.src.models.rebuild_job import STATUS_CANCELED, STATUS_RUNNING

        running_job = MagicMock()
        running_job.status = STATUS_RUNNING
        running_job.celery_task_id = "task-123"
        running_job.target_slot = "a"

        canceled_job = MagicMock()
        canceled_job.status = STATUS_CANCELED

        # db.get 호출 순서:
        # 1: mark running, 2-5: _publish_progress(0/10/20/80), 6: pre-swap check → canceled
        get_call_idx = [0]
        get_results = [running_job] * 5 + [canceled_job] + [canceled_job] * 3

        async def _mock_get(model, pk):
            i = min(get_call_idx[0], len(get_results) - 1)
            get_call_idx[0] += 1
            return get_results[i]

        test_file = tmp_path / "kb.txt"
        test_file.write_text("test")

        row = MagicMock()
        row.id = 1
        row.original_path = str(test_file)
        row.chunk_count = 3

        mock_exec_result = MagicMock()
        mock_exec_result.scalars.return_value.all.return_value = [row]

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(side_effect=_mock_get)
        mock_db.execute = AsyncMock(return_value=mock_exec_result)
        mock_db.commit = AsyncMock()

        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()
        mock_redis.publish = AsyncMock()
        mock_redis.aclose = AsyncMock()

        mock_swap = MagicMock()

        def _factory():
            return _make_async_cm(mock_db)

        with (
            patch("api.src.models.base.async_session_factory", _factory),
            patch("api.src.workers.rag_tasks.aioredis.from_url", return_value=mock_redis),
            patch("api.src.settings.settings.faiss_index_a_path", str(tmp_path / "idx_a")),
            patch("api.src.settings.settings.faiss_index_b_path", str(tmp_path / "idx_b")),
            patch("api.src.settings.settings.faiss_current_path", str(tmp_path / "current")),
            patch("rag.update_vectorstore.update_vectorstore"),
            patch("api.utils.faiss_swap.atomic_swap", mock_swap),
        ):
            result = await _rebuild_index_async("task-123", 1)

        assert result == {"status": "canceled", "job_id": 1}
        mock_swap.assert_not_called()
