"""지식 인덱스 재구축(임베딩) 비용 계산 — 수정요청 게시판 #145.

배경
----
관리자 화면의 "지출"은 그동안 `qa_logs`(챗봇 질의응답 기록) 한 테이블만 합산했다.
비용 집계가 langchain `get_openai_callback()` 기반이라 **채팅(LLM) 호출만** 세고
**임베딩(OpenAIEmbeddings) 호출은 세지 않았다.** 그래서 지식 인덱스를 재구축할
때마다 실제로는 OpenAI 에 돈이 나갔는데 어디에도 기록이 남지 않았다.

이 모듈은 **OpenAI 에 추가 요청을 보내지 않고** tiktoken 으로 로컬에서 토큰 수를
직접 세어 비용을 환산한다. (토큰을 세려고 API 를 부르면 돈이 더 나간다.)

모델이나 단가가 바뀌면 아래 상수 3개만 고치면 된다.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from functools import lru_cache

# ─── 단가·모델 상수 (여기만 고치면 됨) ────────────────────────────────────────

#: 재구축 시 실제로 쓰는 임베딩 모델.
#: SSOT 는 vendor/rag/update_vectorstore/update_vectorstore.py 의
#: `OpenAIEmbeddings(model="text-embedding-3-large")`.
EMBEDDING_MODEL = "text-embedding-3-large"

#: text-embedding-3-large 의 토크나이저 인코딩 이름.
#: (text-embedding-3-* 계열은 모두 cl100k_base 를 쓴다.)
EMBEDDING_ENCODING = "cl100k_base"

#: OpenAI 공식 단가 — text-embedding-3-large: $0.13 / 1,000,000 tokens.
#: 출처: https://openai.com/api/pricing (2026-09 기준)
EMBEDDING_USD_PER_1M_TOKENS = Decimal("0.13")

#: tiktoken 을 못 쓸 때만 쓰는 근사 계수 — "문자 수 ÷ 이 값 = 토큰 수".
#: 한국어는 cl100k_base 에서 대략 1.5자당 1토큰이라 이 값을 쓴다.
#: 어디까지나 비상용 근사이며, 정상 경로에서는 쓰이지 않는다.
_APPROX_CHARS_PER_TOKEN = Decimal("1.5")


@lru_cache(maxsize=1)
def _get_encoding():
    """tiktoken 인코더 — 최초 1회만 로드해서 재사용. 없으면 None."""
    try:
        import tiktoken
    except ImportError:  # pragma: no cover - 의존성 누락 방어
        return None
    try:
        return tiktoken.get_encoding(EMBEDDING_ENCODING)
    except Exception:  # pragma: no cover - 인코딩 캐시 다운로드 실패 등
        return None


def count_tokens(texts: Iterable[str]) -> tuple[int, bool]:
    """임베딩될 텍스트들의 총 토큰 수를 센다.

    Returns:
        (총 토큰 수, 근사 여부). 근사 여부가 True 면 tiktoken 을 쓰지 못해
        문자 수 기반으로 어림한 값이라는 뜻이다(화면에도 그렇게 표시해야 함).
    """
    enc = _get_encoding()
    if enc is None:
        total_chars = sum(len(t) for t in texts)
        approx = int(Decimal(total_chars) / _APPROX_CHARS_PER_TOKEN)
        return approx, True

    total = 0
    for text in texts:
        # disallowed_special=() : 지식 문서 안에 <|endoftext|> 같은 문자열이
        # 우연히 들어 있어도 예외를 내지 말고 평범한 글자로 세게 한다.
        total += len(enc.encode(text, disallowed_special=()))
    return total, False


def embedding_cost_usd(token_count: int) -> Decimal:
    """임베딩 토큰 수 → USD 비용.

    소수점 6자리로 반올림 — qa_logs.cost_usd 와 동일 정밀도.
    """
    if token_count <= 0:
        return Decimal("0.000000")
    usd = (Decimal(token_count) / Decimal(1_000_000)) * EMBEDDING_USD_PER_1M_TOKENS
    return usd.quantize(Decimal("0.000001"))
