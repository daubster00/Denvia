"""qa_reframe_service 단위 테스트 — Story 2.6."""

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from api.src.integrations.openai.client import TokenUsage
from api.src.schemas.qa import ReframePayload
from api.src.services import qa_reframe_service
from api.src.services.qa_reframe_service import (
    ReframeExtractionResult,
    _passes_heuristic,
)


# ---------------------------------------------------------------------------
# 단계 1: 휴리스틱 감지 테스트
# ---------------------------------------------------------------------------

def test_heuristic_rejects_long_text():
    """400자 초과 텍스트는 즉시 분기 B로 반환."""
    long_text = "치과 임플란트 시술 후 관리법에 대해 자세히 알려드리겠습니다. " * 30  # 충분히 김
    assert not _passes_heuristic(long_text)


def test_heuristic_rejects_no_question_mark():
    """물음표로 끝나지 않는 텍스트 — 분기 B."""
    text = "더 자세한 정보가 필요합니다."
    assert not _passes_heuristic(text)


def test_heuristic_passes_stateless_guidance_without_question_mark():
    """새 질문 안내문은 물음표 없이도 분기 A로 진입."""
    text = "정보가 부족해요. 새 질문에 치식 번호와 처치를 포함해서 다시 질문해줘."
    assert _passes_heuristic(text)


def test_heuristic_rejects_confirmative_phrase():
    """확정형 어미 포함 텍스트 — 분기 B. 첫 60자 이내에 확정 어미."""
    text = "다음과 같습니다. 뭔가 더 알려드릴까요?"
    assert not _passes_heuristic(text)


def test_heuristic_passes_short_question():
    """짧고 물음표로 끝나는 역질문 — 분기 A로 진입."""
    text = "임플란트가 몇 개인가요?"
    assert _passes_heuristic(text)


def test_heuristic_passes_fullwidth_question_mark():
    """전각 물음표 허용."""
    text = "어느 치아인지 알려주실래요？"
    assert _passes_heuristic(text)


def test_heuristic_rejects_confirmative_phrases():
    """여러 확정 어미 케이스 각각 검증."""
    for phrase in ["다음과 같습니다", "정답은", "산정 횟수는", "회로 산정", "치식 #"]:
        text = f"{phrase} 알아야 할 내용이 있나요?"
        assert not _passes_heuristic(text), f"확정 어미 '{phrase}' 는 reject 되어야 함"


# ---------------------------------------------------------------------------
# ReframePayload 검증 테스트
# ---------------------------------------------------------------------------

def test_reframe_payload_valid():
    """최소 3개 옵션 + 최대 4개 옵션 경계값 모두 통과."""
    p = ReframePayload(
        follow_up_question="새 질문에 치식 번호와 처치를 포함해서 다시 질문해줘.",
        options=["#36 침윤마취 청구 가능 횟수는?", "#46 전달마취 산정 기준은?", "#36, #46 동시 마취 청구는?"],
    )
    assert len(p.options) == 3


def test_reframe_payload_option_max_length():
    """option 120자 통과."""
    opt_120 = "가" * 120
    p = ReframePayload(
        follow_up_question="질문?",
        options=[opt_120, "나", "다"],
    )
    assert p.options[0] == opt_120


def test_reframe_payload_option_1_char_passes():
    """option 1자 통과."""
    p = ReframePayload(
        follow_up_question="질문?",
        options=["가", "나", "다"],
    )
    assert p.options[0] == "가"


def test_reframe_payload_option_empty_rejected():
    """option 빈 문자열(trim 후) → ValidationError."""
    with pytest.raises((ValidationError, ValueError)):
        ReframePayload(
            follow_up_question="질문?",
            options=["   ", "나", "다"],
        )


def test_reframe_payload_option_too_long_rejected():
    """option 121자 → ValidationError."""
    with pytest.raises((ValidationError, ValueError)):
        ReframePayload(
            follow_up_question="질문?",
            options=["가" * 121, "나", "다"],
        )


def test_reframe_payload_option_newline_rejected():
    """option 개행 포함 → ValidationError."""
    with pytest.raises((ValidationError, ValueError)):
        ReframePayload(
            follow_up_question="질문?",
            options=["상악\n전치", "나", "다"],
        )


def test_reframe_payload_option_carriage_return_rejected():
    """option \r 포함 → ValidationError."""
    with pytest.raises((ValidationError, ValueError)):
        ReframePayload(
            follow_up_question="질문?",
            options=["상악\r전치", "나", "다"],
        )


def test_reframe_payload_options_too_few_rejected():
    """option 2개 → ValidationError."""
    with pytest.raises((ValidationError, ValueError)):
        ReframePayload(
            follow_up_question="질문?",
            options=["가", "나"],
        )


def test_reframe_payload_options_too_many_rejected():
    """option 5개 → ValidationError."""
    with pytest.raises((ValidationError, ValueError)):
        ReframePayload(
            follow_up_question="질문?",
            options=["가", "나", "다", "라", "마"],
        )


def test_reframe_payload_follow_up_question_normalizes_whitespace():
    """follow_up_question 다중 공백·개행 → 단일 공백으로 정규화."""
    p = ReframePayload(
        follow_up_question="어느\n\n치아\t인지   알려주세요?",
        options=["가", "나", "다"],
    )
    assert p.follow_up_question == "어느 치아 인지 알려주세요?"


def test_reframe_payload_follow_up_question_blank_rejected():
    """빈 follow_up_question → ValidationError."""
    with pytest.raises((ValidationError, ValueError)):
        ReframePayload(
            follow_up_question="   \n  ",
            options=["가", "나", "다"],
        )


def test_reframe_payload_options_trimmed():
    """option 앞뒤 공백은 trim되어 저장."""
    p = ReframePayload(
        follow_up_question="질문?",
        options=["  상악 전치  ", " 나 ", "다"],
    )
    assert p.options[0] == "상악 전치"
    assert p.options[1] == "나"


# ---------------------------------------------------------------------------
# detect_and_extract 성공 경로 테스트
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_detect_and_extract_success():
    """Mock LLM 성공 → ReframeExtractionResult(payload, usage) 반환."""
    mock_payload = ReframePayload(
        follow_up_question="새 질문에 치식 번호와 처치를 포함해서 다시 질문해줘.",
        options=["#36 침윤마취 청구 가능 횟수는?", "#46 전달마취 산정 기준은?", "#36, #46 동시 마취 청구는?"],
    )
    mock_usage = TokenUsage(input_tokens=10, output_tokens=20, total_tokens=30, cost_usd=0.001)

    from contextlib import contextmanager

    @contextmanager
    def _mock_capture():
        yield mock_usage

    with (
        patch.object(qa_reframe_service, "build_structuring_llm") as mock_build,
        patch.object(qa_reframe_service, "capture_usage", side_effect=_mock_capture),
        patch.object(qa_reframe_service, "with_retry", side_effect=lambda fn: fn),
    ):
        # structured_llm.ainvoke를 직접 AsyncMock으로 설정
        mock_structured_llm = MagicMock()
        mock_structured_llm.ainvoke = AsyncMock(return_value=mock_payload)
        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = mock_structured_llm
        mock_build.return_value = mock_llm

        result = await qa_reframe_service.detect_and_extract(
            question_text="임플란트 치료 방법?",
            full_text="정보가 부족해요. 새 질문에 치식 번호와 처치를 포함해서 다시 질문해줘.",
        )

    assert result is not None
    assert isinstance(result, ReframeExtractionResult)
    assert result.payload.follow_up_question == "새 질문에 치식 번호와 처치를 포함해서 다시 질문해줘."
    assert len(result.payload.options) == 3


# ---------------------------------------------------------------------------
# detect_and_extract 폴백 경로 테스트
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_detect_and_extract_heuristic_fail_returns_none():
    """휴리스틱 실패(긴 텍스트) → None 즉시 반환, LLM 호출 없음."""
    long_text = "치과 임플란트에 대해 자세한 정보를 제공하겠습니다. " * 30

    with patch.object(qa_reframe_service, "build_structuring_llm") as mock_build:
        result = await qa_reframe_service.detect_and_extract(
            question_text="질문",
            full_text=long_text,
        )
        mock_build.assert_not_called()

    assert result is None


@pytest.mark.asyncio
async def test_detect_and_extract_validation_error_returns_none():
    """structuring LLM이 스키마 미준수 → ValidationError 흡수 → None 반환."""
    from contextlib import contextmanager

    @contextmanager
    def _mock_capture():
        yield TokenUsage(0, 0, 0, 0.0)

    async def _bad_ainvoke(messages):
        # options가 2개뿐인 잘못된 페이로드 생성 시도
        return ReframePayload(
            follow_up_question="질문?",
            options=["가", "나"],  # 3개 미만 → ValidationError
        )

    with (
        patch.object(qa_reframe_service, "build_structuring_llm") as mock_build,
        patch.object(qa_reframe_service, "capture_usage", side_effect=_mock_capture),
        patch.object(qa_reframe_service, "with_retry", side_effect=lambda fn: fn),
    ):
        mock_structured_llm = MagicMock()
        mock_structured_llm.ainvoke = AsyncMock(side_effect=_bad_ainvoke)
        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = mock_structured_llm
        mock_build.return_value = mock_llm

        result = await qa_reframe_service.detect_and_extract(
            question_text="질문",
            full_text="어떤 상황인지 알려주실래요?",
        )

    assert result is None


@pytest.mark.asyncio
async def test_detect_and_extract_llm_exception_returns_none(caplog):
    """LLM 예외 → None 반환 + qa.reframe.extract_failed warning (error_type만)."""
    import logging

    from contextlib import contextmanager

    @contextmanager
    def _mock_capture():
        yield TokenUsage(0, 0, 0, 0.0)

    async def _raise_error(messages):
        raise RuntimeError("connection error")

    with (
        patch.object(qa_reframe_service, "build_structuring_llm") as mock_build,
        patch.object(qa_reframe_service, "capture_usage", side_effect=_mock_capture),
        patch.object(qa_reframe_service, "with_retry", side_effect=lambda fn: fn),
        caplog.at_level(logging.WARNING),
    ):
        mock_structured_llm = MagicMock()
        mock_structured_llm.ainvoke = AsyncMock(side_effect=RuntimeError("connection error"))
        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = mock_structured_llm
        mock_build.return_value = mock_llm

        result = await qa_reframe_service.detect_and_extract(
            question_text="질문",
            full_text="어떤 상황인지?",
        )

    assert result is None


@pytest.mark.asyncio
async def test_detect_and_extract_timeout_returns_none(caplog):
    """5초 timeout 초과 → None 반환 + qa.reframe.timeout warning."""
    import logging

    from contextlib import contextmanager

    @contextmanager
    def _mock_capture():
        yield TokenUsage(0, 0, 0, 0.0)

    async def _slow_invoke(messages):
        await asyncio.sleep(100)  # 5초 초과 시뮬레이션

    with (
        patch.object(qa_reframe_service, "build_structuring_llm") as mock_build,
        patch.object(qa_reframe_service, "capture_usage", side_effect=_mock_capture),
        patch.object(qa_reframe_service, "with_retry", side_effect=lambda fn: fn),
        patch.object(qa_reframe_service, "_STRUCTURING_TIMEOUT_SECONDS", 0.01),
        caplog.at_level(logging.WARNING),
    ):
        mock_structured_llm = MagicMock()
        mock_structured_llm.ainvoke = AsyncMock(side_effect=_slow_invoke)
        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = mock_structured_llm
        mock_build.return_value = mock_llm

        result = await qa_reframe_service.detect_and_extract(
            question_text="질문",
            full_text="어떤 상황인지?",
        )

    assert result is None
