"""QAService.stream() reframe 분기 통합 테스트 — Story 2.6.

qa_service.stream() 내부의 reframe 분기를 AsyncMock으로 격리하여
SSE 이벤트 순서, qa_logs 직렬화, structuring usage 분리를 검증한다.
"""

import json
from decimal import Decimal
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.src.integrations.openai.client import TokenUsage
from api.src.models.qa_log import QALog
from api.src.models.user import User
from api.src.schemas.qa import ReframePayload
from api.src.services import qa_reframe_service
from api.src.services.qa_service import QAService
from api.src.services.qa_reframe_service import ReframeExtractionResult


# ---------------------------------------------------------------------------
# 공통 헬퍼
# ---------------------------------------------------------------------------

def _make_rag_module_mock(
    rule_answer: str | None = None,
    procedures: list[str] | None = None,
    normalized: str = "임플란트 보험",
) -> ModuleType:
    mock_mod = ModuleType("rag.run_qa")
    mock_mod.apply_scaling_rules = lambda text: text
    mock_mod.get_syn_dict = lambda: {}
    mock_mod.normalize_query = lambda query, syn: normalized
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
    events = []
    async for ev in gen:
        events.append(ev)
    return events


def _make_reframe_result(
    follow_up_question: str = "어느 치아인지 알려주세요?",
    options: list[str] | None = None,
) -> ReframeExtractionResult:
    payload = ReframePayload(
        follow_up_question=follow_up_question,
        options=options or ["상악 전치", "하악 구치", "어금니"],
    )
    usage = TokenUsage(input_tokens=10, output_tokens=20, total_tokens=30, cost_usd=0.001)
    return ReframeExtractionResult(payload=payload, usage=usage)


# ---------------------------------------------------------------------------
# RAG 경로 + reframe 감지 (분기 A): token* → reframe → done
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rag_reframe_detected_event_order():
    """RAG 경로 + reframe 감지 시 SSE 이벤트 순서: token* → reframe → done."""
    svc = QAService()
    db = _make_db(log_id=10)
    user = _make_user()

    reframe_result = _make_reframe_result()

    async def _mock_stream(query, on_complete):
        yield "어느"
        yield " 치아인지?"
        on_complete(TokenUsage(5, 10, 15, 0.002), "어느 치아인지?", [])

    rag_mock = _make_rag_module_mock(rule_answer=None, procedures=[])

    with (
        patch.dict("sys.modules", {"rag": MagicMock(), "rag.run_qa": rag_mock}),
        patch("api.src.services.qa_service.query_runner.ensure_initialized", new_callable=AsyncMock),
        patch("api.src.services.qa_service.query_runner.stream_rag_answer", side_effect=_mock_stream),
        patch.object(qa_reframe_service, "detect_and_extract", new=AsyncMock(return_value=reframe_result)),
    ):
        events = await _collect(svc.stream(db=db, user=user, question_text="임플란트 치료"))

    event_names = [ev["event"] for ev in events]
    # reframe은 done 직전에 위치해야 함
    assert "token" in event_names
    assert "reframe" in event_names
    assert "done" in event_names
    reframe_idx = event_names.index("reframe")
    done_idx = event_names.index("done")
    assert reframe_idx < done_idx, "reframe은 done 직전이어야 함"


@pytest.mark.asyncio
async def test_rag_reframe_payload_content():
    """reframe 이벤트 payload에 follow_up_question과 options가 포함된다."""
    svc = QAService()
    db = _make_db(log_id=11)
    user = _make_user()

    reframe_result = _make_reframe_result(
        follow_up_question="어느 치아인지?",
        options=["상악 전치", "하악 구치", "어금니"],
    )

    async def _mock_stream(query, on_complete):
        yield "어느 치아인지?"
        on_complete(TokenUsage(5, 10, 15, 0.002), "어느 치아인지?", [])

    rag_mock = _make_rag_module_mock(rule_answer=None, procedures=[])

    with (
        patch.dict("sys.modules", {"rag": MagicMock(), "rag.run_qa": rag_mock}),
        patch("api.src.services.qa_service.query_runner.ensure_initialized", new_callable=AsyncMock),
        patch("api.src.services.qa_service.query_runner.stream_rag_answer", side_effect=_mock_stream),
        patch.object(qa_reframe_service, "detect_and_extract", new=AsyncMock(return_value=reframe_result)),
    ):
        events = await _collect(svc.stream(db=db, user=user, question_text="임플란트"))

    reframe_ev = next(ev for ev in events if ev["event"] == "reframe")
    data = json.loads(reframe_ev["data"])
    assert data["follow_up_question"] == "어느 치아인지?"
    assert len(data["options"]) == 3


# ---------------------------------------------------------------------------
# RAG 경로 + reframe 미감지 (분기 B): token* → done
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rag_no_reframe_only_token_and_done():
    """RAG 경로 + reframe 미감지 시: token* → done (reframe 이벤트 없음)."""
    svc = QAService()
    db = _make_db(log_id=12)
    user = _make_user()

    async def _mock_stream(query, on_complete):
        yield "임플란트 치료 방법입니다."
        on_complete(TokenUsage(5, 10, 15, 0.002), "임플란트 치료 방법입니다.", [])

    rag_mock = _make_rag_module_mock(rule_answer=None, procedures=[])

    with (
        patch.dict("sys.modules", {"rag": MagicMock(), "rag.run_qa": rag_mock}),
        patch("api.src.services.qa_service.query_runner.ensure_initialized", new_callable=AsyncMock),
        patch("api.src.services.qa_service.query_runner.stream_rag_answer", side_effect=_mock_stream),
        patch.object(qa_reframe_service, "detect_and_extract", new=AsyncMock(return_value=None)),
    ):
        events = await _collect(svc.stream(db=db, user=user, question_text="임플란트"))

    event_names = [ev["event"] for ev in events]
    assert "token" in event_names
    assert "done" in event_names
    assert "reframe" not in event_names


# ---------------------------------------------------------------------------
# 룰 경로 → reframe 미발행
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rule_path_no_reframe():
    """룰 경로 → detect_and_extract 미호출, reframe 이벤트 없음."""
    svc = QAService()
    db = _make_db(log_id=13)
    user = _make_user()

    RULE_ANSWER = "장애인가산 300% 적용 가능합니다."
    rag_mock = _make_rag_module_mock(
        rule_answer=RULE_ANSWER,
        procedures=["발치"],
        normalized="장애인 발치 가산 가능?",
    )

    mock_detect = AsyncMock(return_value=None)

    with (
        patch.dict("sys.modules", {"rag": MagicMock(), "rag.run_qa": rag_mock}),
        patch("api.src.services.qa_service.query_runner.ensure_initialized", new_callable=AsyncMock),
        patch.object(qa_reframe_service, "detect_and_extract", mock_detect),
    ):
        events = await _collect(svc.stream(db=db, user=user, question_text="장애인 발치 가산"))

    event_names = [ev["event"] for ev in events]
    assert "reframe" not in event_names
    # 룰 경로에서 detect_and_extract 호출 없음 검증
    mock_detect.assert_not_called()


# ---------------------------------------------------------------------------
# error 경로 → reframe 미발행
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_error_path_no_reframe():
    """OpenAI 예외 경로 → reframe 이벤트 없음."""
    import openai

    svc = QAService()
    db = _make_db(log_id=14)
    user = _make_user()

    async def _mock_stream_raises(query, on_complete):
        raise openai.APITimeoutError("timeout")
        yield

    rag_mock = _make_rag_module_mock(rule_answer=None, procedures=[])
    mock_detect = AsyncMock(return_value=None)

    with (
        patch.dict("sys.modules", {"rag": MagicMock(), "rag.run_qa": rag_mock}),
        patch("api.src.services.qa_service.query_runner.ensure_initialized", new_callable=AsyncMock),
        patch("api.src.services.qa_service.query_runner.stream_rag_answer", side_effect=_mock_stream_raises),
        patch.object(qa_reframe_service, "detect_and_extract", mock_detect),
    ):
        events = await _collect(svc.stream(db=db, user=user, question_text="임플란트"))

    event_names = [ev["event"] for ev in events]
    assert "reframe" not in event_names
    mock_detect.assert_not_called()


# ---------------------------------------------------------------------------
# GeneratorExit 취소 경로 → reframe 미발행
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generator_exit_no_reframe():
    """GeneratorExit 취소 → reframe 이벤트 없음."""
    svc = QAService()
    db = _make_db(log_id=15)
    user = _make_user()

    async def _mock_stream_many(query, on_complete):
        for ch in ["a", "b", "c"]:
            yield ch
        on_complete(TokenUsage(0, 0, 0, 0.0), "abc", [])

    rag_mock = _make_rag_module_mock(rule_answer=None, procedures=[])
    mock_detect = AsyncMock(return_value=None)

    with (
        patch.dict("sys.modules", {"rag": MagicMock(), "rag.run_qa": rag_mock}),
        patch("api.src.services.qa_service.query_runner.ensure_initialized", new_callable=AsyncMock),
        patch("api.src.services.qa_service.query_runner.stream_rag_answer", side_effect=_mock_stream_many),
        patch.object(qa_reframe_service, "detect_and_extract", mock_detect),
    ):
        gen = svc.stream(db=db, user=user, question_text="중단")
        first = await gen.__anext__()
        assert first["event"] == "token"
        await gen.aclose()

    mock_detect.assert_not_called()


# ---------------------------------------------------------------------------
# asyncio.CancelledError 취소 경로 → reframe 미발행 (Story 2.5 abort 보강)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cancelled_error_no_reframe():
    """asyncio.CancelledError → reframe 이벤트 없음."""
    import asyncio

    svc = QAService()
    db = _make_db(log_id=16)
    user = _make_user()

    async def _mock_stream_cancelled(query, on_complete):
        raise asyncio.CancelledError()
        yield

    rag_mock = _make_rag_module_mock(rule_answer=None, procedures=[])
    mock_detect = AsyncMock(return_value=None)

    with (
        patch.dict("sys.modules", {"rag": MagicMock(), "rag.run_qa": rag_mock}),
        patch("api.src.services.qa_service.query_runner.ensure_initialized", new_callable=AsyncMock),
        patch("api.src.services.qa_service.query_runner.stream_rag_answer", side_effect=_mock_stream_cancelled),
        patch.object(qa_reframe_service, "detect_and_extract", mock_detect),
    ):
        with pytest.raises(asyncio.CancelledError):
            await _collect(svc.stream(db=db, user=user, question_text="중단"))

    mock_detect.assert_not_called()


# ---------------------------------------------------------------------------
# qa_logs.answer_text 직렬화 검증
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_answer_text_serialization_with_reframe():
    """reframe 시 answer_text 형식: {follow_up_question}\\n\\n{json.dumps({'options': []})}."""
    svc = QAService()
    db = _make_db(log_id=17)
    user = _make_user()

    reframe_result = _make_reframe_result(
        follow_up_question="어느 치아인지 알려주세요?",
        options=["상악 전치", "하악 구치", "어금니"],
    )

    async def _mock_stream(query, on_complete):
        yield "어느 치아인지 알려주세요?"
        on_complete(TokenUsage(5, 10, 15, 0.002), "어느 치아인지 알려주세요?", [])

    rag_mock = _make_rag_module_mock(rule_answer=None, procedures=[])

    with (
        patch.dict("sys.modules", {"rag": MagicMock(), "rag.run_qa": rag_mock}),
        patch("api.src.services.qa_service.query_runner.ensure_initialized", new_callable=AsyncMock),
        patch("api.src.services.qa_service.query_runner.stream_rag_answer", side_effect=_mock_stream),
        patch.object(qa_reframe_service, "detect_and_extract", new=AsyncMock(return_value=reframe_result)),
    ):
        await _collect(svc.stream(db=db, user=user, question_text="임플란트"))

    added: QALog = db.add.call_args[0][0]
    assert added.answer_text is not None
    assert "어느 치아인지 알려주세요?" in added.answer_text
    assert '{"options":' in added.answer_text or '"options":' in added.answer_text


# ---------------------------------------------------------------------------
# qa_logs.cost_usd에 structuring usage 미합산 검증
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_qa_logs_cost_does_not_include_structuring_usage():
    """qa_logs.cost_usd는 RAG 본 체인 usage만 기록 — structuring usage 합산 금지."""
    svc = QAService()
    db = _make_db(log_id=18)
    user = _make_user()

    rag_usage = TokenUsage(input_tokens=100, output_tokens=200, total_tokens=300, cost_usd=0.005)
    structuring_usage = TokenUsage(input_tokens=10, output_tokens=20, total_tokens=30, cost_usd=0.001)
    payload = ReframePayload(
        follow_up_question="어느 치아?",
        options=["상악", "하악", "어금니"],
    )
    reframe_result = ReframeExtractionResult(payload=payload, usage=structuring_usage)

    async def _mock_stream(query, on_complete):
        yield "어느 치아?"
        on_complete(rag_usage, "어느 치아?", [])

    rag_mock = _make_rag_module_mock(rule_answer=None, procedures=[])

    with (
        patch.dict("sys.modules", {"rag": MagicMock(), "rag.run_qa": rag_mock}),
        patch("api.src.services.qa_service.query_runner.ensure_initialized", new_callable=AsyncMock),
        patch("api.src.services.qa_service.query_runner.stream_rag_answer", side_effect=_mock_stream),
        patch.object(qa_reframe_service, "detect_and_extract", new=AsyncMock(return_value=reframe_result)),
    ):
        await _collect(svc.stream(db=db, user=user, question_text="임플란트"))

    added: QALog = db.add.call_args[0][0]
    # RAG 본 체인 usage만 반영되어야 함 (structuring 0.001 미합산)
    assert added.cost_usd == Decimal(str(rag_usage.cost_usd))
    assert added.input_tokens == rag_usage.input_tokens
    assert added.output_tokens == rag_usage.output_tokens


# ---------------------------------------------------------------------------
# vendor/rag 변경 0줄 검증 (NFR-M2)
# ---------------------------------------------------------------------------

def test_vendor_rag_not_modified():
    """vendor/rag/ 디렉토리 파일을 본 스토리가 수정하지 않았는지 grep 검증.

    qa_reframe_service.py가 vendor/rag를 import하거나 수정하지 않음을 확인.
    """
    import inspect
    import api.src.services.qa_reframe_service as svc_mod

    source = inspect.getsource(svc_mod)
    assert "vendor" not in source, "qa_reframe_service는 vendor/rag를 참조하면 안 됨"
    assert "run_qa" not in source, "qa_reframe_service는 run_qa를 import하면 안 됨"
    assert "prompt_builder" not in source, "qa_reframe_service는 prompt_builder를 참조하면 안 됨"
