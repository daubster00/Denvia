"""synonym_service 단위 테스트 — Story 8.5.

CRUD / 충돌 / CSV 파서 / dict 빌드 단위 동작을 검증한다.
"""
from __future__ import annotations

import pytest

from api.src.schemas.admin.synonyms import (
    SynonymGroupCreateRequest,
    SynonymGroupUpdateRequest,
)


# ────────────────────────────────────────────────────────────────
# Pydantic validator
# ────────────────────────────────────────────────────────────────

def test_create_request_strips_canonical_and_synonyms():
    req = SynonymGroupCreateRequest(
        canonical_term="  광중합기  ",
        synonyms=[" 큐링기 ", "큐어링", "  ", "큐링기"],
    )
    assert req.canonical_term == "광중합기"
    assert req.synonyms == ["큐링기", "큐어링"]  # trim + dedupe + 빈 제거


def test_create_request_removes_self_reference():
    req = SynonymGroupCreateRequest(
        canonical_term="광중합기",
        synonyms=["큐링기", "광중합기", "큐어링"],
    )
    assert req.synonyms == ["큐링기", "큐어링"]


def test_create_request_empty_canonical_raises():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SynonymGroupCreateRequest(canonical_term="   ", synonyms=[])


def test_create_request_canonical_too_long_raises():
    from pydantic import ValidationError

    long_term = "가" * 101
    with pytest.raises(ValidationError):
        SynonymGroupCreateRequest(canonical_term=long_term, synonyms=[])


def test_create_request_too_many_synonyms_raises():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SynonymGroupCreateRequest(
            canonical_term="대표",
            synonyms=[f"syn{i}" for i in range(51)],
        )


def test_update_request_same_rules_as_create():
    req = SynonymGroupUpdateRequest(canonical_term=" A ", synonyms=[" b ", "b"])
    assert req.canonical_term == "A"
    assert req.synonyms == ["b"]


# ────────────────────────────────────────────────────────────────
# CSV parser
# ────────────────────────────────────────────────────────────────

def test_parse_csv_basic_two_rows():
    from api.src.services.synonym_service import _parse_csv_rows

    csv_text = "canonical_term,synonyms\n광중합기,큐링기|큐어링\n공단검진,국가검진\n"
    parsed, invalid = _parse_csv_rows(csv_text.encode("utf-8"))
    assert len(parsed) == 2
    assert parsed[0]["canonical_term"] == "광중합기"
    assert parsed[0]["synonyms"] == ["큐링기", "큐어링"]
    assert parsed[1]["canonical_term"] == "공단검진"
    assert parsed[1]["synonyms"] == ["국가검진"]
    assert invalid == []


def test_parse_csv_invalid_header_raises():
    from fastapi import HTTPException

    from api.src.services.synonym_service import _parse_csv_rows

    bad = b"wrong_header,synonyms\nfoo,bar\n"
    with pytest.raises(HTTPException) as exc:
        _parse_csv_rows(bad)
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "IMPORT_HEADER_INVALID"


def test_parse_csv_empty_canonical_marked_invalid():
    from api.src.services.synonym_service import _parse_csv_rows

    csv_text = "canonical_term,synonyms\n,abc|def\n가,b\n"
    parsed, invalid = _parse_csv_rows(csv_text.encode("utf-8"))
    assert len(invalid) == 1
    assert invalid[0].row == 2
    assert len(parsed) == 1
    assert parsed[0]["canonical_term"] == "가"


def test_parse_csv_file_too_large_raises():
    from fastapi import HTTPException

    from api.src.services.synonym_service import _parse_csv_rows

    big = b"canonical_term,synonyms\n" + (b"a,b\n" * (1024 * 1024))
    with pytest.raises(HTTPException) as exc:
        _parse_csv_rows(big)
    assert exc.value.status_code == 413


def test_parse_csv_with_utf8_bom():
    from api.src.services.synonym_service import _parse_csv_rows

    bom = "﻿".encode("utf-8")
    csv = bom + b"canonical_term,synonyms\nFOO,bar\n"
    parsed, invalid = _parse_csv_rows(csv)
    assert len(parsed) == 1
    assert parsed[0]["canonical_term"] == "FOO"


# ────────────────────────────────────────────────────────────────
# CSV export
# ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_export_csv_includes_bom_and_pipe_separator():
    from unittest.mock import AsyncMock, MagicMock

    from api.src.models.synonym_group import SynonymGroup
    from api.src.services.synonym_service import export_csv

    rows = [
        MagicMock(spec=SynonymGroup, canonical_term="공단검진", synonyms=["국가검진", "공단"]),
        MagicMock(spec=SynonymGroup, canonical_term="광중합기", synonyms=["큐링기"]),
    ]
    rows[0].canonical_term = "공단검진"
    rows[0].synonyms = ["국가검진", "공단"]
    rows[1].canonical_term = "광중합기"
    rows[1].synonyms = ["큐링기"]

    exec_result = MagicMock()
    exec_result.scalars.return_value.all.return_value = rows

    db = MagicMock()
    db.execute = AsyncMock(return_value=exec_result)

    body = await export_csv(db)
    # BOM 확인
    assert body.startswith(b"\xef\xbb\xbf")
    text = body.decode("utf-8-sig")
    assert "canonical_term,synonyms" in text
    assert "공단검진,국가검진|공단" in text
    assert "광중합기,큐링기" in text


# ────────────────────────────────────────────────────────────────
# build_synonyms_dict_from_db
# ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_build_synonyms_dict_from_db_returns_canonical_to_list_map():
    from unittest.mock import AsyncMock, MagicMock

    from api.src.models.synonym_group import SynonymGroup
    from api.src.services.synonym_service import build_synonyms_dict_from_db

    rows = [MagicMock(spec=SynonymGroup), MagicMock(spec=SynonymGroup)]
    rows[0].canonical_term = "광중합기"
    rows[0].synonyms = ["큐링기", "큐어링"]
    rows[1].canonical_term = "공단검진"
    rows[1].synonyms = []

    exec_result = MagicMock()
    exec_result.scalars.return_value.all.return_value = rows

    db = MagicMock()
    db.execute = AsyncMock(return_value=exec_result)

    d = await build_synonyms_dict_from_db(db)
    assert d == {"광중합기": ["큐링기", "큐어링"], "공단검진": []}


# ────────────────────────────────────────────────────────────────
# invalidate_runtime_cache
# ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_invalidate_runtime_cache_calls_redis_delete():
    from unittest.mock import AsyncMock, patch

    from api.src.services.synonym_service import (
        RUNTIME_CACHE_KEY,
        invalidate_runtime_cache,
    )

    fake_redis = AsyncMock()
    fake_redis.__aenter__ = AsyncMock(return_value=fake_redis)
    fake_redis.__aexit__ = AsyncMock(return_value=False)
    fake_redis.delete = AsyncMock()

    with patch(
        "api.src.services.synonym_service._get_redis",
        new=AsyncMock(return_value=fake_redis),
    ):
        await invalidate_runtime_cache()

    fake_redis.delete.assert_awaited_once_with(RUNTIME_CACHE_KEY)


@pytest.mark.asyncio
async def test_invalidate_runtime_cache_swallows_redis_error():
    from unittest.mock import AsyncMock, patch

    from api.src.services.synonym_service import invalidate_runtime_cache

    with patch(
        "api.src.services.synonym_service._get_redis",
        new=AsyncMock(side_effect=RuntimeError("redis-down")),
    ):
        # 예외가 새어 나오면 안 된다 — 변경 트랜잭션을 끊지 않기 위함
        await invalidate_runtime_cache()


# ────────────────────────────────────────────────────────────────
# create_group / update_group / delete_group — 충돌 검출
# ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_group_conflict_returns_409():
    from unittest.mock import AsyncMock, MagicMock, patch

    from fastapi import HTTPException

    from api.src.models.synonym_group import SynonymGroup
    from api.src.services.synonym_service import create_group

    conflict_row = MagicMock(spec=SynonymGroup)
    conflict_row.id = 12
    conflict_row.canonical_term = "광중합기"

    with patch(
        "api.src.services.synonym_service.find_conflict",
        new=AsyncMock(return_value=conflict_row),
    ):
        request = MagicMock()
        request.state = MagicMock()
        admin = MagicMock()
        admin.id = 99
        db = MagicMock()

        payload = SynonymGroupCreateRequest(canonical_term="광중합기", synonyms=[])

        with pytest.raises(HTTPException) as exc:
            await create_group(request, db, payload, admin)

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "SYNONYM_CONFLICT"
    assert exc.value.detail["conflicting_group_id"] == 12


@pytest.mark.asyncio
async def test_update_group_not_found_returns_404():
    from unittest.mock import AsyncMock, MagicMock, patch

    from fastapi import HTTPException

    from api.src.services.synonym_service import update_group

    with patch(
        "api.src.services.synonym_service.get_by_id",
        new=AsyncMock(return_value=None),
    ):
        request = MagicMock()
        request.state = MagicMock()
        admin = MagicMock()
        admin.id = 99
        db = MagicMock()
        payload = SynonymGroupUpdateRequest(canonical_term="x", synonyms=[])

        with pytest.raises(HTTPException) as exc:
            await update_group(request, db, 99999, payload, admin)

    assert exc.value.status_code == 404
    assert exc.value.detail["code"] == "SYNONYM_GROUP_NOT_FOUND"


@pytest.mark.asyncio
async def test_delete_group_not_found_returns_404():
    from unittest.mock import AsyncMock, MagicMock, patch

    from fastapi import HTTPException

    from api.src.services.synonym_service import delete_group

    with patch(
        "api.src.services.synonym_service.get_by_id",
        new=AsyncMock(return_value=None),
    ):
        request = MagicMock()
        request.state = MagicMock()
        db = MagicMock()
        with pytest.raises(HTTPException) as exc:
            await delete_group(request, db, 12345)

    assert exc.value.status_code == 404
