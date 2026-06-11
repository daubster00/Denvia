"""admin_user_activity_service.get_user_qa_log_detail 단위 테스트.

관리자 '상세보기' 흐름에서 normalized_query / retrieved_docs 가
서비스 레이어를 거치며 올바르게 매핑되는지, 다른 사용자의 로그를 노출하지
않는지(user_id × qa_log_id 교차 검증) 확인한다.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.src.services import admin_user_activity_service


def _make_qa_log_row(
    *,
    row_id: int = 101,
    user_id: int = 7,
    question_text: str = "임플란트 비용?",
    normalized_query: str | None = "임플란트 수가",
    retrieved_docs: list | None = None,
    prompt_text: str | None = None,
    answer_text: str | None = "보험 청구 가능 코드는 ...",
    rule_matched: bool = False,
    status: str | None = "completed",
):
    row = MagicMock()
    row.id = row_id
    row.user_id = user_id
    row.question_text = question_text
    row.normalized_query = normalized_query
    row.retrieved_docs = retrieved_docs
    row.prompt_text = prompt_text
    row.answer_text = answer_text
    row.rule_matched = rule_matched
    row.status = status
    row.input_tokens = 10
    row.output_tokens = 20
    row.cost_usd = Decimal("0.001")
    row.latency_ms = 1234
    row.created_at = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    return row


def _stub_db_returning(value):
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=value)
    db.execute = AsyncMock(return_value=result)
    return db


@pytest.mark.asyncio
async def test_returns_none_when_row_missing():
    db = _stub_db_returning(None)
    detail = await admin_user_activity_service.get_user_qa_log_detail(
        db, user_id=7, qa_log_id=999
    )
    assert detail is None


@pytest.mark.asyncio
async def test_maps_normalized_query_and_docs():
    docs = [
        {"page_content": "임플란트 보험 청구 코드 U2240", "metadata": {"source": "보험.md"}},
        {"page_content": "수가 표 — 2025년", "metadata": {"source": "수가표.pdf", "page": 3}},
    ]
    row = _make_qa_log_row(retrieved_docs=docs)
    db = _stub_db_returning(row)

    detail = await admin_user_activity_service.get_user_qa_log_detail(
        db, user_id=7, qa_log_id=101
    )

    assert detail is not None
    assert detail.qa_log_id == 101
    assert detail.question_text == "임플란트 비용?"
    assert detail.normalized_query == "임플란트 수가"
    assert len(detail.retrieved_docs) == 2
    assert detail.retrieved_docs[0].page_content.startswith("임플란트 보험")
    assert detail.retrieved_docs[1].metadata.get("page") == 3
    assert detail.answer_text == "보험 청구 가능 코드는 ..."
    assert detail.rule_matched is False
    assert detail.input_tokens == 10
    assert detail.cost_usd == Decimal("0.001")


@pytest.mark.asyncio
async def test_legacy_row_with_null_audit_fields_returns_empty_lists():
    row = _make_qa_log_row(normalized_query=None, retrieved_docs=None)
    db = _stub_db_returning(row)

    detail = await admin_user_activity_service.get_user_qa_log_detail(
        db, user_id=7, qa_log_id=101
    )

    assert detail is not None
    assert detail.normalized_query is None
    assert detail.retrieved_docs == []


@pytest.mark.asyncio
async def test_skips_invalid_doc_entries():
    bad_docs = [
        {"page_content": "ok", "metadata": {"source": "a"}},
        "not-a-dict",
        None,
        {"page_content": "second", "metadata": {}},
    ]
    row = _make_qa_log_row(retrieved_docs=bad_docs)
    db = _stub_db_returning(row)

    detail = await admin_user_activity_service.get_user_qa_log_detail(
        db, user_id=7, qa_log_id=101
    )

    assert detail is not None
    contents = [d.page_content for d in detail.retrieved_docs]
    assert contents == ["ok", "second"]


@pytest.mark.asyncio
async def test_rule_matched_path_typically_has_no_docs():
    row = _make_qa_log_row(rule_matched=True, retrieved_docs=[])
    db = _stub_db_returning(row)

    detail = await admin_user_activity_service.get_user_qa_log_detail(
        db, user_id=7, qa_log_id=101
    )

    assert detail is not None
    assert detail.rule_matched is True
    assert detail.retrieved_docs == []
