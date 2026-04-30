"""RAG 런타임 래퍼 — FastAPI 동일 프로세스에서 vendor/rag 자산을 호출."""

import asyncio
import json
import queue
from collections.abc import AsyncIterator

import redis.asyncio as aioredis
import structlog

from api.src.integrations.openai.client import TokenUsage, build_chat_llm, capture_usage, with_retry
from api.src.rag_integration.prompt_injection import PromptOverride, build_prompt_with_overrides
from api.src.settings import REDIS_DB_RUNTIME_CONFIG, settings

logger = structlog.get_logger(__name__)

_initialized = False


async def ensure_initialized() -> None:
    """FAISS 인덱스와 동의어 사전을 초기화한다 (idempotent, 첫 호출에만 실행)."""
    global _initialized
    if _initialized:
        return
    faiss_path = settings.faiss_current_path
    await asyncio.to_thread(_do_init, faiss_path)
    _initialized = True
    logger.info("rag.query_runner.initialized")


def _do_init(faiss_path: str) -> None:
    from rag.run_qa import init_rag  # type: ignore[import-untyped]

    init_rag(faiss_path=faiss_path)


async def run_rule_answer(question_text: str) -> str | None:
    """규칙 기반 답변을 비동기로 실행한다.

    question_text는 PII — 로그 출력 금지.
    """
    from rag.run_qa import apply_scaling_rules, generate_rule_answer, get_syn_dict, normalize_query  # type: ignore[import-untyped]

    await ensure_initialized()

    def _run():
        query = apply_scaling_rules(question_text)
        syn_dict = get_syn_dict()
        if syn_dict:
            query = normalize_query(query, syn_dict)
        logger.info("rag.query_runner.call")
        return generate_rule_answer(query)

    return await asyncio.to_thread(_run)


async def _load_runtime_params() -> dict:
    """Redis DB 3에서 런타임 구성을 읽는다. 실패 시 기본값 반환."""
    try:
        r = aioredis.from_url(
            settings.redis_url,
            db=REDIS_DB_RUNTIME_CONFIG,
            decode_responses=True,
        )
        async with r:
            keys = await r.mget(
                "runtime:rag_k",
                "runtime:rag_temperature",
                "runtime:max_tokens",
                "runtime:prompt:BASE",
                "runtime:prompt:치식_위치",
                "runtime:prompt:치면_방향",
                "runtime:prompt:마취_산정",
                "runtime:prompt:브릿지",
            )
        return {
            "rag_k": int(keys[0]) if keys[0] else 5,
            "rag_temperature": float(keys[1]) if keys[1] else 0.0,
            "max_tokens": int(keys[2]) if keys[2] else 1024,
            "prompt_BASE": keys[3],
            "prompt_치식_위치": keys[4],
            "prompt_치면_방향": keys[5],
            "prompt_마취_산정": keys[6],
            "prompt_브릿지": keys[7],
        }
    except Exception as e:
        logger.warning("query_runner.runtime_params_load_failed", error=str(e))
        return {"rag_k": 5, "rag_temperature": 0.0, "max_tokens": 1024}


async def stream_rag_answer(
    query: str,
    on_complete: callable,
) -> AsyncIterator[str]:
    """RAG 체인을 streaming으로 실행해 토큰 단위로 yield한다.

    asyncio.to_thread + Queue 패턴 사용 (Story 2.1 패턴과 동일).
    on_complete(usage, full_text) 콜백은 스트림 종료 시 qa_logs UPDATE용.
    ADR-0002 §결정 2: return_source_documents=False (D-02, AR15 강제).
    """
    from rag.run_qa import get_retriever  # type: ignore[import-untyped]
    from langchain_classic.chains import RetrievalQA
    from langchain_core.prompts import PromptTemplate

    await ensure_initialized()
    runtime = await _load_runtime_params()

    # 프롬프트 오버라이드 구성 (async context에서 읽어 클로저로 전달)
    block_ids = ("BASE", "치식_위치", "치면_방향", "마취_산정", "브릿지")
    overrides: dict[str, PromptOverride] = {}
    for bid in block_ids:
        raw = runtime.get(f"prompt_{bid}")
        if raw:
            try:
                parsed = json.loads(raw)
                overrides[bid] = PromptOverride(
                    content=parsed.get("content", ""),
                    enabled=parsed.get("enabled", True),
                )
            except Exception:
                pass  # 파싱 실패 시 해당 블록 fallback

    token_queue: queue.Queue[str | None] = queue.Queue()
    accumulated: list[str] = []
    usage_holder: list[TokenUsage] = []
    exc_holder: list[BaseException] = []

    def _run_sync() -> None:
        """동기 스레드에서 RetrievalQA를 실행하고 토큰을 Queue에 넣는다."""
        try:
            from langchain_core.callbacks.base import BaseCallbackHandler

            class _QueueCallbackHandler(BaseCallbackHandler):
                def on_llm_new_token(self, token: str, **kwargs) -> None:
                    accumulated.append(token)
                    token_queue.put(token)

            handler = _QueueCallbackHandler()

            prompt_template_str = build_prompt_with_overrides(query, overrides or None)

            retriever = get_retriever()
            if hasattr(retriever, "search_kwargs"):
                retriever.search_kwargs["k"] = runtime["rag_k"]

            llm = build_chat_llm(
                streaming=True,
                callbacks=[handler],
                temperature=runtime["rag_temperature"],
                max_tokens=runtime["max_tokens"],
            )

            chain = RetrievalQA.from_chain_type(
                llm=llm,
                chain_type="stuff",
                retriever=retriever,
                return_source_documents=False,
                chain_type_kwargs={
                    "prompt": PromptTemplate.from_template(prompt_template_str)
                },
            )

            with capture_usage() as usage:
                with_retry(chain.invoke)({"query": query})
            usage_holder.append(usage)
        except Exception as e:
            exc_holder.append(e)
        finally:
            token_queue.put(None)  # sentinel

    thread_task = asyncio.get_event_loop().run_in_executor(None, _run_sync)

    try:
        while True:
            token = await asyncio.get_event_loop().run_in_executor(
                None, token_queue.get
            )
            if token is None:
                break
            yield token
    finally:
        await thread_task

    if exc_holder:
        raise exc_holder[0]

    full_text = "".join(accumulated)
    usage = usage_holder[0] if usage_holder else TokenUsage(0, 0, 0, 0.0)
    on_complete(usage, full_text)
