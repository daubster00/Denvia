"""RAG 관리 서비스 — Story 8.1/8.2/8.3 TXT 지식 업로드 + 편집/삭제 + 재빌드."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import structlog
from fastapi import HTTPException, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.knowledge_upload import (
    KnowledgeUpload,
    STATUS_ACTIVE,
    STATUS_DELETED,
    STATUS_REBUILD_PENDING,
    STATUS_VALIDATED,
)
from api.src.models.user import User
from api.src.rag_integration.indexer import ParseFailure, dry_run_parse
from api.src.schemas.admin.rag import (
    ActiveRebuildInfo,
    HierarchyPreviewItem,
    KnowledgeEditResponse,
    KnowledgeListItem,
    KnowledgeListResponse,
    KnowledgeUploadResponse,
    RagStatusResponse,
    RebuildJobStatusResponse,
    RebuildTriggerResponse,
)

logger = structlog.get_logger()

UPLOAD_DIR = Path(__file__).parent.parent.parent / "data" / "uploads" / "knowledge"
MAX_BYTES = 10 * 1024 * 1024  # 10 MB


def _safe_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)[:200]


async def upload_and_validate(
    request: Request,
    file: UploadFile,
    admin: User,
    db: AsyncSession,
) -> KnowledgeUploadResponse:
    """1차 검증 → dry-run 파싱 → DB INSERT → 파일 저장."""
    # 1차 검증 — 순서 엄수 (AC-3): 크기(스트리밍) → MIME → 확장자 → UTF-8
    _CHUNK = 64 * 1024
    _buf: list[bytes] = []
    _total = 0
    while True:
        _part = await file.read(_CHUNK)
        if not _part:
            break
        _total += len(_part)
        if _total > MAX_BYTES:
            raise HTTPException(
                422,
                detail={
                    "code": "UPLOAD_TOO_LARGE",
                    "message": "파일이 10MB를 초과합니다.",
                    "limit_mb": 10,
                },
            )
        _buf.append(_part)
    raw = b"".join(_buf)

    content_type = (file.content_type or "").split(";")[0].strip()
    if content_type and content_type not in ("text/plain", ""):
        raise HTTPException(
            422,
            detail={
                "code": "UPLOAD_MIME_INVALID",
                "message": "텍스트 파일(.txt)만 업로드 가능합니다.",
                "provided": file.content_type,
            },
        )

    original_name = file.filename or ""
    if not original_name.lower().endswith(".txt"):
        raise HTTPException(
            422,
            detail={
                "code": "UPLOAD_EXT_INVALID",
                "message": "확장자가 .txt가 아닙니다.",
                "provided": original_name,
            },
        )

    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            422,
            detail={
                "code": "UPLOAD_ENCODING_INVALID",
                "message": "UTF-8 인코딩이 아닙니다. (CP949·EUC-KR 등 미지원)",
                "detected_encoding_hint": "non_utf8",
            },
        )

    # SHA-256 중복 검출 (AC-7)
    content_hash = hashlib.sha256(raw).hexdigest()
    dup_result = await db.execute(
        select(KnowledgeUpload).where(
            KnowledgeUpload.content_hash == content_hash,
            KnowledgeUpload.deleted_at.is_(None),
        )
    )
    dup = dup_result.scalar_one_or_none()
    if dup:
        raise HTTPException(
            409,
            detail={
                "code": "UPLOAD_DUPLICATE",
                "message": "동일한 내용의 파일이 이미 업로드되어 있습니다.",
                "existing_upload_id": dup.id,
                "existing_filename": dup.filename,
            },
        )

    # dry-run 파싱 (AC-4) — 임시 파일 사용, try/finally로 항상 삭제
    fd, tmp_str = tempfile.mkstemp(suffix=".txt")
    tmp_path = Path(tmp_str)
    try:
        import os
        os.close(fd)
        tmp_path.write_text(decoded, encoding="utf-8")
        parse_result = dry_run_parse(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    if parse_result.failure or parse_result.chunk_count == 0:
        failure = parse_result.failure or ParseFailure("no_categories", "청크가 생성되지 않았습니다.")
        raise HTTPException(
            422,
            detail={
                "code": "UPLOAD_FORMAT_UNPARSEABLE",
                "message": "지식 파일 포맷을 파싱할 수 없습니다.",
                "reason": failure.reason,
                "parse_message": failure.message,
            },
        )

    # DB INSERT + 파일 저장 (AC-6) — 트랜잭션/파일 잔재 방지
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    final_path: Path | None = None
    try:
        safe_name = _safe_filename(original_name)
        hierarchy_data = [asdict(g) for g in parse_result.hierarchy]

        upload = KnowledgeUpload(
            filename=original_name,
            original_path="",  # flush 후 id 획득하여 확정
            size_bytes=len(raw),
            content_hash=content_hash,
            chunk_count=parse_result.chunk_count,
            category_count=parse_result.category_count,
            hierarchy_json=hierarchy_data,
            status=STATUS_VALIDATED,
            uploaded_by_admin_id=admin.id,
        )
        db.add(upload)
        await db.flush()  # id 획득 (commit 전 — 실패 시 rollback 가능)

        final_path = UPLOAD_DIR / f"{upload.id}_{safe_name}"
        final_path.write_bytes(raw)

        upload.original_path = str(final_path)
        await db.commit()
    except Exception:
        await db.rollback()
        if final_path is not None:
            final_path.unlink(missing_ok=True)
        raise

    # AuditMiddleware 보강 속성 설정 (AC-9)
    request.state.audit_target_type = "knowledge_upload"
    request.state.audit_target_id = upload.id
    request.state.audit_diff = {
        "filename": original_name,
        "size_bytes": len(raw),
        "chunk_count": parse_result.chunk_count,
        "category_count": parse_result.category_count,
        "content_hash": content_hash,
    }

    logger.info(
        "admin.rag.knowledge_uploaded",
        upload_id=upload.id,
        filename=original_name,
        chunk_count=parse_result.chunk_count,
    )

    return KnowledgeUploadResponse(
        upload_id=upload.id,
        filename=original_name,
        size_bytes=len(raw),
        chunk_count=parse_result.chunk_count,
        category_count=parse_result.category_count,
        hierarchy_preview=[
            HierarchyPreviewItem(major=g.major, minors=g.minors[:10])
            for g in parse_result.hierarchy
        ],
    )


async def get_upload(upload_id: int, db: AsyncSession) -> KnowledgeUpload:
    """단건 조회 (GET/PUT용) — deleted_at IS NULL 체크."""
    row = await db.get(KnowledgeUpload, upload_id)
    if row is None or row.deleted_at is not None:
        raise HTTPException(
            404,
            detail={"code": "KNOWLEDGE_NOT_FOUND", "message": "지식 파일을 찾을 수 없습니다."},
        )
    return row


async def get_upload_any(upload_id: int, db: AsyncSession) -> KnowledgeUpload:
    """단건 조회 (DELETE용) — deleted_at 무관."""
    row = await db.get(KnowledgeUpload, upload_id)
    if row is None:
        raise HTTPException(
            404,
            detail={"code": "KNOWLEDGE_NOT_FOUND", "message": "지식 파일을 찾을 수 없습니다."},
        )
    return row


async def edit_upload(
    request: Request,
    upload_id: int,
    content: str,
    admin: User,
    db: AsyncSession,
) -> KnowledgeEditResponse:
    upload = await get_upload(upload_id, db)

    fd, tmp_str = tempfile.mkstemp(suffix=".txt")
    tmp_path = Path(tmp_str)
    try:
        os.close(fd)
        tmp_path.write_text(content, encoding="utf-8")
        parse_result = dry_run_parse(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    if parse_result.failure or parse_result.chunk_count == 0:
        failure = parse_result.failure or ParseFailure("no_categories", "청크가 생성되지 않았습니다.")
        raise HTTPException(
            422,
            detail={
                "code": "UPLOAD_FORMAT_UNPARSEABLE",
                "message": "지식 파일 포맷을 파싱할 수 없습니다.",
                "reason": failure.reason,
                "parse_message": failure.message,
            },
        )

    new_raw = content.encode("utf-8")
    new_hash = hashlib.sha256(new_raw).hexdigest()

    dup_result = await db.execute(
        select(KnowledgeUpload).where(
            KnowledgeUpload.content_hash == new_hash,
            KnowledgeUpload.deleted_at.is_(None),
            KnowledgeUpload.id != upload_id,
        )
    )
    dup = dup_result.scalar_one_or_none()
    if dup:
        raise HTTPException(
            409,
            detail={
                "code": "UPLOAD_DUPLICATE",
                "message": "동일한 내용의 파일이 이미 업로드되어 있습니다.",
                "existing_upload_id": dup.id,
                "existing_filename": dup.filename,
            },
        )

    before_chunk_count = upload.chunk_count
    before_size_bytes = upload.size_bytes
    before_hash = upload.content_hash
    now = datetime.now(tz=timezone.utc)
    original_path = Path(upload.original_path)
    try:
        backup_raw = original_path.read_bytes()
    except FileNotFoundError:
        raise HTTPException(
            500,
            detail={
                "code": "KNOWLEDGE_FILE_MISSING",
                "message": "지식 파일을 디스크에서 찾을 수 없습니다. 운영팀에 문의하세요.",
            },
        )
    replace_tmp = original_path.with_suffix(original_path.suffix + ".editing")

    try:
        replace_tmp.write_bytes(new_raw)
        os.replace(replace_tmp, original_path)
        upload.size_bytes = len(new_raw)
        upload.chunk_count = parse_result.chunk_count
        upload.category_count = parse_result.category_count
        upload.content_hash = new_hash
        upload.hierarchy_json = [asdict(g) for g in parse_result.hierarchy]
        upload.status = STATUS_VALIDATED
        upload.last_modified_at = now
        await db.commit()
    except Exception:
        await db.rollback()
        replace_tmp.unlink(missing_ok=True)
        original_path.write_bytes(backup_raw)
        raise

    request.state.audit_target_type = "knowledge_upload"
    request.state.audit_target_id = upload_id
    request.state.audit_diff = {
        "before": {
            "size_bytes": before_size_bytes,
            "chunk_count": before_chunk_count,
            "content_hash": before_hash,
        },
        "after": {
            "size_bytes": len(new_raw),
            "chunk_count": parse_result.chunk_count,
            "content_hash": new_hash,
        },
    }

    logger.info("admin.rag.knowledge_edited", upload_id=upload_id,
                chunk_count=parse_result.chunk_count)
    return KnowledgeEditResponse.model_validate(upload)


async def delete_upload(
    request: Request,
    upload_id: int,
    admin: User,
    db: AsyncSession,
) -> None:
    upload = await get_upload_any(upload_id, db)
    if upload.status in (STATUS_DELETED, STATUS_REBUILD_PENDING):
        raise HTTPException(
            409,
            detail={"code": "KNOWLEDGE_ALREADY_DELETED", "message": "이미 삭제된 파일입니다."},
        )

    # active 파일은 인덱스에 반영됐으므로 다음 재빌드 시 제거 대상 표시
    # validated 파일은 인덱스에 반영된 적 없으므로 pending 취소로 처리
    new_status = STATUS_REBUILD_PENDING if upload.status == STATUS_ACTIVE else STATUS_DELETED

    diff = {
        "filename": upload.filename,
        "chunk_count": upload.chunk_count,
        "category_count": upload.category_count,
    }
    now = datetime.now(tz=timezone.utc)
    try:
        upload.deleted_at = now
        upload.status = new_status
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    request.state.audit_target_type = "knowledge_upload"
    request.state.audit_target_id = upload_id
    request.state.audit_diff = diff
    logger.info("admin.rag.knowledge_deleted", upload_id=upload_id)


async def trigger_rebuild(request: Request, admin, db: AsyncSession) -> RebuildTriggerResponse:
    """재빌드 트리거 — 동시 1건 제한 + INSERT + apply_async + task id 저장."""
    from api.src.models.rebuild_job import ACTIVE_STATUSES, RebuildJob, STATUS_FAILED
    from api.src.workers.rag_tasks import rebuild_index_task
    from api.utils.faiss_swap import get_current_slot
    from api.src.settings import settings
    from sqlalchemy.exc import IntegrityError

    # 동시 1건 제한 (fast-path: select 먼저 확인)
    existing = (await db.execute(
        select(RebuildJob).where(RebuildJob.status.in_(list(ACTIVE_STATUSES)))
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(
            409,
            detail={
                "code": "REBUILD_ALREADY_IN_PROGRESS",
                "message": "이미 재빌드가 진행 중입니다.",
                "active_job_id": existing.id,
            },
        )

    # 재빌드 후 인덱스에 들어갈 파일이 0건이면 update_vectorstore가 실패하므로
    # 트리거 단계에서 차단 (worker query와 동일 조건: deleted_at IS NULL)
    indexable_count = (await db.execute(
        select(func.count()).select_from(KnowledgeUpload).where(
            KnowledgeUpload.deleted_at.is_(None)
        )
    )).scalar_one()
    if indexable_count == 0:
        raise HTTPException(
            422,
            detail={
                "code": "REBUILD_NO_ACTIVE_FILES",
                "message": "재빌드할 활성 지식 파일이 없습니다. 새 파일을 업로드한 뒤 다시 시도해 주세요.",
            },
        )

    # target slot 결정
    current_slot = get_current_slot(
        settings.faiss_current_path,
        settings.faiss_index_a_path,
        settings.faiss_index_b_path,
    )
    target_slot = "b" if current_slot == "a" else "a"

    # pending_changes_count
    status_resp = await get_rag_status(db)
    pending_count = status_resp.pending_changes_count

    job = RebuildJob(
        triggered_by_admin_id=admin.id,
        target_slot=target_slot,
    )
    db.add(job)

    # worker가 조회 가능하도록 먼저 commit (partial unique index로 race-safe)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = (await db.execute(
            select(RebuildJob).where(RebuildJob.status.in_(list(ACTIVE_STATUSES)))
        )).scalar_one_or_none()
        raise HTTPException(
            409,
            detail={
                "code": "REBUILD_ALREADY_IN_PROGRESS",
                "message": "이미 재빌드가 진행 중입니다.",
                "active_job_id": existing.id if existing else None,
            },
        )

    job_id = job.id  # PK는 commit 후 사용 가능

    # Celery task enqueue — 실패 시 job을 failed로 마킹
    try:
        task = rebuild_index_task.apply_async(args=[job_id])
    except Exception as enqueue_exc:
        try:
            job.status = STATUS_FAILED
            job.error_message = f"enqueue_failed: {str(enqueue_exc)[:200]}"
            job.finished_at = datetime.now(tz=timezone.utc)
            await db.commit()
        except Exception:
            await db.rollback()
        logger.error("admin.rag.rebuild_enqueue_failed", job_id=job_id, error=str(enqueue_exc))
        raise HTTPException(
            500,
            detail={
                "code": "REBUILD_ENQUEUE_FAILED",
                "message": "재빌드 큐 등록에 실패했습니다.",
            },
        )

    # celery task id 별도 트랜잭션으로 저장 (non-critical)
    job.celery_task_id = task.id
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        logger.warning("admin.rag.rebuild_task_id_save_failed", job_id=job_id)

    request.state.audit_target_type = "rebuild_job"
    request.state.audit_target_id = job_id
    request.state.audit_diff = {"pending_changes_count": pending_count, "target_slot": target_slot}

    logger.info("admin.rag.rebuild_triggered", job_id=job_id, target_slot=target_slot)
    return RebuildTriggerResponse(job_id=job_id, target_slot=target_slot)


async def cancel_rebuild(
    request: Request, job_id: int, admin, db: AsyncSession
) -> RebuildJobStatusResponse:
    """재빌드 취소 — Celery revoke + DB 상태 갱신."""
    from api.src.models.rebuild_job import ACTIVE_STATUSES, RebuildJob, STATUS_CANCELED
    from api.src.workers.celery_app import celery_app

    job = await db.get(RebuildJob, job_id)
    if job is None:
        raise HTTPException(
            404,
            detail={"code": "REBUILD_JOB_NOT_FOUND", "message": "재빌드 작업을 찾을 수 없습니다."},
        )

    if job.status not in ACTIVE_STATUSES:
        raise HTTPException(
            409,
            detail={
                "code": "REBUILD_NOT_CANCELABLE",
                "message": "재빌드를 취소할 수 없는 상태입니다.",
                "current_status": job.status,
            },
        )

    if job.celery_task_id:
        celery_app.control.revoke(job.celery_task_id, terminate=True)

    now = datetime.now(tz=timezone.utc)
    job.status = STATUS_CANCELED
    job.error_message = "user_canceled"
    job.finished_at = now
    await db.commit()

    request.state.audit_target_type = "rebuild_job"
    request.state.audit_target_id = job_id
    request.state.audit_diff = {"canceled": True, "job_id": job_id}

    logger.info("admin.rag.rebuild_canceled", job_id=job_id, admin_id=admin.id)
    return RebuildJobStatusResponse.model_validate(job)


async def get_rebuild_job(job_id: int, db: AsyncSession) -> RebuildJobStatusResponse:
    """재빌드 job 단건 조회 (폴링 fallback)."""
    from api.src.models.rebuild_job import RebuildJob

    job = await db.get(RebuildJob, job_id)
    if job is None:
        raise HTTPException(
            404,
            detail={"code": "REBUILD_JOB_NOT_FOUND", "message": "재빌드 작업을 찾을 수 없습니다."},
        )
    return RebuildJobStatusResponse.model_validate(job)


async def get_rag_status(db: AsyncSession) -> RagStatusResponse:
    """재빌드 대기 카운트 + 마지막 재빌드 + 활성 재빌드 반환."""
    from api.src.models.rebuild_job import ACTIVE_STATUSES, RebuildJob, STATUS_SUCCESS

    # 마지막 성공 재빌드
    last_success = (await db.execute(
        select(RebuildJob)
        .where(RebuildJob.status == STATUS_SUCCESS)
        .order_by(RebuildJob.swapped_at.desc())
        .limit(1)
    )).scalar_one_or_none()

    # 마지막 job (성공/실패 불문)
    last_job = (await db.execute(
        select(RebuildJob)
        .order_by(RebuildJob.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()

    # 활성 job
    active_job = (await db.execute(
        select(RebuildJob)
        .where(RebuildJob.status.in_(list(ACTIVE_STATUSES)))
        .order_by(RebuildJob.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()

    # pending_changes_count:
    # - validated + deleted_at IS NULL : 아직 인덱스에 반영되지 않은 신규 파일
    # - rebuild_pending                : active였다가 삭제된 파일 (다음 재빌드로 인덱스에서 제거 필요)
    # validated→deleted 전환(인덱스 미반영 파일 삭제)은 카운트에서 제외
    pending_q = select(func.count()).select_from(
        select(KnowledgeUpload).where(
            (
                (KnowledgeUpload.status == STATUS_VALIDATED)
                & KnowledgeUpload.deleted_at.is_(None)
            ) | (
                KnowledgeUpload.status == STATUS_REBUILD_PENDING
            )
        ).subquery()
    )

    pending = (await db.execute(pending_q)).scalar_one()

    active_rebuild_info = None
    if active_job:
        active_rebuild_info = ActiveRebuildInfo(
            job_id=active_job.id,
            status=active_job.status,
            progress_percent=active_job.progress_percent,
            stage=active_job.stage,
        )

    return RagStatusResponse(
        pending_changes_count=pending,
        last_rebuild_at=last_success.swapped_at if last_success else None,
        last_rebuild_status=last_job.status if last_job else None,
        active_rebuild=active_rebuild_info,
    )


async def list_uploads(
    page: int,
    per_page: int,
    db: AsyncSession,
) -> KnowledgeListResponse:
    """업로드된 파일 목록 조회 — deleted_at IS NOT NULL 행 제외 (AC-10)."""
    base_q = select(KnowledgeUpload).where(KnowledgeUpload.deleted_at.is_(None))

    count_q = select(func.count()).select_from(base_q.subquery())
    total = (await db.execute(count_q)).scalar_one()

    items_q = (
        base_q.order_by(KnowledgeUpload.uploaded_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    rows = (await db.execute(items_q)).scalars().all()

    logger.info("admin.rag.knowledge_listed", page=page, total=total)

    return KnowledgeListResponse(
        items=[KnowledgeListItem.model_validate(r) for r in rows],
        page=page,
        per_page=per_page,
        total=total,
    )
