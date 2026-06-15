"""동의어 사전(synonym_groups) 서비스 — Story 8.5.

책임:
- CRUD: list / create / update / delete / get_by_id
- 충돌 검사: canonical_term 자체 + 다른 그룹의 synonyms 배열 contains 검사
- CSV import: dry_run 미리보기 + 트랜잭션 적용
- CSV export: canonical_term ASC + UTF-8 BOM
- build_synonyms_dict_from_db(): RAG 런타임 dict 빌드
- invalidate_runtime_cache(): Redis DB 3 `runtime:synonyms_v1` DELETE

Cache-Aside (Redis DB 3): query_runner.run_rule_answer가 GET → miss 시 DB → SET.
변경 시 즉시 무효화 → 다음 RAG 호출이 새 dict를 빌드.
"""
from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timezone

import redis.asyncio as aioredis
import structlog
from fastapi import HTTPException, Request
from sqlalchemy import collate, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.synonym_group import SynonymGroup
from api.src.models.user import User
from api.src.schemas.admin.synonyms import (
    ImportConflict,
    ImportInvalidRow,
    ImportPreviewResponse,
    ImportSummary,
    SynonymGroupCreateRequest,
    SynonymGroupRead,
    SynonymGroupUpdateRequest,
    SynonymListResponse,
    _clean_synonyms,
    _clean_term,
)
from api.src.settings import REDIS_DB_RUNTIME_CONFIG, settings

logger = structlog.get_logger(__name__)

RUNTIME_CACHE_KEY = "runtime:synonyms_v1"
RUNTIME_CACHE_TTL_SEC = 3600

MAX_IMPORT_ROWS = 5000
MAX_IMPORT_BYTES = 1 * 1024 * 1024  # 1 MB


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

async def list_groups(
    db: AsyncSession, *, q: str | None, page: int, size: int
) -> SynonymListResponse:
    """검색·페이지네이션. q는 canonical_term ILIKE OR synonyms::text ILIKE."""
    size = max(1, min(size, 100))
    page = max(1, page)
    offset = (page - 1) * size

    stmt = select(SynonymGroup)
    count_stmt = select(func.count(SynonymGroup.id))

    if q:
        q_norm = q.strip()
        if q_norm:
            like = f"%{q_norm}%"
            from sqlalchemy import text as sa_text

            cond = or_(
                SynonymGroup.canonical_term.ilike(like),
                sa_text("synonyms::text ILIKE :like_q").bindparams(like_q=like),
            )
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)

    # COLLATE "C" → UTF-8 codepoint 순. Hangul 음절(U+AC00–U+D7A3)은
    # 자모(초성/중성/종성) 순으로 배치돼 있어 ㄱ,ㄴ,ㄷ... 한글 자모 순 정렬과 일치.
    stmt = (
        stmt.order_by(collate(SynonymGroup.canonical_term, "C").asc())
        .limit(size)
        .offset(offset)
    )

    rows = (await db.execute(stmt)).scalars().all()
    total = int((await db.execute(count_stmt)).scalar() or 0)

    return SynonymListResponse(
        groups=[SynonymGroupRead.model_validate(r) for r in rows],
        total=total,
        page=page,
        size=size,
    )


async def get_by_id(db: AsyncSession, group_id: int) -> SynonymGroup | None:
    return (
        await db.execute(select(SynonymGroup).where(SynonymGroup.id == group_id))
    ).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Conflict check
# ---------------------------------------------------------------------------

async def find_conflict(
    db: AsyncSession,
    term: str,
    *,
    exclude_id: int | None = None,
) -> SynonymGroup | None:
    """term이 canonical 또는 어떤 그룹의 synonyms 배열에 이미 존재하는지 검사."""
    from sqlalchemy import text as sa_text

    where_parts = [
        "(canonical_term = :term OR synonyms @> CAST(:term_arr AS JSONB))"
    ]
    params: dict = {
        "term": term,
        "term_arr": json.dumps([term], ensure_ascii=False),
    }
    if exclude_id is not None:
        where_parts.append("id != :exclude_id")
        params["exclude_id"] = exclude_id

    sql = sa_text(
        "SELECT id, canonical_term, synonyms, updated_at "
        "FROM synonym_groups WHERE " + " AND ".join(where_parts) + " LIMIT 1"
    )
    row = (await db.execute(sql, params)).first()
    if row is None:
        return None
    # row → SynonymGroup ORM 재조회 (간단성 우선)
    return await get_by_id(db, row[0])


def _conflict_response(existing: SynonymGroup, term: str) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": "SYNONYM_CONFLICT",
            "message": (
                f"'{term}'은(는) 이미 그룹 '{existing.canonical_term}'에 존재합니다."
            ),
            "conflicting_group_id": existing.id,
            "conflicting_term": term,
        },
    )


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------

async def create_group(
    request: Request,
    db: AsyncSession,
    payload: SynonymGroupCreateRequest,
    admin: User,
) -> SynonymGroup:
    canonical = payload.canonical_term
    synonyms = payload.synonyms

    # 1) canonical 충돌
    conflict = await find_conflict(db, canonical)
    if conflict is not None:
        raise _conflict_response(conflict, canonical)

    # 2) 각 동의어 충돌
    for syn in synonyms:
        conflict = await find_conflict(db, syn)
        if conflict is not None:
            raise _conflict_response(conflict, syn)

    now = datetime.now(tz=timezone.utc)
    row = SynonymGroup(
        canonical_term=canonical,
        synonyms=list(synonyms),
        created_by_admin_id=admin.id,
        updated_by_admin_id=admin.id,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    request.state.audit_target_type = "synonym_group"
    request.state.audit_target_id = str(row.id)
    request.state.audit_diff = {
        "op": "create",
        "after": {"canonical_term": canonical, "synonyms": synonyms},
    }

    await invalidate_runtime_cache()
    logger.info(
        "admin.rag.synonym.created",
        group_id=row.id,
        canonical=canonical,
        synonym_count=len(synonyms),
    )
    return row


async def update_group(
    request: Request,
    db: AsyncSession,
    group_id: int,
    payload: SynonymGroupUpdateRequest,
    admin: User,
) -> SynonymGroup:
    row = await get_by_id(db, group_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "SYNONYM_GROUP_NOT_FOUND"},
        )

    canonical = payload.canonical_term
    synonyms = payload.synonyms

    conflict = await find_conflict(db, canonical, exclude_id=group_id)
    if conflict is not None:
        raise _conflict_response(conflict, canonical)
    for syn in synonyms:
        conflict = await find_conflict(db, syn, exclude_id=group_id)
        if conflict is not None:
            raise _conflict_response(conflict, syn)

    before = {
        "canonical_term": row.canonical_term,
        "synonyms": list(row.synonyms or []),
    }

    row.canonical_term = canonical
    row.synonyms = list(synonyms)
    row.updated_by_admin_id = admin.id
    row.updated_at = datetime.now(tz=timezone.utc)
    await db.commit()
    await db.refresh(row)

    request.state.audit_target_type = "synonym_group"
    request.state.audit_target_id = str(row.id)
    request.state.audit_diff = {
        "op": "update",
        "before": before,
        "after": {"canonical_term": canonical, "synonyms": synonyms},
    }

    await invalidate_runtime_cache()
    logger.info("admin.rag.synonym.updated", group_id=row.id, canonical=canonical)
    return row


async def delete_group(
    request: Request,
    db: AsyncSession,
    group_id: int,
) -> None:
    row = await get_by_id(db, group_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "SYNONYM_GROUP_NOT_FOUND"},
        )

    before = {
        "canonical_term": row.canonical_term,
        "synonyms": list(row.synonyms or []),
    }
    await db.delete(row)
    await db.commit()

    request.state.audit_target_type = "synonym_group"
    request.state.audit_target_id = str(group_id)
    request.state.audit_diff = {"op": "delete", "before": before}

    await invalidate_runtime_cache()
    logger.info("admin.rag.synonym.deleted", group_id=group_id)


# ---------------------------------------------------------------------------
# CSV import / export
# ---------------------------------------------------------------------------

def _parse_csv_rows(file_bytes: bytes) -> tuple[list[dict], list[ImportInvalidRow]]:
    """CSV 파싱. (parsed_rows, invalid_rows). 헤더 검증 포함.

    포맷:
        canonical_term,synonyms
        광중합기,큐링기|큐어링
    """
    if len(file_bytes) > MAX_IMPORT_BYTES:
        raise HTTPException(
            status_code=413,
            detail={
                "code": "IMPORT_FILE_TOO_LARGE",
                "message": f"파일은 최대 {MAX_IMPORT_BYTES // 1024}KB까지 가능합니다.",
            },
        )

    # UTF-8 with BOM 대응
    text = file_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))

    fieldnames = reader.fieldnames or []
    if "canonical_term" not in fieldnames or "synonyms" not in fieldnames:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "IMPORT_HEADER_INVALID",
                "message": "CSV 헤더는 'canonical_term,synonyms' 이어야 합니다.",
            },
        )

    parsed: list[dict] = []
    invalid: list[ImportInvalidRow] = []

    for idx, raw_row in enumerate(reader, start=2):  # 1행은 헤더
        if len(parsed) + len(invalid) >= MAX_IMPORT_ROWS:
            raise HTTPException(
                status_code=413,
                detail={
                    "code": "IMPORT_TOO_MANY_ROWS",
                    "message": f"한 번에 최대 {MAX_IMPORT_ROWS}행까지 가능합니다.",
                },
            )

        canonical_raw = (raw_row.get("canonical_term") or "").strip()
        synonyms_raw = (raw_row.get("synonyms") or "").strip()

        if not canonical_raw:
            invalid.append(
                ImportInvalidRow(row=idx, error="canonical_term이 비어 있습니다.")
            )
            continue

        try:
            canonical = _clean_term(canonical_raw, field="canonical_term")
        except ValueError as exc:
            invalid.append(ImportInvalidRow(row=idx, error=str(exc)))
            continue

        raw_syns = [s for s in synonyms_raw.split("|")] if synonyms_raw else []
        try:
            synonyms = _clean_synonyms(raw_syns, canonical=canonical)
        except ValueError as exc:
            invalid.append(ImportInvalidRow(row=idx, error=str(exc)))
            continue

        parsed.append(
            {"row": idx, "canonical_term": canonical, "synonyms": synonyms}
        )

    return parsed, invalid


async def import_csv(
    request: Request,
    db: AsyncSession,
    file_bytes: bytes,
    *,
    dry_run: bool,
    admin: User,
) -> ImportPreviewResponse:
    parsed, invalid = _parse_csv_rows(file_bytes)

    # 기존 DB 매핑: canonical → SynonymGroup
    rows = (await db.execute(select(SynonymGroup))).scalars().all()
    by_canonical: dict[str, SynonymGroup] = {r.canonical_term: r for r in rows}
    # 어떤 그룹이 어떤 표현(canonical|synonyms)을 점유했는지 매핑
    occupancy: dict[str, SynonymGroup] = {}
    for r in rows:
        occupancy[r.canonical_term] = r
        for s in (r.synonyms or []):
            occupancy.setdefault(s, r)

    to_create: list[dict] = []
    to_update: list[tuple[SynonymGroup, dict]] = []
    unchanged = 0
    conflicts: list[ImportConflict] = []

    csv_terms_seen: dict[str, int] = {}  # CSV 내부 중복 검출

    for row in parsed:
        idx = row["row"]
        canonical = row["canonical_term"]
        synonyms = row["synonyms"]

        # (a) CSV 내부 canonical 중복
        prev_row = csv_terms_seen.get(canonical)
        if prev_row is not None:
            conflicts.append(
                ImportConflict(
                    row=idx,
                    canonical_term=canonical,
                    reason=f"CSV {prev_row}행에 동일 canonical이 이미 있음",
                )
            )
            continue
        csv_terms_seen[canonical] = idx

        existing = by_canonical.get(canonical)

        # (b) canonical이 다른 그룹의 synonym으로 점유돼 있으면 충돌
        owner = occupancy.get(canonical)
        if owner is not None and owner is not existing:
            conflicts.append(
                ImportConflict(
                    row=idx,
                    canonical_term=canonical,
                    reason=f"이미 그룹 '{owner.canonical_term}'에 존재",
                )
            )
            continue

        # (c) 동의어 충돌 검사
        synonym_conflict = False
        for syn in synonyms:
            owner = occupancy.get(syn)
            if owner is None:
                continue
            if existing is not None and owner.id == existing.id:
                continue
            conflicts.append(
                ImportConflict(
                    row=idx,
                    canonical_term=canonical,
                    reason=(
                        f"동의어 '{syn}'은(는) 이미 그룹 '{owner.canonical_term}'에 존재"
                    ),
                )
            )
            synonym_conflict = True
            break
        if synonym_conflict:
            continue

        if existing is None:
            to_create.append(row)
        else:
            current_syns = list(existing.synonyms or [])
            if current_syns == synonyms:
                unchanged += 1
            else:
                to_update.append((existing, row))

    summary = ImportSummary(
        to_create=len(to_create),
        to_update=len(to_update),
        conflicts=len(conflicts),
        invalid=len(invalid),
        unchanged=unchanged,
    )

    if dry_run:
        return ImportPreviewResponse(
            summary=summary,
            conflicts=conflicts,
            invalid=invalid,
        )

    if conflicts:
        # 충돌 1건이라도 있으면 전체 롤백 — DB 변경 0
        raise HTTPException(
            status_code=409,
            detail={
                "code": "IMPORT_HAS_CONFLICTS",
                "message": "CSV에 충돌이 있어 적용을 중단했습니다.",
                "summary": summary.model_dump(),
                "conflicts": [c.model_dump() for c in conflicts],
            },
        )

    now = datetime.now(tz=timezone.utc)
    for row in to_create:
        db.add(
            SynonymGroup(
                canonical_term=row["canonical_term"],
                synonyms=list(row["synonyms"]),
                created_by_admin_id=admin.id,
                updated_by_admin_id=admin.id,
                created_at=now,
                updated_at=now,
            )
        )
    for existing, row in to_update:
        existing.synonyms = list(row["synonyms"])
        existing.updated_by_admin_id = admin.id
        existing.updated_at = now

    await db.commit()

    request.state.audit_target_type = "synonym_group"
    request.state.audit_target_id = "bulk"
    # 행 수가 100을 넘으면 stats만 (PRD § AC-6)
    audit_diff: dict = {"op": "import", "stats": summary.model_dump()}
    if len(parsed) <= 100:
        audit_diff["rows"] = [
            {
                "row": r["row"],
                "canonical_term": r["canonical_term"],
                "synonym_count": len(r["synonyms"]),
            }
            for r in parsed
        ]
    request.state.audit_diff = audit_diff

    await invalidate_runtime_cache()
    logger.info(
        "admin.rag.synonym.imported",
        to_create=summary.to_create,
        to_update=summary.to_update,
        unchanged=summary.unchanged,
        invalid=summary.invalid,
    )

    return ImportPreviewResponse(
        summary=summary,
        conflicts=[],
        invalid=invalid,
    )


async def export_csv(db: AsyncSession) -> bytes:
    """canonical_term ASC + UTF-8 BOM CSV 바이트."""
    rows = (
        await db.execute(
            select(SynonymGroup).order_by(
                collate(SynonymGroup.canonical_term, "C").asc()
            )
        )
    ).scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["canonical_term", "synonyms"])
    for r in rows:
        writer.writerow([r.canonical_term, "|".join(r.synonyms or [])])
    text = buf.getvalue()
    return ("﻿" + text).encode("utf-8")


# ---------------------------------------------------------------------------
# RAG runtime helpers
# ---------------------------------------------------------------------------

# 접두-기호형 동의어 패턴: <영숫자 접두><기호><tail>  (예: "g.inlay" → 접두 "g", tail "inlay")
_PREFIXED_SYMBOL_FORM = re.compile(r"^[a-z0-9]+[^a-z0-9가-힣]+(?P<tail>[a-z0-9가-힣].*)$")
_HAS_SYMBOL = re.compile(r"[^a-z0-9가-힣]")


def _sanitize_group_synonyms(synonyms: list[str]) -> list[str]:
    """vendor 동의어 정규화에 넘기기 전, 접두-기호형 동의어를 런타임 dict에서만 제거한다.

    #94: 그룹 동의어가 ["inray","inlay","g.inlay"] 일 때, "g.inlay"는 vendor PHASE 1
    (기호 포함 동의어 직접 치환)이 토큰 전체를 대표어로 바꿔 "g." 접두가 사라진다
    (→ "인레이"). 같은 그룹에 평문 "inlay"가 있으면 "g.inlay"를 dict에서 빼,
    토크나이저가 안쪽 "inlay"만 치환해 접두를 보존("g.인레이")하도록 한다.

    정당한 기호 동의어(c/f, p/e 등)는 tail("f","e")이 평문 동의어와 일치하지 않으므로
    그대로 유지된다. DB·관리자 UI·검색에는 영향 없음(런타임 dict 빌드 시점에만 적용).
    """
    plain_lower = {
        s.lower() for s in synonyms if not _HAS_SYMBOL.search(s.lower())
    }
    kept: list[str] = []
    for s in synonyms:
        sl = s.lower()
        if _HAS_SYMBOL.search(sl):
            m = _PREFIXED_SYMBOL_FORM.match(sl)
            if m and m.group("tail") in plain_lower:
                continue  # 접두 보존을 위해 런타임 dict에서만 제외
        kept.append(s)
    return kept


async def build_synonyms_dict_from_db(db: AsyncSession) -> dict[str, list[str]]:
    """RAG normalize_query(query, dict)에 직접 전달할 dict 빌드.

    접두-기호형 동의어(평문 tail이 있는 "g.inlay" 등)는 vendor PHASE 1 직접치환이
    접두를 삼키므로 빌드 시 제거해 토크나이저 경유 치환으로 접두를 보존한다(#94).
    """
    rows = (await db.execute(select(SynonymGroup))).scalars().all()
    return {
        r.canonical_term: _sanitize_group_synonyms(list(r.synonyms or []))
        for r in rows
    }


async def _get_redis() -> aioredis.Redis:
    return aioredis.from_url(
        settings.redis_url,
        db=REDIS_DB_RUNTIME_CONFIG,
        decode_responses=True,
    )


async def invalidate_runtime_cache() -> None:
    """Redis DB 3 `runtime:synonyms_v1` DELETE."""
    try:
        r = await _get_redis()
        async with r:
            await r.delete(RUNTIME_CACHE_KEY)
    except Exception as exc:
        logger.warning("synonym_service.cache_invalidate_failed", error=str(exc))


def _csv_filename_today() -> str:
    return f"synonyms-{datetime.now(tz=timezone.utc).strftime('%Y%m%d')}.csv"


__all__ = [
    "RUNTIME_CACHE_KEY",
    "RUNTIME_CACHE_TTL_SEC",
    "build_synonyms_dict_from_db",
    "create_group",
    "delete_group",
    "export_csv",
    "find_conflict",
    "get_by_id",
    "import_csv",
    "invalidate_runtime_cache",
    "list_groups",
    "update_group",
    "_csv_filename_today",
    "_sanitize_group_synonyms",
]
