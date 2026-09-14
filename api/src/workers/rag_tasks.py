"""RAG 재빌드 Celery 태스크 — Story 8.3."""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import redis.asyncio as aioredis
import structlog

from api.src.workers.celery_app import celery_app
from api.src.settings import REDIS_DB_CELERY, settings

logger = structlog.get_logger(__name__)


# ─── 헬퍼 ─────────────────────────────────────────────────────────────────────

async def _publish_progress(
    r: aioredis.Redis,
    job_id: int,
    progress: int,
    stage: str,
    **extra,
) -> None:
    from api.src.models.base import async_session_factory
    from api.src.models.rebuild_job import RebuildJob

    async with async_session_factory() as db:
        job = await db.get(RebuildJob, job_id)
        if job:
            job.progress_percent = progress
            job.stage = stage
            await db.commit()

    payload = json.dumps(
        {"type": "rag_rebuild_progress", "job_id": job_id, "progress": progress, "stage": stage, **extra}
    )
    await r.set(f"rag:rebuild:progress:{job_id}", payload, ex=3600)
    await r.publish("admin:events", payload)


async def _send_rebuild_notification(
    job_id: int,
    template_code: str,
    variables: dict[str, str],
) -> None:
    """4.1 NotificationService 어댑터로 운영 관리자에게 알림톡 발송.

    수신자는 트리거 관리자가 아니라 admin_recipient.resolve_admin_target 으로
    DB users.phone 을 본다 (admin@denvia.ai.kr 단일).
    예산·이상탐지·문의 알림과 동일 정책.
    """
    from api.src.integrations.messaging.admin_recipient import resolve_admin_target
    from api.src.integrations.messaging.notification_service import get_notification_service
    from api.src.models.base import async_session_factory

    async with async_session_factory() as db:
        admin, admin_phone = await resolve_admin_target(db)

    if admin is None or not admin_phone:
        logger.info("rag.rebuild.notification_skipped", job_id=job_id, reason="admin_phone_missing")
        return

    service = get_notification_service()
    await service.send(
        user_id=admin.id,
        phone=admin_phone,
        template_code=template_code,
        variables=variables,
        idempotency_key=f"rag_rebuild:{job_id}:{template_code}",
    )


# ─── 재빌드 태스크 ─────────────────────────────────────────────────────────────

@celery_app.task(name="rag.rebuild_index", bind=True)
def rebuild_index_task(self, job_id: int) -> dict:
    return asyncio.run(_rebuild_index_async(self.request.id, job_id))


async def _rebuild_index_async(celery_task_id: str, job_id: int) -> dict:
    from api.src.models.base import async_session_factory
    from api.src.models.knowledge_upload import (
        KnowledgeUpload,
        STATUS_ACTIVE,
        STATUS_DELETED,
        STATUS_REBUILD_PENDING,
        STATUS_VALIDATED,
    )
    from api.src.models.rebuild_job import (
        RebuildJob,
        STATUS_CANCELED,
        STATUS_FAILED,
        STATUS_RUNNING,
        STATUS_SUCCESS,
    )
    from api.utils.faiss_swap import atomic_swap
    from sqlalchemy import select, update as sa_update

    redis_url = f"{settings.redis_url}/{REDIS_DB_CELERY}"
    r = aioredis.from_url(redis_url, decode_responses=True)

    try:
        # Step 1: mark running
        async with async_session_factory() as db:
            job = await db.get(RebuildJob, job_id)
            if job is None:
                logger.error("rag.rebuild.job_not_found", job_id=job_id)
                return {"error": "job_not_found"}
            job.status = STATUS_RUNNING
            job.started_at = datetime.now(tz=timezone.utc)
            if job.celery_task_id != celery_task_id:
                job.celery_task_id = celery_task_id
            await db.commit()
            target_slot = job.target_slot

        target_path = Path(
            settings.faiss_index_a_path if target_slot == "a"
            else settings.faiss_index_b_path
        )

        await _publish_progress(r, job_id, 0, "init")

        # Step 2: target slot 초기화 (이전 partial 정리)
        if target_path.exists():
            shutil.rmtree(target_path)

        # Step 3: 활성 지식 파일 수집
        async with async_session_factory() as db:
            rows = (await db.execute(
                select(KnowledgeUpload).where(KnowledgeUpload.deleted_at.is_(None))
            )).scalars().all()

        if not rows:
            raise ValueError("재빌드할 활성 지식 파일이 없습니다.")

        # 원본 파일 존재 검증 — 하나라도 없으면 즉시 실패
        missing = [
            f"upload_id={r.id} path={str(r.original_path)[:120]}"
            for r in rows
            if not Path(r.original_path).exists()
        ]
        if missing:
            raise ValueError(f"원본 파일 없음: {'; '.join(missing[:5])}")

        await _publish_progress(r, job_id, 10, "parsing")

        tmpdir = Path(tempfile.mkdtemp(prefix="denvia_rebuild_"))
        try:
            for row in rows:
                src = Path(row.original_path)
                shutil.copy2(src, tmpdir / src.name)
        except Exception:
            shutil.rmtree(tmpdir, ignore_errors=True)
            raise

        await _publish_progress(r, job_id, 20, "embedding")

        # Step 3-b: 재구축 비용 측정 (수정요청 게시판 #145)
        # 임베딩 호출은 langchain get_openai_callback 에 잡히지 않아 그동안
        # 재구축 비용이 어디에도 기록되지 않았다. 여기서는 OpenAI 에 추가
        # 요청을 보내지 않고 tiktoken 으로 로컬에서 토큰만 센다.
        # 중요: 측정은 재구축 동작을 1밀리도 바꾸지 않는다. 실패해도
        # 재구축을 막지 않도록 예외를 전부 삼킨다.
        embedding_tokens: int | None = None
        embedding_cost: Decimal | None = None
        try:
            from api.src.services.embedding_cost import (
                EMBEDDING_MODEL,
                count_tokens,
                embedding_cost_usd,
            )
            from rag.update_vectorstore import build_documents

            _docs = build_documents(str(tmpdir))
            embedding_tokens, _is_approx = count_tokens(
                d.page_content for d in _docs
            )
            embedding_cost = embedding_cost_usd(embedding_tokens)
            logger.info(
                "rag.rebuild.embedding_cost_measured",
                job_id=job_id,
                model=EMBEDDING_MODEL,
                document_count=len(_docs),
                embedding_tokens=embedding_tokens,
                embedding_cost_usd=str(embedding_cost),
                approximate=_is_approx,
            )
        except Exception as e:  # 측정 실패 ≠ 재구축 실패
            embedding_tokens = None
            embedding_cost = None
            logger.warning(
                "rag.rebuild.embedding_cost_measure_failed",
                job_id=job_id,
                error=str(e),
            )

        # Step 4: update_vectorstore 호출 (sync — 스레드풀에서 실행)
        from rag.update_vectorstore import update_vectorstore

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, update_vectorstore, str(tmpdir), str(target_path)
            )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        # 임베딩이 실제로 끝났다 = OpenAI 에 과금이 발생했다.
        # 이후 관리자가 취소해도 나간 돈은 나간 것이므로 여기서 바로 기록한다.
        if embedding_tokens is not None:
            try:
                async with async_session_factory() as db:
                    _cost_job = await db.get(RebuildJob, job_id)
                    if _cost_job is not None:
                        _cost_job.embedding_token_count = embedding_tokens
                        _cost_job.embedding_cost_usd = embedding_cost
                        await db.commit()
            except Exception as e:
                logger.warning(
                    "rag.rebuild.embedding_cost_save_failed",
                    job_id=job_id,
                    error=str(e),
                )

        await _publish_progress(r, job_id, 80, "faiss_build")

        # swap 전 취소 확인 — canceled면 swap 없이 중단
        async with async_session_factory() as db:
            _pre_swap_check = await db.get(RebuildJob, job_id)
            if _pre_swap_check is not None and _pre_swap_check.status == STATUS_CANCELED:
                logger.info("rag.rebuild.aborted_before_swap", job_id=job_id)
                return {"status": "canceled", "job_id": job_id}

        # Step 5: atomic swap
        atomic_swap(settings.faiss_current_path, target_path)

        await _publish_progress(r, job_id, 95, "swap")

        # Step 6+7: 취소 재확인 후 상태 전환 + success 마킹 (한 트랜잭션)
        # swap 완료 후에도 canceled 상태면 DB 전환·success 마킹 모두 생략
        now = datetime.now(tz=timezone.utc)
        chunk_total = sum(row.chunk_count or 0 for row in rows)
        async with async_session_factory() as db:
            job = await db.get(RebuildJob, job_id)
            if job is None or job.status == STATUS_CANCELED:
                logger.info("rag.rebuild.canceled_after_swap", job_id=job_id)
                return {"status": "canceled", "job_id": job_id}
            await db.execute(
                sa_update(KnowledgeUpload)
                .where(
                    KnowledgeUpload.deleted_at.is_(None),
                    KnowledgeUpload.status == STATUS_VALIDATED,
                )
                .values(status=STATUS_ACTIVE)
            )
            await db.execute(
                sa_update(KnowledgeUpload)
                .where(KnowledgeUpload.status == STATUS_REBUILD_PENDING)
                .values(status=STATUS_DELETED)
            )
            job.status = STATUS_SUCCESS
            job.swapped_at = now
            job.finished_at = now
            job.chunk_count_after = chunk_total
            await db.commit()

        await _publish_progress(r, job_id, 100, "done", status="success")
        logger.info("rag.rebuild.success", job_id=job_id)

        # Step 8: 알림톡 발송 (4.1 어댑터)
        try:
            await _send_rebuild_notification(
                job_id,
                "system.rag_rebuild_complete",
                {"chunk_count": str(chunk_total)},
            )
        except Exception as e:
            logger.warning("rag.rebuild.alimtalk_failed", error=str(e))

        return {"status": "success", "job_id": job_id}

    except Exception as exc:
        now = datetime.now(tz=timezone.utc)
        error_msg = str(exc)[:500]
        try:
            async with async_session_factory() as db:
                job = await db.get(RebuildJob, job_id)
                if job:
                    job.status = STATUS_FAILED
                    job.finished_at = now
                    job.error_message = error_msg
                    await db.commit()
        except Exception:
            pass

        try:
            await _publish_progress(r, job_id, 0, "failed", status="failed", error=error_msg)
        except Exception:
            pass

        logger.error("rag.rebuild.failed", job_id=job_id, error=error_msg)

        try:
            await _send_rebuild_notification(
                job_id,
                "system.rag_rebuild_failed",
                {"error": error_msg},
            )
        except Exception:
            pass

        raise
    finally:
        await r.aclose()


# ─── Beat 태스크 ───────────────────────────────────────────────────────────────

@celery_app.task(name="rag.reap_stale_rebuilds")
def reap_stale_rebuilds() -> dict:
    return asyncio.run(_reap_stale_rebuilds_async())


async def _reap_stale_rebuilds_async() -> dict:
    from api.src.models.base import async_session_factory
    from api.src.models.rebuild_job import RebuildJob, STATUS_FAILED, STATUS_RUNNING
    from sqlalchemy import update as sa_update

    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=4)
    async with async_session_factory() as db:
        result = await db.execute(
            sa_update(RebuildJob)
            .where(
                RebuildJob.status == STATUS_RUNNING,
                RebuildJob.started_at < cutoff,
            )
            .values(
                status=STATUS_FAILED,
                error_message="worker_timeout_or_crash",
                finished_at=datetime.now(tz=timezone.utc),
            )
        )
        await db.commit()

    reaped = result.rowcount
    logger.info("rag.reap_stale_rebuilds.done", reaped=reaped)
    return {"reaped": reaped}


@celery_app.task(name="rag.purge_deleted_knowledge_files")
def purge_deleted_knowledge_files() -> dict:
    return asyncio.run(_purge_deleted_knowledge_async())


async def _purge_deleted_knowledge_async() -> dict:
    from api.src.models.base import async_session_factory
    from api.src.models.knowledge_upload import KnowledgeUpload, STATUS_DELETED
    from sqlalchemy import select

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=30)
    async with async_session_factory() as db:
        rows = (await db.execute(
            select(KnowledgeUpload).where(
                KnowledgeUpload.status == STATUS_DELETED,
                KnowledgeUpload.deleted_at < cutoff,
            )
        )).scalars().all()

    purged = 0
    for row in rows:
        try:
            p = Path(row.original_path)
            if p.exists():
                p.unlink()
            purged += 1
            logger.info("rag.knowledge_purged", upload_id=row.id, path=str(p))
        except Exception as e:
            logger.warning("rag.knowledge_purge_failed", upload_id=row.id, error=str(e))

    return {"purged": purged}
