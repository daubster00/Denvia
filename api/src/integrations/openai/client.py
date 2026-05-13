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


DEFAULT_CHAT_MODEL = "o4-mini"


def _is_reasoning_model(name: str) -> bool:
    """o3-/o4- 계열은 reasoning 모델 — temperature 파라미터 미지원.

    OpenAI API가 reasoning 모델에 temperature != 1 전달 시 400 반환.
    """
    return name.startswith("o3") or name.startswith("o4")


def build_chat_llm(
    *,
    streaming: bool,
    callbacks: list | None = None,
    temperature: float = 0.0,
    max_tokens: int = 1024,
    model_name: str | None = None,
) -> ChatOpenAI:
    """ADR-0002 §결정 2: 인수자 기본값은 ``o4-mini`` (변경 금지 → 관리자 override만 허용).

    ``model_name``이 None이면 ``DEFAULT_CHAT_MODEL``(=o4-mini)을 사용한다. 관리자 설정
    페이지에서 Redis ``runtime:chat_model``을 다른 허용 모델로 바꿨을 때만 외부에서
    주입한 값이 들어온다 (runtime_config_service.ALLOWED_CHAT_MODELS 화이트리스트).

    reasoning 모델(o3-/o4-)은 ``temperature`` 파라미터를 미지원하므로 전달하지 않는다.
    일반 chat 모델(gpt-4o*, gpt-4-turbo 등)에만 ``temperature``를 전달한다.
    """
    effective_model = model_name or DEFAULT_CHAT_MODEL

    kwargs: dict = {
        "model_name": effective_model,
        "streaming": streaming,
        "callbacks": callbacks or [],
        "max_tokens": max_tokens,
    }
    if not _is_reasoning_model(effective_model):
        kwargs["temperature"] = temperature
    return ChatOpenAI(**kwargs)


# Story 2.6: 역질문 응답 구조화 전용 모델 — RAG 본 체인의 o4-mini와 별도 운용.
# ADR-0002 §결정 2 ③ 보호 대상은 RAG 본 체인이며, 본 모델은 웹 레이어 후처리 전용.
STRUCTURING_MODEL = "gpt-4o-mini"


def build_structuring_llm(callbacks: list | None = None) -> ChatOpenAI:
    """Story 2.6: 역질문 구조화 전용 ChatOpenAI 팩토리.

    외부 모듈(qa_reframe_service)이 langchain_openai.ChatOpenAI를 직접
    import / 인스턴스화하지 않도록 어댑터 모듈 안에서만 ChatOpenAI를 만든다.
    streaming=False 고정 (구조화 출력은 단발 호출). callbacks는 향후 커스텀
    LangChain handler 주입용 hook (현재 capture_usage는 callback list가 아닌
    TokenUsage를 yield하므로 본 팩토리에 callback list를 전달하지 않는다).
    """
    return ChatOpenAI(model=STRUCTURING_MODEL, streaming=False, callbacks=callbacks or [])


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
