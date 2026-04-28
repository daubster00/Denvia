"""Reframe 응답 후처리 서비스 — Story 2.6.

RAG 체인이 자유 텍스트 역질문만 출력하는 제약(NFR-M2)을 우회하기 위해
웹 레이어에서 휴리스틱 사전 필터 + 별도 structuring LLM 호출로
{follow_up_question, options[3~4]} 구조화 페이로드를 합성한다.

설계 근거: _bmad-output/implementation-artifacts/2-6-question-re-frame.md §5.0
"""

import asyncio
from dataclasses import dataclass

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from api.src.integrations.openai.client import (
    TokenUsage,
    build_structuring_llm,
    capture_usage,
    with_retry,
)
from api.src.schemas.qa import ReframePayload

logger = structlog.get_logger(__name__)

# 단계 1 휴리스틱 임계값
_MAX_REFRAME_LEN = 400
_CONFIRMATIVE_PHRASES = (
    "다음과 같습니다",
    "정답은",
    "산정 횟수는",
    "회로 산정",
    "치식 #",
    "보세요\n",
    "입니다.\n",
)
_STRUCTURING_TIMEOUT_SECONDS = 5

_SYSTEM_PROMPT = (
    "사용자의 원 질문과 어시스턴트의 자유 텍스트 후속 질문을 받아 구조화한다. "
    "follow_up_question은 어시스턴트의 의도를 보존하되 한 문장으로 자연스럽게 요약한다. "
    "options는 3~4개의 짧은 한국어 후속 답변 후보(각 1~120자)로, "
    "사용자가 클릭 한 번으로 재질의할 수 있는 명확한 선택지여야 한다. "
    "options에는 의미가 명확히 구분되는 항목만 포함하고, 중복·모호한 표현은 피한다."
)


@dataclass(frozen=True)
class ReframeExtractionResult:
    """detect_and_extract 결과 컨테이너 (Story 2.6).

    payload: 구조화된 ReframePayload (Pydantic 검증 통과).
    usage: structuring 호출 한 건의 TokenUsage —
           qa.reframe.extracted 관측 전용. qa_logs.cost_usd에 합산 금지.
    """

    payload: ReframePayload
    usage: TokenUsage


def _passes_heuristic(full_text: str) -> bool:
    """단계 1 — 휴리스틱 사전 필터. LLM 호출 없음."""
    text = full_text.strip()
    if len(text) > _MAX_REFRAME_LEN:
        return False
    if not (text.endswith("?") or text.endswith("？")):
        return False
    head = text[:60]
    if any(p in head for p in _CONFIRMATIVE_PHRASES):
        return False
    return True


async def detect_and_extract(
    *, question_text: str, full_text: str
) -> ReframeExtractionResult | None:
    """역질문 감지 + 구조화 추출.

    None 반환 시 일반 답변으로 폴백 (사용자 UX 무영향).
    예외 / timeout / Pydantic ValidationError는 모두 None으로 흡수한다.
    """
    if not _passes_heuristic(full_text):
        return None

    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"[원 질문]\n{question_text}\n\n"
                f"[어시스턴트 자유 텍스트 후속 질문]\n{full_text}"
            )
        ),
    ]

    try:
        with capture_usage() as usage:
            llm = build_structuring_llm()
            structured_llm = llm.with_structured_output(ReframePayload)
            invoke = with_retry(structured_llm.ainvoke)
            payload: ReframePayload = await asyncio.wait_for(
                invoke(messages), timeout=_STRUCTURING_TIMEOUT_SECONDS
            )
        return ReframeExtractionResult(payload=payload, usage=usage)
    except asyncio.TimeoutError:
        logger.warning(
            "qa.reframe.timeout",
            timeout_seconds=_STRUCTURING_TIMEOUT_SECONDS,
        )
        return None
    except Exception as exc:
        # PII(question/answer 본문)는 절대 노출 금지 — error_type만 기록.
        logger.warning(
            "qa.reframe.extract_failed",
            error_type=type(exc).__name__,
        )
        return None
