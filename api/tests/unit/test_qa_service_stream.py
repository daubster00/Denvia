"""QAService.stream() 단위 테스트 — AsyncMock으로 DB 세션·RAG 격리.

rag.run_qa 모듈은 langchain 의존성을 모듈 임포트 시 로드하므로,
sys.modules 수준에서 mock해 단위 테스트 시 외부 의존성을 완전히 격리한다.
"""

import json
import sys
from decimal import Decimal
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.src.integrations.openai.client import TokenUsage
from api.src.models.qa_log import QALog
from api.src.models.user import User
from api.src.services.qa_service import QAService


# ---------------------------------------------------------------------------
# rag.run_qa sys.modules 모킹 픽스처
# ---------------------------------------------------------------------------

def _make_rag_module_mock(
    rule_answer: str | None = None,
    procedures: list[str] | None = None,
):
    """rag.run_qa 모듈을 모킹한 ModuleType을 반환한다."""
    mock_mod = ModuleType("rag.run_qa")
    mock_mod.apply_scaling_rules = lambda text: text
    mock_mod.get_syn_dict = lambda: {}
    mock_mod.normalize_query = lambda query, syn: query
    mock_mod.generate_rule_answer = lambda query: rule_answer
    mock_mod.extract_procedures = lambda query: procedures or []
    return mock_mod


def _make_user(user_id: int = 1, subscription_status: str = "pro") -> User:
    user = MagicMock(spec=User)
    user.id = user_id
    user.subscription_status = subscription_status
    return user


def _make_db(log_id: int = 42) -> AsyncMock:
    db = AsyncMock()

    async def _fake_refresh(obj):
        obj.id = log_id

    db.refresh = _fake_refresh
    db.add = MagicMock()
    return db


async def _collect(gen) -> list[dict]:
    """AsyncIterator[dict]에서 모든 이벤트를 수집한다."""
    events = []
    async for ev in gen:
        events.append(ev)
    return events


# ---------------------------------------------------------------------------
# RAG 경로 테스트
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_rag_path_yields_token_and_done():
    """RAG 경로: token 이벤트 + done 이벤트가 순서대로 발행된다."""
    svc = QAService()
    db = _make_db(log_id=10)
    user = _make_user()

    async def _mock_stream(query, on_complete):
        yield "안녕"
        yield "하세요"
        on_complete(TokenUsage(5, 10, 15, 0.002), "안녕하세요")

    rag_mock = _make_rag_module_mock(rule_answer=None, procedures=[])

    with (
        patch.dict("sys.modules", {"rag": MagicMock(), "rag.run_qa": rag_mock}),
        patch("api.src.services.qa_service.query_runner.ensure_initialized", new_callable=AsyncMock),
        patch("api.src.services.qa_service.query_runner.stream_rag_answer", side_effect=_mock_stream),
    ):
        events = await _collect(svc.stream(db=db, user=user, question_text="임플란트 보험"))

    event_names = [ev["event"] for ev in events]
    assert "token" in event_names
    assert "done" in event_names
    assert "error" not in event_names

    # 토큰 누적 검증
    tokens = [json.loads(ev["data"])["delta"] for ev in events if ev["event"] == "token"]
    assert "".join(tokens) == "안녕하세요"

    # done 페이로드 검증
    done_data = json.loads(next(ev["data"] for ev in events if ev["event"] == "done"))
    assert done_data["qa_log_id"] == 10
    assert done_data["total_tokens"] == 15
    assert done_data["rule_matched"] is False


# ---------------------------------------------------------------------------
# 룰 매칭 경로 테스트
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_rule_path_yields_rule_matched_token_done():
    """룰 경로: rule_matched → token → done 3종 이벤트 순서 검증."""
    svc = QAService()
    db = _make_db(log_id=20)
    user = _make_user()

    RULE_ANSWER = "장애인가산 300% 적용 가능합니다."
    PROCEDURES = ["발치", "보통처치"]

    rag_mock = _make_rag_module_mock(rule_answer=RULE_ANSWER, procedures=PROCEDURES)

    # normalize 결과가 "장애인"+"가산" 포함하도록 설정
    rag_mock.normalize_query = lambda query, syn: "장애인 발치 가산 가능?"

    with (
        patch.dict("sys.modules", {"rag": MagicMock(), "rag.run_qa": rag_mock}),
        patch("api.src.services.qa_service.query_runner.ensure_initialized", new_callable=AsyncMock),
    ):
        events = await _collect(svc.stream(db=db, user=user, question_text="장애인 발치 가산 가능?"))

    event_names = [ev["event"] for ev in events]
    assert event_names == ["rule_matched", "token", "done"]

    rule_data = json.loads(events[0]["data"])
    assert rule_data["procedure_count"] == len(PROCEDURES)

    token_data = json.loads(events[1]["data"])
    assert token_data["delta"] == RULE_ANSWER

    done_data = json.loads(events[2]["data"])
    assert done_data["rule_matched"] is True
    assert done_data["total_tokens"] == 0


# ---------------------------------------------------------------------------
# 예외 → error 이벤트 테스트
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_exception_yields_error_event():
    """OpenAI 예외 → event: error가 발행된다."""
    import openai

    svc = QAService()
    db = _make_db(log_id=30)
    user = _make_user()

    async def _mock_stream_raises(query, on_complete):
        raise openai.APITimeoutError("timeout")
        yield  # make it a generator

    rag_mock = _make_rag_module_mock(rule_answer=None, procedures=[])

    with (
        patch.dict("sys.modules", {"rag": MagicMock(), "rag.run_qa": rag_mock}),
        patch("api.src.services.qa_service.query_runner.ensure_initialized", new_callable=AsyncMock),
        patch("api.src.services.qa_service.query_runner.stream_rag_answer", side_effect=_mock_stream_raises),
    ):
        events = await _collect(svc.stream(db=db, user=user, question_text="임플란트"))

    error_events = [ev for ev in events if ev["event"] == "error"]
    assert len(error_events) == 1
    err_data = json.loads(error_events[0]["data"])
    assert err_data["code"] == "OPENAI_TIMEOUT"
    assert "지연" in err_data["message"]


# ---------------------------------------------------------------------------
# PII 보호 테스트
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_does_not_log_question_text(caplog):
    """PII 원칙 — question_text가 structlog 이벤트에 포함되면 안 됨."""
    import logging

    svc = QAService()
    db = _make_db(log_id=99)
    user = _make_user()
    sensitive = "매우민감한질문텍스트"

    async def _mock_stream(query, on_complete):
        yield "답변"
        on_complete(TokenUsage(1, 2, 3, 0.0), "답변")

    rag_mock = _make_rag_module_mock(rule_answer=None, procedures=[])

    with (
        patch.dict("sys.modules", {"rag": MagicMock(), "rag.run_qa": rag_mock}),
        patch("api.src.services.qa_service.query_runner.ensure_initialized", new_callable=AsyncMock),
        patch("api.src.services.qa_service.query_runner.stream_rag_answer", side_effect=_mock_stream),
        caplog.at_level(logging.INFO),
    ):
        async for _ in svc.stream(db=db, user=user, question_text=sensitive):
            pass

    for record in caplog.records:
        assert sensitive not in record.getMessage(), "question_text가 로그에 노출되면 안 됨"


# ---------------------------------------------------------------------------
# qa_logs INSERT-then-UPDATE 패턴 테스트
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_inserts_immediately_then_updates():
    """요청 시작 시 즉시 INSERT, 종료 시 UPDATE — AC-4."""
    svc = QAService()
    db = _make_db(log_id=55)
    user = _make_user()

    async def _mock_stream(query, on_complete):
        yield "답변"
        on_complete(TokenUsage(1, 2, 3, 0.001), "답변")

    rag_mock = _make_rag_module_mock(rule_answer=None, procedures=[])

    with (
        patch.dict("sys.modules", {"rag": MagicMock(), "rag.run_qa": rag_mock}),
        patch("api.src.services.qa_service.query_runner.ensure_initialized", new_callable=AsyncMock),
        patch("api.src.services.qa_service.query_runner.stream_rag_answer", side_effect=_mock_stream),
    ):
        await _collect(svc.stream(db=db, user=user, question_text="치료비"))

    # add가 1회 호출됨 (INSERT)
    db.add.assert_called_once()
    added: QALog = db.add.call_args[0][0]
    assert isinstance(added, QALog)

    # commit이 2회 이상 호출됨 (INSERT commit + UPDATE commit — INSERT-then-UPDATE 패턴)
    assert db.commit.await_count >= 2

    # 스트림 완료 후 log row가 업데이트됨 (answer_text가 설정됨)
    assert added.answer_text is not None
    assert added.latency_ms is not None
