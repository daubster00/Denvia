"""Reframe 응답 후처리 서비스 — Story 2.6.

RAG 체인이 자유 텍스트 역질문만 출력하는 제약(NFR-M2)을 우회하기 위해
웹 레이어에서 휴리스틱 사전 필터 + 별도 structuring LLM 호출로
{follow_up_question, options[3~4]} 구조화 페이로드를 합성한다.
대화 맥락을 이어받지 않는 QA 정책에 맞춰, 결과는 후속 답변 요구가 아닌
"독립된 새 질문을 작성하는 안내"로 정규화한다.

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
_INFO_SHORTAGE_GUIDANCE_MARKERS = (
    "새 질문",
    "다시 질문",
    "포함해서",
    "정보가 부족",
    "필요한 정보",
)
_STRUCTURING_TIMEOUT_SECONDS = 5

_SYSTEM_PROMPT = (
    "사용자의 원 질문과 어시스턴트의 자유 텍스트 정보부족 안내를 받아 구조화한다. "
    "이 서비스는 이전 대화 맥락을 이어받지 않으므로, 사용자의 다음 답변을 기다리는 "
    "후속 질문 형태로 만들면 안 된다. "
    "follow_up_question은 부족한 정보 때문에 답변할 수 없다는 점과 독립된 새 질문으로 "
    "다시 질문해야 한다는 점을 한 문장으로 안내한다. "
    "반드시 '새 질문에 ... 포함해서 다시 질문해줘' 형식을 사용하고, "
    "'알려줘?', '입력해줘?', '어느 치아인가요?'처럼 이어지는 답변을 유도하는 표현은 금지한다. "
    "options는 3~4개의 짧은 한국어 새 질문 예시 또는 새 질문에 넣을 구체 문구(각 1~120자)로 만든다. "
    "사용자가 클릭하면 입력창에 들어가 독립 질문으로 제출할 수 있어야 한다. "
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
    head = text[:60]
    if any(p in head for p in _CONFIRMATIVE_PHRASES):
        return False
    if text.endswith("?") or text.endswith("？"):
        return True
    if any(marker in text for marker in _INFO_SHORTAGE_GUIDANCE_MARKERS):
        return True
    return False


async def detect_and_extract(
    *, question_text: str, full_text: str
) -> ReframeExtractionResult | None:
    """정보부족 안내 감지 + 구조화 추출.

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
                f"[어시스턴트 자유 텍스트 정보부족 안내]\n{full_text}"
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
