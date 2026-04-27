"""RAG 런타임 래퍼 — FastAPI 동일 프로세스에서 vendor/rag 자산을 호출."""

import asyncio
import queue
from collections.abc import AsyncIterator

import structlog

from api.src.integrations.openai.client import TokenUsage, build_chat_llm, capture_usage, with_retry
from api.src.settings import settings

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
    from rag.run_qa import init_rag
    init_rag(faiss_path=faiss_path)


async def run_rule_answer(question_text: str) -> str | None:
    """규칙 기반 답변을 비동기로 실행한다.

    question_text는 PII — 로그 출력 금지.
    """
    from rag.run_qa import apply_scaling_rules, normalize_query, generate_rule_answer, get_syn_dict

    await ensure_initialized()

    def _run():
        query = apply_scaling_rules(question_text)
        syn_dict = get_syn_dict()
        if syn_dict:
            query = normalize_query(query, syn_dict)
        logger.info("rag.query_runner.call")
        return generate_rule_answer(query)

    return await asyncio.to_thread(_run)


async def stream_rag_answer(
    query: str,
    on_complete: callable,
) -> AsyncIterator[str]:
    """RAG 체인을 streaming으로 실행해 토큰 단위로 yield한다.

    asyncio.to_thread + Queue 패턴 사용 (Story 2.1 패턴과 동일).
    on_complete(usage, full_text) 콜백은 스트림 종료 시 qa_logs UPDATE용.
    ADR-0002 §결정 2: return_source_documents=False (D-02, AR15 강제).
    """
    from rag.run_qa import get_retriever
    from rag.prompt_builder import build_prompt_template
    from langchain_classic.chains import RetrievalQA
    from langchain_core.prompts import PromptTemplate

    await ensure_initialized()

    token_queue: queue.Queue[str | None] = queue.Queue()
    accumulated: list[str] = []
    usage_holder: list[TokenUsage] = []
    exc_holder: list[BaseException] = []

    def _run_sync() -> None:
        """동기 스레드에서 RetrievalQA를 실행하고 토큰을 Queue에 넣는다."""
        try:
            from langchain_core.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
            from langchain_core.callbacks.base import BaseCallbackHandler

            class _QueueCallbackHandler(BaseCallbackHandler):
                def on_llm_new_token(self, token: str, **kwargs) -> None:
                    accumulated.append(token)
                    token_queue.put(token)

            handler = _QueueCallbackHandler()
            llm = build_chat_llm(streaming=True, callbacks=[handler])

            prompt_template_str = build_prompt_template(query)
            chain = RetrievalQA.from_chain_type(
                llm=llm,
                chain_type="stuff",
                retriever=get_retriever(),
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
            # 큐에서 토큰을 비동기적으로 가져온다
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
