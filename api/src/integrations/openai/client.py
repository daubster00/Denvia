"""OpenAI 호출 래퍼 — tenacity 재시도 + 토큰/비용 캡처.

architecture.md §876: 외부 연동은 integrations/<provider> 어댑터 경유 강제.
NFR-R3, AR12: 지수 백오프 3회 재시도.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from threading import Lock
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

# LLM 요청 타임아웃(초) — 게시판 #112. 미설정 시 httpx 무한 대기라, 상류가 hang 하면
# 스트림이 종료 이벤트를 못 내고 qa_logs 가 'in_progress' 로 영구 고아가 됐다. 스트리밍에서
# 이 값은 "토큰 사이 무응답(read) 허용 시간"으로 동작 — 정상 토큰이 흐르면 계속 리셋되므로
# 긴 답변을 자르지 않고, 진짜 stall 일 때만 APITimeoutError 를 일으켜 error 경로로 떨어뜨린다.
LLM_REQUEST_TIMEOUT_SECONDS = 60.0


def _is_reasoning_model(name: str) -> bool:
    """o3-/o4-/gpt-5.x 계열은 reasoning 모델 — temperature 파라미터 미지원.

    OpenAI API가 이들 모델에 temperature != 1 전달 시 400(Unsupported value)을 반환한다.
    (gpt-5.6-luna/terra/sol 실측 확인 2026-07: "Only the default (1) value is supported").
    temperature 를 생략하면 어떤 모델이든 안전(기본값 사용)하므로, 판별이 애매하면
    reasoning 으로 취급해 temperature 를 빼는 방향이 옳다 — 넣어서 400 나는 것보다 안전.
    """
    return name.startswith("o3") or name.startswith("o4") or name.startswith("gpt-5")


# ChatOpenAI 인스턴스 모듈 전역 캐시 — 같은 옵션이면 같은 인스턴스 재사용해서
# 내부 httpx 클라이언트(keep-alive 풀)·TLS 세션을 따뜻하게 유지한다.
# 이전엔 매 chat 요청마다 새 ChatOpenAI 를 만들어 매번 TCP/TLS handshake 가 발생했고
# 첫 요청의 LLM TTFT 가 2초+ 콜드였다. 워밍업도 같은 캐시 키로 접근해 같은 인스턴스를
# 데우면 실제 chat 의 첫 요청부터 keep-alive 가 살아 있다.
#
# 캐시 키에서 callbacks 는 제외 — 호출자는 invoke time 에 RunnableConfig 로 callbacks 를
# 전달해야 한다. callbacks 를 build time 에 박으면 같은 옵션이라도 매번 새 인스턴스가
# 만들어져 캐시가 무의미해진다.
_LLM_CACHE: dict[tuple, ChatOpenAI] = {}
_LLM_CACHE_LOCK = Lock()


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

    캐시 동작 (2026-05-29):
    - ``callbacks`` 가 None/빈 리스트면 ``_LLM_CACHE`` 에서 (모델·streaming·temperature·
      max_tokens) 키로 캐시 히트. 같은 옵션이면 같은 ChatOpenAI 인스턴스를 재사용.
    - ``callbacks`` 가 채워져 있으면 캐시 우회 + 새 인스턴스 (하위 호환성). 새 코드는
      ``chain.invoke(input, config={"callbacks": [...]})`` 패턴으로 invoke time 에 전달해야
      캐시 효과를 받는다.
    """
    effective_model = model_name or DEFAULT_CHAT_MODEL
    use_cache = not callbacks  # None or [] 면 캐시 사용

    kwargs: dict = {
        "model_name": effective_model,
        "streaming": streaming,
        "callbacks": callbacks or [],
        "max_tokens": max_tokens,
        # 게시판 #112 — 무한 hang 방지. reasoning/일반 모델 공통 적용.
        "request_timeout": LLM_REQUEST_TIMEOUT_SECONDS,
    }
    if not _is_reasoning_model(effective_model):
        kwargs["temperature"] = temperature

    if not use_cache:
        return ChatOpenAI(**kwargs)

    cache_key = (
        effective_model,
        streaming,
        temperature if not _is_reasoning_model(effective_model) else None,
        max_tokens,
    )
    cached = _LLM_CACHE.get(cache_key)
    if cached is not None:
        return cached
    with _LLM_CACHE_LOCK:
        cached = _LLM_CACHE.get(cache_key)
        if cached is not None:
            return cached
        llm = ChatOpenAI(**kwargs)
        _LLM_CACHE[cache_key] = llm
        return llm


def invalidate_chat_llm_cache(*, model_name: str | None = None) -> int:
    """캐시 무효화 — model_name 지정 시 해당 모델 항목만, 미지정 시 전체.

    관리자가 chat_model 을 바꿔 같은 옵션의 이전 모델 캐시가 stale 해진 경우는 거의 없다
    (캐시 키에 모델이 포함되므로 자연 분리). 본 함수는 테스트·운영 디버깅 용도.
    반환값: 제거된 엔트리 수.
    """
    with _LLM_CACHE_LOCK:
        if model_name is None:
            n = len(_LLM_CACHE)
            _LLM_CACHE.clear()
            return n
        to_remove = [k for k in _LLM_CACHE if k[0] == model_name]
        for k in to_remove:
            _LLM_CACHE.pop(k, None)
        return len(to_remove)


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
