"""OpenAI 호출 래퍼 — tenacity 재시도 + 토큰/비용 캡처.

architecture.md §876: 외부 연동은 integrations/<provider> 어댑터 경유 강제.
NFR-R3, AR12: 지수 백오프 3회 재시도.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Generator

import openai
import structlog
from langchain_community.callbacks import get_openai_callback
from langchain_openai import ChatOpenAI
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = structlog.get_logger(__name__)

_RETRY_EXCEPTIONS = (openai.APITimeoutError, openai.APIConnectionError, openai.RateLimitError)


@dataclass
class TokenUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float


def build_chat_llm(*, streaming: bool, callbacks: list | None = None) -> ChatOpenAI:
    """ADR-0002 §결정 2: model_name="o4-mini" 기본값 유지 (변경 금지)."""
    return ChatOpenAI(model_name="o4-mini", streaming=streaming, callbacks=callbacks or [])


def with_retry(fn):
    """OpenAI 호출 공통 재시도 데코레이터 (NFR-R3, AR12)."""
    return retry(
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(_RETRY_EXCEPTIONS),
        reraise=True,
    )(fn)


@contextmanager
def capture_usage() -> Generator[TokenUsage, None, None]:
    """get_openai_callback 컨텍스트 — TokenUsage로 변환하여 yield."""
    with get_openai_callback() as cb:
        usage = TokenUsage(0, 0, 0, 0.0)
        yield usage
        usage.input_tokens = cb.prompt_tokens
        usage.output_tokens = cb.completion_tokens
        usage.total_tokens = cb.total_tokens
        usage.cost_usd = cb.total_cost
