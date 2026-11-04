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


@pytest.fixture(autouse=True)
def _mute_admin_failure_alert():
    """실패 경로에서 관리자 알림 훅이 **진짜 DB** 를 열지 않게 막는다.

    이 파일이 보는 것은 SSE 이벤트 규약이지 알림톡이 아니다. 훅을 그대로 두면
    `async_session_factory` 가 postgres 에 붙으려다 실패하고(단위 테스트엔 DB 가 없다),
    삼켜지긴 해도 접속 재시도로 느려지고 로그에 긴 트레이스백이 쌓인다.
    알림 로직 자체는 `test_qa_alert_service.py` 가 따로 본다.
    """
    with patch.object(QAService, "_notify_admin_on_failure_burst", new=AsyncMock()):
        yield


@pytest.fixture(autouse=True)
def _stub_synonyms():
    """동의어 dict 조회를 빈 dict 로 고정한다 (이 파일이 보는 것은 SSE 이벤트 규약).

    격리 목적도 있다 — ``patch.dict("sys.modules", ...)`` 블록 안에서 synonym_service 를
    처음 import 하면 블록을 벗어날 때 스냅샷 복원으로 sys.modules 에서 다시 빠진다.
    그러면 다음 테스트가 SQLAlchemy 모델을 두 번 선언해
    "Table 'synonym_groups' is already defined" 로 깨진다(이 파일만 단독 실행할 때).
    """
    with patch(
        "api.src.services.qa_service.query_runner.get_synonyms_dict",
        new=AsyncMock(return_value={}),
    ):
        yield


# ---------------------------------------------------------------------------
# rag.run_qa sys.modules 모킹 픽스처
# ---------------------------------------------------------------------------

def _make_rag_module_mock(
    rule_answer: str | None = None,
    procedures: list[str] | None = None,
    periodontal_result=None,
):
    """rag.run_qa 모듈을 모킹한 ModuleType을 반환한다."""
    mock_mod = ModuleType("rag.run_qa")
    mock_mod.apply_scaling_rules = lambda text: text
    mock_mod.get_syn_dict = lambda: {}
    mock_mod.normalize_query = lambda query, syn: query
    mock_mod.generate_rule_answer = lambda query: rule_answer
    mock_mod.extract_procedures = lambda query: procedures or []
    # 게시판 #139/#140 — 치주낭측정 결정형 우회. 기본 None(미매칭 → 기존 분기 유지).
    mock_mod.get_periodontal_result = lambda query: periodontal_result
    return mock_mod


def _make_user(user_id: int = 1, subscription_status: str = "pro") -> User:
    user = MagicMock(spec=User)
    user.id = user_id
    user.subscription_status = subscription_status
    user.current_session_id = None
    user.admin_grade = "master"
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

    async def _mock_stream(query, on_complete, on_thread_complete=None, search_query=None, history_block=""):
        yield "안녕"
        yield "하세요"
        on_complete(TokenUsage(5, 10, 15, 0.002), "안녕하세요", [], None)

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
# 치주낭측정 경로 테스트 (게시판 #139/#140)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_periodontal_path_yields_token_and_done():
    """치주낭 경로: RAG 처럼 token 다회 + done. rule_matched=True, 검색 없음(docs 빈 리스트).

    치주낭은 최우선 분기 — 장애인/RAG 보다 먼저 잡히고, 장애인 전용 rule_matched
    이벤트(procedure_count)는 쏘지 않는다.
    """
    svc = QAService()
    db = _make_db(log_id=15)
    user = _make_user()

    async def _mock_perio_stream(raw_query, count, detail, on_complete, on_thread_complete=None):
        yield "1.5"
        yield "회"
        on_complete(TokenUsage(12, 3, 15, 0.001), "1.5회", [], "PERIO_PROMPT")

    # 치주낭 매칭 → (count, detail). 장애인 룰도 있으나 치주낭이 최우선이어야 함.
    rag_mock = _make_rag_module_mock(
        rule_answer="장애인가산...",
        procedures=["발치"],
        periodontal_result=(1.5, {"방식": "2분의1악 병합"}),
    )
    rag_mock.normalize_query = lambda query, syn: "장애인 가산 11~17 치주낭 몇회"

    with (
        patch.dict("sys.modules", {"rag": MagicMock(), "rag.run_qa": rag_mock}),
        patch("api.src.services.qa_service.query_runner.ensure_initialized", new_callable=AsyncMock),
        patch(
            "api.src.services.qa_service.query_runner.stream_periodontal_answer",
            side_effect=_mock_perio_stream,
        ),
    ):
        events = await _collect(
            svc.stream(db=db, user=user, question_text="11~17 치주낭측정검사 몇회야?")
        )

    event_names = [ev["event"] for ev in events]
    # 치주낭은 rule_matched 이벤트를 쏘지 않는다 — token/done 만.
    assert "rule_matched" not in event_names
    assert "token" in event_names
    assert "done" in event_names
    assert "error" not in event_names

    tokens = [json.loads(ev["data"])["delta"] for ev in events if ev["event"] == "token"]
    assert "".join(tokens) == "1.5회"

    done_data = json.loads(next(ev["data"] for ev in events if ev["event"] == "done"))
    assert done_data["qa_log_id"] == 15
    assert done_data["total_tokens"] == 15
    # 결정형 우회이므로 rule_matched=True (치주낭도 규칙 기반 집계)
    assert done_data["rule_matched"] is True


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

    async def _mock_stream_raises(query, on_complete, on_thread_complete=None, search_query=None, history_block=""):
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


@pytest.mark.asyncio
async def test_stream_first_token_timeout_yields_slow_question_error():
    """게시판 #112 후속 — 첫 토큰 45초 상한 초과 시 SLOW_QUESTION error 이벤트 +
    status='error' + latency_ms 기록(리퍼 고아와 구분)."""
    from api.src.rag_integration.query_runner import FirstTokenTimeoutError

    svc = QAService()
    db = _make_db(log_id=71)
    user = _make_user()

    async def _mock_stream_timeout(query, on_complete, on_thread_complete=None, search_query=None, history_block=""):
        raise FirstTokenTimeoutError("첫 토큰이 45초 내 도착하지 않음")
        yield  # make it a generator

    rag_mock = _make_rag_module_mock(rule_answer=None, procedures=[])

    with (
        patch.dict("sys.modules", {"rag": MagicMock(), "rag.run_qa": rag_mock}),
        patch("api.src.services.qa_service.query_runner.ensure_initialized", new_callable=AsyncMock),
        patch("api.src.services.qa_service.query_runner.stream_rag_answer", side_effect=_mock_stream_timeout),
    ):
        events = await _collect(svc.stream(db=db, user=user, question_text="전악 치식 질문"))

    error_events = [ev for ev in events if ev["event"] == "error"]
    assert len(error_events) == 1
    err_data = json.loads(error_events[0]["data"])
    assert err_data["code"] == "SLOW_QUESTION"
    # 2026-09-30 — 문구에서 "질문이 복잡해" 를 뺐다(장애 원인이 질문이 아니었다).
    # 사용자 탓으로 읽히지 않으면서 "다시 시도" 를 안내하는지만 본다.
    assert "질문이 복잡" not in err_data["message"]
    assert "다시 시도" in err_data["message"]

    added: QALog = db.add.call_args[0][0]
    assert added.status == "error"
    # 리퍼가 청소하는 in_progress 고아(latency NULL)와 달리 latency_ms 가 기록돼야 한다.
    assert added.latency_ms is not None


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

    async def _mock_stream(query, on_complete, on_thread_complete=None, search_query=None, history_block=""):
        yield "답변"
        on_complete(TokenUsage(1, 2, 3, 0.0), "답변", [], None)

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

    async def _mock_stream(query, on_complete, on_thread_complete=None, search_query=None, history_block=""):
        yield "답변"
        on_complete(TokenUsage(1, 2, 3, 0.001), "답변", [])

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


# ---------------------------------------------------------------------------
# Story 2.5: status 컬럼 검증
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_success_sets_status_completed():
    """성공 경로: log.status == 'completed'."""
    svc = QAService()
    db = _make_db(log_id=60)
    user = _make_user()

    async def _mock_stream(query, on_complete, on_thread_complete=None, search_query=None, history_block=""):
        yield "답변"
        on_complete(TokenUsage(1, 2, 3, 0.001), "답변", [])

    rag_mock = _make_rag_module_mock(rule_answer=None, procedures=[])

    with (
        patch.dict("sys.modules", {"rag": MagicMock(), "rag.run_qa": rag_mock}),
        patch("api.src.services.qa_service.query_runner.ensure_initialized", new_callable=AsyncMock),
        patch("api.src.services.qa_service.query_runner.stream_rag_answer", side_effect=_mock_stream),
    ):
        await _collect(svc.stream(db=db, user=user, question_text="치료비"))

    added: QALog = db.add.call_args[0][0]
    assert added.status == "completed"


@pytest.mark.asyncio
async def test_stream_exception_sets_status_error():
    """Exception 경로: log.status == 'error'."""
    import openai

    svc = QAService()
    db = _make_db(log_id=70)
    user = _make_user()

    async def _mock_stream_raises(query, on_complete, on_thread_complete=None, search_query=None, history_block=""):
        raise openai.APITimeoutError("timeout")
        yield  # make it a generator

    rag_mock = _make_rag_module_mock(rule_answer=None, procedures=[])

    with (
        patch.dict("sys.modules", {"rag": MagicMock(), "rag.run_qa": rag_mock}),
        patch("api.src.services.qa_service.query_runner.ensure_initialized", new_callable=AsyncMock),
        patch("api.src.services.qa_service.query_runner.stream_rag_answer", side_effect=_mock_stream_raises),
    ):
        await _collect(svc.stream(db=db, user=user, question_text="임플란트"))

    added: QALog = db.add.call_args[0][0]
    assert added.status == "error"


@pytest.mark.asyncio
async def test_stream_cancelled_error_sets_status_aborted():
    """Story 2.5 review issue 2: asyncio.CancelledError 경로도 status='aborted'.

    FastAPI/Starlette/sse-starlette가 클라이언트 abort 시 generator로 전달하는
    asyncio.CancelledError는 BaseException 하위라 except Exception에 잡히지 않는다.
    명시적 except로 status='aborted' commit이 보장되어야 한다.
    """
    import asyncio

    svc = QAService()
    db = _make_db(log_id=80)
    user = _make_user()

    async def _mock_stream_cancelled(query, on_complete, on_thread_complete=None, search_query=None, history_block=""):
        raise asyncio.CancelledError()
        yield  # make it a generator

    rag_mock = _make_rag_module_mock(rule_answer=None, procedures=[])

    with (
        patch.dict("sys.modules", {"rag": MagicMock(), "rag.run_qa": rag_mock}),
        patch("api.src.services.qa_service.query_runner.ensure_initialized", new_callable=AsyncMock),
        patch("api.src.services.qa_service.query_runner.stream_rag_answer", side_effect=_mock_stream_cancelled),
    ):
        with pytest.raises(asyncio.CancelledError):
            await _collect(svc.stream(db=db, user=user, question_text="중단된 질문"))

    added: QALog = db.add.call_args[0][0]
    assert added.status == "aborted"
    assert added.latency_ms is not None
    # abort는 error 이벤트로 기록되지 않아야 함 — db.commit이 INSERT + abort UPDATE 두 번만 호출
    assert db.commit.await_count >= 2


@pytest.mark.asyncio
async def test_stream_aclose_sets_status_aborted():
    """Story 2.5 review issue 2 보강: 소비자 aclose()(GeneratorExit) 경로도 status='aborted'."""
    svc = QAService()
    db = _make_db(log_id=85)
    user = _make_user()

    async def _mock_stream_many(query, on_complete, on_thread_complete=None, search_query=None, history_block=""):
        for ch in ["a", "b", "c"]:
            yield ch
        on_complete(TokenUsage(0, 0, 0, 0.0), "abc", [])

    rag_mock = _make_rag_module_mock(rule_answer=None, procedures=[])

    with (
        patch.dict("sys.modules", {"rag": MagicMock(), "rag.run_qa": rag_mock}),
        patch("api.src.services.qa_service.query_runner.ensure_initialized", new_callable=AsyncMock),
        patch("api.src.services.qa_service.query_runner.stream_rag_answer", side_effect=_mock_stream_many),
    ):
        gen = svc.stream(db=db, user=user, question_text="중단")
        first = await gen.__anext__()
        assert first["event"] == "token"
        await gen.aclose()

    added: QALog = db.add.call_args[0][0]
    assert added.status == "aborted"
    assert added.latency_ms is not None


# ---------------------------------------------------------------------------
# 대화 이어가기 (#149) + 2026-11-03 적대적 검수 P0-1 · P0-3 · P1-2 · P1-4 · P1-7
#
# 전제: 이전 대화는 **서버가 검증해 읽어온 턴**(ConversationTurn)으로 들어온다.
# 브라우저가 보낸 과거 답변 문자열은 더 이상 stream() 에 들어오지 않는다(검수 P0-2).
# ---------------------------------------------------------------------------

import asyncio  # noqa: E402

from api.src.services.chat_history_service import ConversationTurn  # noqa: E402

HISTORY_TURNS = [
    ConversationTurn(question="스케일링 산정 기준 알려주세요", answer="3분의1악당 1회입니다."),
]


def _history_cfg(enabled: bool = True):
    from api.src.services.runtime_config_service import ChatHistoryConfig

    return ChatHistoryConfig(
        enabled=enabled, max_turns=5, max_tokens=3000, rewriter_model="gpt-6-luna"
    )


def _rewrite_result(related: bool, search_query: str, usage=None):
    from api.src.rag_integration.query_rewriter import (
        RewriteResult,
        RewriteStatus,
        UsageState,
    )

    # 재수정 P1-5 — ``called`` 불리언은 ``status`` 로 교체됐다(호출 결말을 구분해 기록).
    return RewriteResult(
        related=related,
        search_query=search_query,
        status=RewriteStatus.SUCCESS if related else RewriteStatus.UNRELATED,
        usage=usage,
        usage_state=UsageState.MEASURED,
    )


def _rag_stream_capture(seen: dict, tokens=("답변",), usage=None, docs=None, prompt=None):
    """stream_rag_answer 대역 — 받은 인자를 seen 에 기록하고 토큰을 흘린다."""

    async def _mock_stream(
        query, on_complete, on_thread_complete=None, search_query=None, history_block=""
    ):
        seen["query"] = query
        seen["search_query"] = search_query
        seen["history_block"] = history_block
        seen["on_thread_complete"] = on_thread_complete
        for t in tokens:
            yield t
        on_complete(
            usage or TokenUsage(1, 2, 3, 0.001),
            "".join(tokens),
            docs if docs is not None else [],
            prompt,
        )

    return _mock_stream


@pytest.mark.asyncio
async def test_stream_clarify_path_skips_rag_and_asks_back():
    """이전 대화가 있는데 판정이 "안 이어짐" + 조각 질문이면 RAG 를 타지 않고 되묻는다.

    클라이언트가 지적한 구멍(판정 실패 시 조각 질문이 그대로 검색되는 것)을 막는 경로다.
    되묻기 응답은 answer_kind='clarification' 으로 **구조적으로** 표시된다(검수 P1-7).
    """
    from api.src.rag_integration.question_completeness import (
        ANSWER_KIND_CLARIFICATION,
        CLARIFY_MESSAGE,
    )

    svc = QAService()
    db = _make_db(log_id=50)
    user = _make_user()
    rag_mock = _make_rag_module_mock(rule_answer=None, procedures=[])
    rag_stream = MagicMock()

    with (
        patch.dict("sys.modules", {"rag": MagicMock(), "rag.run_qa": rag_mock}),
        patch("api.src.services.qa_service.query_runner.ensure_initialized", new_callable=AsyncMock),
        patch("api.src.services.qa_service.query_runner.stream_rag_answer", rag_stream),
        patch(
            "api.src.services.qa_service.runtime_config_service.get_chat_history_config",
            new=AsyncMock(return_value=_history_cfg()),
        ),
        patch(
            "api.src.rag_integration.query_rewriter.rewrite_query",
            new=AsyncMock(return_value=_rewrite_result(False, "하얀색?")),
        ),
    ):
        events = await _collect(
            svc.stream(
                db=db,
                user=user,
                question_text="하얀색?",
                redis_runtime=MagicMock(),
                history_turns=HISTORY_TURNS,
            )
        )

    assert [ev["event"] for ev in events] == ["token", "done"]
    assert json.loads(events[0]["data"])["delta"] == CLARIFY_MESSAGE
    rag_stream.assert_not_called()  # 검색·답변 생성을 아예 하지 않는다

    added: QALog = db.add.call_args[0][0]
    assert added.answer_text == CLARIFY_MESSAGE
    assert added.status == "completed"
    assert added.answer_kind == ANSWER_KIND_CLARIFICATION
    assert added.retrieved_docs == []
    assert added.prompt_text is None


@pytest.mark.asyncio
async def test_clarify_does_not_restore_question_quota():
    """되묻기도 질문 1회 차감 유지 — 2026-11-03 사용자 확정 정책.

    환급·카운터 복원 로직이 들어오면 이 테스트가 깨진다(의도적 고정).
    stream() 은 quota 키를 쓰지 않으며, 차감은 preflight 에서 이미 끝났다.
    """
    svc = QAService()
    db = _make_db(log_id=60)
    user = _make_user()
    redis_quota = AsyncMock()
    rag_mock = _make_rag_module_mock(rule_answer=None, procedures=[])

    with (
        patch.dict("sys.modules", {"rag": MagicMock(), "rag.run_qa": rag_mock}),
        patch("api.src.services.qa_service.query_runner.ensure_initialized", new_callable=AsyncMock),
        patch("api.src.services.qa_service.query_runner.stream_rag_answer", MagicMock()),
        patch(
            "api.src.services.qa_service.runtime_config_service.get_chat_history_config",
            new=AsyncMock(return_value=_history_cfg()),
        ),
        patch(
            "api.src.rag_integration.query_rewriter.rewrite_query",
            new=AsyncMock(return_value=_rewrite_result(False, "하얀색?")),
        ),
    ):
        await _collect(
            svc.stream(
                db=db,
                user=user,
                question_text="하얀색?",
                redis_quota=redis_quota,
                redis_runtime=MagicMock(),
                history_turns=HISTORY_TURNS,
            )
        )

    # 차감을 되돌리는 연산이 하나도 없어야 한다.
    for forbidden in ("decr", "decrby", "delete"):
        assert not getattr(redis_quota, forbidden).await_count, (
            "되묻기에서 quota 를 되돌리면 안 된다(정책 확정): " + forbidden
        )
    # set 은 이상탐지 기록용으로 쓰인다 — 다만 질문 횟수 키를 덮어쓰면 안 된다.
    for call in redis_quota.set.await_args_list:
        key = str(call.args[0]) if call.args else ""
        assert not key.startswith("quota:user:"), (
            "질문 횟수 키를 다시 쓰면 차감이 무력화된다: " + key
        )


@pytest.mark.asyncio
async def test_runtime_config_failure_asks_back_for_fragment():
    """검수 P0-3 — 설정 조회(Redis)가 터져도 조각 질문은 되묻는다. RAG 미호출.

    예전에는 설정 실패 시 "되묻기 없음" 으로 떨어져 안전장치가 꺼진 채 조각 질문이
    그대로 검색됐다.
    """
    from api.src.rag_integration.question_completeness import CLARIFY_MESSAGE

    svc = QAService()
    db = _make_db(log_id=61)
    user = _make_user()
    rag_stream = MagicMock()
    rag_mock = _make_rag_module_mock(rule_answer=None, procedures=[])
    rewrite_mock = AsyncMock()

    with (
        patch.dict("sys.modules", {"rag": MagicMock(), "rag.run_qa": rag_mock}),
        patch("api.src.services.qa_service.query_runner.ensure_initialized", new_callable=AsyncMock),
        patch("api.src.services.qa_service.query_runner.stream_rag_answer", rag_stream),
        patch(
            "api.src.services.qa_service.runtime_config_service.get_chat_history_config",
            new=AsyncMock(side_effect=RuntimeError("Redis 다운")),
        ),
        patch("api.src.rag_integration.query_rewriter.rewrite_query", new=rewrite_mock),
    ):
        events = await _collect(
            svc.stream(
                db=db,
                user=user,
                question_text="하얀색?",
                redis_runtime=MagicMock(),
                history_turns=HISTORY_TURNS,
            )
        )

    assert json.loads(events[0]["data"])["delta"] == CLARIFY_MESSAGE
    rag_stream.assert_not_called()
    rewrite_mock.assert_not_awaited()  # 설정을 못 읽었으니 판단 호출도 못 한다


@pytest.mark.asyncio
async def test_runtime_config_failure_answers_self_contained_question():
    """검수 P0-3 — 설정 실패 + 완결된 독립 질문이면 기존 단일 질문 경로로 답한다."""
    svc = QAService()
    db = _make_db(log_id=62)
    user = _make_user()
    seen: dict = {}
    rag_mock = _make_rag_module_mock(rule_answer=None, procedures=[])

    with (
        patch.dict("sys.modules", {"rag": MagicMock(), "rag.run_qa": rag_mock}),
        patch("api.src.services.qa_service.query_runner.ensure_initialized", new_callable=AsyncMock),
        patch(
            "api.src.services.qa_service.query_runner.stream_rag_answer",
            side_effect=_rag_stream_capture(seen),
        ),
        patch(
            "api.src.services.qa_service.runtime_config_service.get_chat_history_config",
            new=AsyncMock(side_effect=RuntimeError("Redis 다운")),
        ),
    ):
        events = await _collect(
            svc.stream(
                db=db,
                user=user,
                question_text="본인부담금 계산 어떻게 하나요",
                redis_runtime=MagicMock(),
                history_turns=HISTORY_TURNS,
            )
        )

    assert [ev["event"] for ev in events] == ["token", "done"]
    assert seen["history_block"] == ""     # 맥락은 붙이지 않는다
    assert seen["search_query"] is None    # 원문으로 검색 = 기존 단일 질문 동작


@pytest.mark.asyncio
async def test_no_history_with_redis_failure_keeps_first_question_behavior():
    """검수 P0-3 — 이전 대화가 없으면 설정 실패와 무관하게 기존 첫 질문 동작."""
    svc = QAService()
    db = _make_db(log_id=63)
    user = _make_user()
    seen: dict = {}
    rag_mock = _make_rag_module_mock(rule_answer=None, procedures=[])
    cfg_mock = AsyncMock(side_effect=RuntimeError("Redis 다운"))

    with (
        patch.dict("sys.modules", {"rag": MagicMock(), "rag.run_qa": rag_mock}),
        patch("api.src.services.qa_service.query_runner.ensure_initialized", new_callable=AsyncMock),
        patch(
            "api.src.services.qa_service.query_runner.stream_rag_answer",
            side_effect=_rag_stream_capture(seen),
        ),
        patch(
            "api.src.services.qa_service.runtime_config_service.get_chat_history_config",
            new=cfg_mock,
        ),
    ):
        events = await _collect(
            svc.stream(
                db=db,
                user=user,
                question_text="하얀색?",
                redis_runtime=MagicMock(),
                history_turns=None,
            )
        )

    assert [ev["event"] for ev in events] == ["token", "done"]
    assert seen["history_block"] == ""
    cfg_mock.assert_not_awaited()  # 설정을 읽을 일 자체가 없다


@pytest.mark.asyncio
async def test_stream_related_followup_uses_completed_search_query_and_history():
    """이어지는 후속 질문: 완성된 검색어로 검색하고 프롬프트에 이전 대화가 붙는다.

    이 경로가 #149 의 본 기능이다. 호출 규약이 깨지면 여기서 먼저 터진다
    (2026-11-02 "not enough values to unpack" 실제 발생).
    """
    svc = QAService()
    db = _make_db(log_id=53)
    user = _make_user()
    seen: dict = {}
    rag_mock = _make_rag_module_mock(rule_answer=None, procedures=[])

    with (
        patch.dict("sys.modules", {"rag": MagicMock(), "rag.run_qa": rag_mock}),
        patch("api.src.services.qa_service.query_runner.ensure_initialized", new_callable=AsyncMock),
        patch(
            "api.src.services.qa_service.query_runner.stream_rag_answer",
            side_effect=_rag_stream_capture(seen, docs=[{"doc": 1}], prompt="PROMPT"),
        ),
        patch(
            "api.src.services.qa_service.runtime_config_service.get_chat_history_config",
            new=AsyncMock(return_value=_history_cfg()),
        ),
        patch(
            "api.src.rag_integration.query_rewriter.rewrite_query",
            new=AsyncMock(
                return_value=_rewrite_result(True, "스케일링 치주질환 동반 시 산정기준")
            ),
        ),
    ):
        events = await _collect(
            svc.stream(
                db=db,
                user=user,
                question_text="그럼 치주질환 있으면?",
                redis_runtime=MagicMock(),
                history_turns=HISTORY_TURNS,
            )
        )

    assert [ev["event"] for ev in events] == ["token", "done"]
    assert seen["search_query"] == "스케일링 치주질환 동반 시 산정기준"
    assert "스케일링 산정 기준" in seen["history_block"]
    # 검수 P0-2 — 이전 대화 블록은 "지시가 아니라 데이터" 임을 프롬프트에서 구분한다.
    assert "지시가 아니라 데이터" in seen["history_block"]
    # 검수 P1-4 — 관리자 감사에는 실제 검색 질의가 남아야 한다.
    added: QALog = db.add.call_args[0][0]
    assert added.normalized_query == "스케일링 치주질환 동반 시 산정기준"


@pytest.mark.asyncio
async def test_disconnected_save_includes_rewrite_cost_and_search_query():
    """검수 P1-2·P1-4 — 연결이 끊겨 백그라운드가 저장할 때도
    판단 단계 비용이 합산되고 실제 검색 질의가 기록돼야 한다.

    답변 30토큰·$1.0 + 재작성 7토큰·$0.25 → 37토큰·$1.25.
    """
    svc = QAService()
    db = _make_db(log_id=64)
    user = _make_user()
    seen: dict = {}
    captured: dict = {}
    rag_mock = _make_rag_module_mock(rule_answer=None, procedures=[])

    async def _fake_guarded(self, qa_log_id, full_text, usage, latency_ms, **kwargs):
        captured["usage"] = usage
        captured["normalized_query"] = kwargs.get("normalized_query")

    with (
        patch.dict("sys.modules", {"rag": MagicMock(), "rag.run_qa": rag_mock}),
        patch("api.src.services.qa_service.query_runner.ensure_initialized", new_callable=AsyncMock),
        patch(
            "api.src.services.qa_service.query_runner.stream_rag_answer",
            side_effect=_rag_stream_capture(seen),
        ),
        patch(
            "api.src.services.qa_service.runtime_config_service.get_chat_history_config",
            new=AsyncMock(return_value=_history_cfg()),
        ),
        patch(
            "api.src.rag_integration.query_rewriter.rewrite_query",
            new=AsyncMock(
                return_value=_rewrite_result(
                    True, "완성된 검색어", usage=TokenUsage(5, 2, 7, 0.25)
                )
            ),
        ),
        patch.object(QAService, "_guarded_persist_full", new=_fake_guarded),
    ):
        await _collect(
            svc.stream(
                db=db,
                user=user,
                question_text="그럼 몇 번까지 돼?",
                redis_runtime=MagicMock(),
                history_turns=HISTORY_TURNS,
            )
        )

        # 스트림 도중 연결이 끊긴 상황 재현 — 생성 스레드가 완성 답변을 넘긴다.
        on_thread_complete = seen["on_thread_complete"]
        assert on_thread_complete is not None
        on_thread_complete("완성 답변", TokenUsage(20, 10, 30, 1.0), [], "PROMPT")
        await asyncio.sleep(0.05)  # 스케줄된 저장 코루틴 소화

    assert captured["usage"].total_tokens == 37
    assert captured["usage"].cost_usd == pytest.approx(1.25)
    assert captured["normalized_query"] == "완성된 검색어"


@pytest.mark.asyncio
async def test_stream_history_disabled_behaves_like_single_question():
    """킬 스위치를 끄면 이전 대화·판정·되묻기 전부 없이 예전 동작으로 돌아간다."""
    svc = QAService()
    db = _make_db(log_id=54)
    user = _make_user()
    rewrite_mock = AsyncMock()
    seen: dict = {}
    rag_mock = _make_rag_module_mock(rule_answer=None, procedures=[])

    with (
        patch.dict("sys.modules", {"rag": MagicMock(), "rag.run_qa": rag_mock}),
        patch("api.src.services.qa_service.query_runner.ensure_initialized", new_callable=AsyncMock),
        patch(
            "api.src.services.qa_service.query_runner.stream_rag_answer",
            side_effect=_rag_stream_capture(seen),
        ),
        patch(
            "api.src.services.qa_service.runtime_config_service.get_chat_history_config",
            new=AsyncMock(return_value=_history_cfg(enabled=False)),
        ),
        patch("api.src.rag_integration.query_rewriter.rewrite_query", new=rewrite_mock),
    ):
        events = await _collect(
            svc.stream(
                db=db,
                user=user,
                question_text="하얀색?",
                redis_runtime=MagicMock(),
                history_turns=HISTORY_TURNS,
            )
        )

    assert [ev["event"] for ev in events] == ["token", "done"]
    rewrite_mock.assert_not_awaited()
    assert seen["search_query"] is None  # 원문으로 검색
    assert seen["history_block"] == ""


@pytest.mark.asyncio
async def test_stream_records_history_context_key_for_replay_guard():
    """검수 P0-1 — 답변 행에 대화 맥락 지문이 남아야 재생 비교가 가능하다."""
    svc = QAService()
    db = _make_db(log_id=65)
    user = _make_user()
    seen: dict = {}
    rag_mock = _make_rag_module_mock(rule_answer=None, procedures=[])

    with (
        patch.dict("sys.modules", {"rag": MagicMock(), "rag.run_qa": rag_mock}),
        patch("api.src.services.qa_service.query_runner.ensure_initialized", new_callable=AsyncMock),
        patch(
            "api.src.services.qa_service.query_runner.stream_rag_answer",
            side_effect=_rag_stream_capture(seen),
        ),
        patch(
            "api.src.services.qa_service.runtime_config_service.get_chat_history_config",
            new=AsyncMock(return_value=_history_cfg()),
        ),
        patch(
            "api.src.rag_integration.query_rewriter.rewrite_query",
            new=AsyncMock(return_value=_rewrite_result(True, "완성된 검색어")),
        ),
    ):
        await _collect(
            svc.stream(
                db=db,
                user=user,
                question_text="그럼 몇 번까지 돼?",
                redis_runtime=MagicMock(),
                history_turns=HISTORY_TURNS,
                history_context_key="ctx-abc",
            )
        )

    added: QALog = db.add.call_args[0][0]
    assert added.history_context_key == "ctx-abc"


# ---------------------------------------------------------------------------
# 이전 대화를 요청했지만 검증 결과가 0개인 경우 — 재수정 P0-3
#
# REJECTED = "맥락 id 를 보냈는데 전부 거부됨"(다른 사용자 id / 삭제된 id /
# 오류·미전달·되묻기 턴). 이것을 "맥락 없는 첫 질문"(NONE)으로 취급하면 조각 질문이
# 그대로 RAG 로 가 엉뚱한 항목의 청구 기준이 나간다.
# ---------------------------------------------------------------------------


def _rejected_stream_kwargs(question: str, **extra):
    from api.src.services.chat_history_service import HistoryState

    base = dict(
        question_text=question,
        redis_runtime=MagicMock(),
        history_turns=[],                       # 전부 거부 → 쓸 턴이 없다
        history_context_key=None,               # 지문도 없다
        history_state=HistoryState.REJECTED,
    )
    base.update(extra)
    return base


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fragment",
    [
        "몇 번까지 돼?",          # 수치만 묻는 맥락 의존
        "65세 미만의 경우는?",     # 나이 조건만
        "그렇게 하면 돼요?",       # 지시어
        "하얀색?",                # 주제 없는 2어절 이하
    ],
)
async def test_rejected_history_fragment_asks_back_without_rag(fragment: str):
    """거부된 맥락 + 조각 질문 → 되묻기. RAG 검색·답변 생성 0회."""
    from api.src.rag_integration.question_completeness import (
        ANSWER_KIND_CLARIFICATION,
        CLARIFY_MESSAGE,
    )

    svc = QAService()
    db = _make_db(log_id=70)
    user = _make_user()
    rag_stream = MagicMock()
    rag_mock = _make_rag_module_mock(rule_answer=None, procedures=[])
    rewrite_mock = AsyncMock()

    with (
        patch.dict("sys.modules", {"rag": MagicMock(), "rag.run_qa": rag_mock}),
        patch("api.src.services.qa_service.query_runner.ensure_initialized", new_callable=AsyncMock),
        patch("api.src.services.qa_service.query_runner.stream_rag_answer", rag_stream),
        patch(
            "api.src.services.qa_service.runtime_config_service.get_chat_history_config",
            new=AsyncMock(return_value=_history_cfg()),
        ),
        patch("api.src.rag_integration.query_rewriter.rewrite_query", new=rewrite_mock),
    ):
        events = await _collect(svc.stream(db=db, user=user, **_rejected_stream_kwargs(fragment)))

    assert [ev["event"] for ev in events] == ["token", "done"]
    assert json.loads(events[0]["data"])["delta"] == CLARIFY_MESSAGE
    rag_stream.assert_not_called()          # RAG 미호출
    rewrite_mock.assert_not_awaited()       # 넣을 맥락이 없으니 판단 호출도 0회 (비용 0)

    added: QALog = db.add.call_args[0][0]
    assert added.answer_kind == ANSWER_KIND_CLARIFICATION
    # 지문은 없다 — 이 되묻기 턴이 재생 후보가 되지 않게 한다.
    assert added.history_context_key is None


@pytest.mark.asyncio
async def test_rejected_history_complete_question_uses_single_question_path():
    """거부된 맥락 + 완결된 독립 질문 → 기존 단일 질문 경로로 정상 처리."""
    svc = QAService()
    db = _make_db(log_id=71)
    user = _make_user()
    seen: dict = {}
    rag_mock = _make_rag_module_mock(rule_answer=None, procedures=[])
    rewrite_mock = AsyncMock()

    with (
        patch.dict("sys.modules", {"rag": MagicMock(), "rag.run_qa": rag_mock}),
        patch("api.src.services.qa_service.query_runner.ensure_initialized", new_callable=AsyncMock),
        patch(
            "api.src.services.qa_service.query_runner.stream_rag_answer",
            _rag_stream_capture(seen, tokens=("임플란트는 ",)),
        ),
        patch(
            "api.src.services.qa_service.runtime_config_service.get_chat_history_config",
            new=AsyncMock(return_value=_history_cfg()),
        ),
        patch("api.src.rag_integration.query_rewriter.rewrite_query", new=rewrite_mock),
    ):
        events = await _collect(
            svc.stream(
                db=db,
                user=user,
                **_rejected_stream_kwargs("임플란트 보험 적용 조건 알려주세요"),
            )
        )

    assert [ev["event"] for ev in events] == ["token", "done"]
    # 단일 질문 경로 = 이전 대화 블록이 비어 있고, 완성 검색어도 쓰지 않는다.
    assert seen["history_block"] == ""
    assert seen["search_query"] is None
    rewrite_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_rejected_history_respects_kill_switch():
    """킬 스위치가 꺼져 있으면 REJECTED 에서도 되묻지 않는다 — 예전 1문1답 동작."""
    svc = QAService()
    db = _make_db(log_id=72)
    user = _make_user()
    seen: dict = {}
    rag_mock = _make_rag_module_mock(rule_answer=None, procedures=[])

    with (
        patch.dict("sys.modules", {"rag": MagicMock(), "rag.run_qa": rag_mock}),
        patch("api.src.services.qa_service.query_runner.ensure_initialized", new_callable=AsyncMock),
        patch(
            "api.src.services.qa_service.query_runner.stream_rag_answer",
            _rag_stream_capture(seen),
        ),
        patch(
            "api.src.services.qa_service.runtime_config_service.get_chat_history_config",
            new=AsyncMock(return_value=_history_cfg(enabled=False)),
        ),
    ):
        events = await _collect(svc.stream(db=db, user=user, **_rejected_stream_kwargs("하얀색?")))

    assert [ev["event"] for ev in events] == ["token", "done"]
    assert seen["history_block"] == ""


@pytest.mark.asyncio
async def test_rejected_history_with_config_failure_still_asks_back():
    """REJECTED + 설정 조회 실패 → 안전 우선으로 되묻는다."""
    from api.src.rag_integration.question_completeness import CLARIFY_MESSAGE

    svc = QAService()
    db = _make_db(log_id=73)
    user = _make_user()
    rag_stream = MagicMock()
    rag_mock = _make_rag_module_mock(rule_answer=None, procedures=[])

    with (
        patch.dict("sys.modules", {"rag": MagicMock(), "rag.run_qa": rag_mock}),
        patch("api.src.services.qa_service.query_runner.ensure_initialized", new_callable=AsyncMock),
        patch("api.src.services.qa_service.query_runner.stream_rag_answer", rag_stream),
        patch(
            "api.src.services.qa_service.runtime_config_service.get_chat_history_config",
            new=AsyncMock(side_effect=RuntimeError("Redis 다운")),
        ),
    ):
        events = await _collect(svc.stream(db=db, user=user, **_rejected_stream_kwargs("몇 번까지 돼?")))

    assert json.loads(events[0]["data"])["delta"] == CLARIFY_MESSAGE
    rag_stream.assert_not_called()


@pytest.mark.asyncio
async def test_state_none_with_fragment_keeps_legacy_first_question_behavior():
    """맥락을 요청하지 않은 첫 질문은 조각이어도 기존대로 답한다 (회귀 금지).

    되묻기는 "이어가려 했는데 이어갈 수 없다" 는 상태에만 적용한다. 첫 질문 정책을
    넓히는 것은 별도 결정 사항이다(검수 문서 §11 남은 위험 2번).
    """
    svc = QAService()
    db = _make_db(log_id=74)
    user = _make_user()
    seen: dict = {}
    rag_mock = _make_rag_module_mock(rule_answer=None, procedures=[])

    with (
        patch.dict("sys.modules", {"rag": MagicMock(), "rag.run_qa": rag_mock}),
        patch("api.src.services.qa_service.query_runner.ensure_initialized", new_callable=AsyncMock),
        patch(
            "api.src.services.qa_service.query_runner.stream_rag_answer",
            _rag_stream_capture(seen),
        ),
    ):
        events = await _collect(
            svc.stream(
                db=db,
                user=user,
                question_text="하얀색?",
                redis_runtime=MagicMock(),
                history_turns=[],
            )
        )

    assert [ev["event"] for ev in events] == ["token", "done"]
    assert seen["history_block"] == ""


@pytest.mark.asyncio
async def test_rejected_history_without_redis_still_asks_back():
    """REJECTED + 설정 조회 수단이 아예 없어도(redis 미주입) 조각 질문은 되묻는다.

    "설정을 못 읽으면 안전장치를 끈다" 는 것이 1차 검수 P0-3 의 결함이었다.
    `redis_runtime=None` 도 같은 범주이므로 같은 안전 쪽으로 떨어져야 한다.
    """
    from api.src.rag_integration.question_completeness import CLARIFY_MESSAGE
    from api.src.services.chat_history_service import HistoryState

    svc = QAService()
    db = _make_db(log_id=75)
    user = _make_user()
    rag_stream = MagicMock()
    rag_mock = _make_rag_module_mock(rule_answer=None, procedures=[])

    with (
        patch.dict("sys.modules", {"rag": MagicMock(), "rag.run_qa": rag_mock}),
        patch("api.src.services.qa_service.query_runner.ensure_initialized", new_callable=AsyncMock),
        patch("api.src.services.qa_service.query_runner.stream_rag_answer", rag_stream),
    ):
        events = await _collect(
            svc.stream(
                db=db,
                user=user,
                question_text="몇 번까지 돼?",
                redis_runtime=None,
                history_turns=[],
                history_state=HistoryState.REJECTED,
            )
        )

    assert json.loads(events[0]["data"])["delta"] == CLARIFY_MESSAGE
    rag_stream.assert_not_called()
