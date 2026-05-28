"""RAG 런타임 래퍼 — FastAPI 동일 프로세스에서 vendor/rag 자산을 호출."""

import asyncio
import json
import os
import queue
import time
from collections.abc import AsyncIterator

import redis.asyncio as aioredis
import structlog

from api.src.integrations.openai.client import TokenUsage, build_chat_llm, capture_usage, with_retry
from api.src.rag_integration.prompt_injection import PromptOverride, build_prompt_with_overrides
from api.src.settings import REDIS_DB_RUNTIME_CONFIG, settings

logger = structlog.get_logger(__name__)

_initialized = False
# 마지막으로 메모리에 로드한 인덱스의 실제 경로(symlink 해석 후).
# 재빌드가 끝나면 atomic_swap이 current symlink의 target을 index_a↔index_b로 바꾼다.
# ensure_initialized()가 매 호출 시 현재 realpath와 비교 → 다르면 자동 리로드.
_loaded_index_realpath: str | None = None

# 관리자 감사용 retrieved_docs 1건당 page_content 최대 길이.
# 너무 길면 JSONB 컬럼 사이즈와 관리자 UI 응답이 비대해진다.
_DOC_CONTENT_LIMIT = 2000


def _serialize_source_documents(docs) -> list[dict]:
    """LangChain Document 리스트를 JSON 직렬화 가능한 dict 리스트로 변환한다.

    qa_logs.retrieved_docs(JSONB) 저장 전용. 관리자 감사 외 용도 금지.
    page_content는 ``_DOC_CONTENT_LIMIT`` 길이로 잘라 폭주를 방지한다.
    """
    out: list[dict] = []
    for d in docs or []:
        content = getattr(d, "page_content", None) or ""
        if len(content) > _DOC_CONTENT_LIMIT:
            content = content[:_DOC_CONTENT_LIMIT] + "…"
        metadata = getattr(d, "metadata", None) or {}
        try:
            json.dumps(metadata, ensure_ascii=False)
            safe_meta = metadata
        except (TypeError, ValueError):
            safe_meta = {k: str(v) for k, v in metadata.items()}
        out.append({"page_content": content, "metadata": safe_meta})
    return out


async def ensure_initialized() -> None:
    """FAISS 인덱스와 동의어 사전을 메모리에 로드한다.

    동작:
      1. 미초기화 → 첫 로드.
      2. 이미 초기화됐고 디스크 symlink target이 동일 → no-op.
      3. 이미 초기화됐는데 symlink target이 바뀜(= 관리자 재빌드 + atomic_swap 완료)
         → vendor 전역 변수 비우고 새 인덱스로 리로드.

    main.py lifespan에서 부팅 시 1회 미리 호출 → 첫 사용자 질문 지연 제거.
    qa_service.stream에서도 호출 → 매 요청마다 swap 감지 + 자동 리로드 트리거.
    """
    global _initialized, _loaded_index_realpath
    faiss_path = settings.faiss_current_path
    try:
        current_realpath = os.path.realpath(faiss_path)
    except OSError:
        current_realpath = faiss_path

    if _initialized and _loaded_index_realpath == current_realpath:
        return

    if _initialized and _loaded_index_realpath != current_realpath:
        logger.info(
            "rag.query_runner.reload_detected",
            old_path=_loaded_index_realpath,
            new_path=current_realpath,
        )
        await asyncio.to_thread(_reset_vendor_globals)
        _initialized = False

    t0 = time.perf_counter()
    await asyncio.to_thread(_do_init, faiss_path)
    _initialized = True
    _loaded_index_realpath = current_realpath
    logger.info(
        "rag.query_runner.initialized",
        path=current_realpath,
        elapsed_ms=int((time.perf_counter() - t0) * 1000),
    )


def _do_init(faiss_path: str) -> None:
    from rag.run_qa import init_rag  # type: ignore[import-untyped]

    init_rag(faiss_path=faiss_path)


def _reset_vendor_globals() -> None:
    """vendor/rag/run_qa/run_qa.py 안쪽 모듈의 lazy-init 전역 변수를 비워
    다음 init_rag 호출 시 FAISS 인덱스·동의어 사전을 디스크에서 새로 읽도록 한다.

    재빌드 후 atomic_swap으로 디스크 symlink가 바뀌었을 때, 메모리에 들고 있던
    이전 vectorstore/retriever 객체가 stale해지는 것을 막는 유일한 경로.
    vendor 코드는 손대지 않고(ADR-0002), 모듈 전역만 외부에서 초기화한다.

    주의: 전역(`_embeddings/_vectorstore/_retriever/_syn_dict`)은 패키지
    `rag.run_qa`가 아니라 안쪽 파일 모듈 `rag.run_qa.run_qa`에 살아 있다.
    `rag.run_qa.__init__`는 공개 함수만 re-export하고 언더스코어 전역은
    가져오지 않으므로, 패키지를 잡고 속성을 설정하면 무관한 새 속성만
    생기고 실제 캐시는 그대로 남아 init_rag가 `_retriever is None` 분기를
    건너뛰어 재로드가 일어나지 않는다.
    """
    try:
        import rag.run_qa.run_qa as _vendor  # type: ignore[import-untyped]

        _vendor._embeddings = None
        _vendor._vectorstore = None
        _vendor._retriever = None
        _vendor._syn_dict = None
    except Exception as exc:
        logger.warning("rag.query_runner.vendor_reset_failed", error=str(exc))


def reset() -> None:
    """캐시 상태를 외부에서 명시적으로 무효화한다 (테스트·관리자 핫리로드용).

    다음 ensure_initialized() 호출이 디스크에서 인덱스를 새로 읽는다.
    """
    global _initialized, _loaded_index_realpath
    _reset_vendor_globals()
    _initialized = False
    _loaded_index_realpath = None
    logger.info("rag.query_runner.reset")


async def run_rule_answer(question_text: str) -> str | None:
    """규칙 기반 답변을 비동기로 실행한다.

    question_text는 PII — 로그 출력 금지.

    Story 8.5 변경: vendor의 `get_syn_dict()` / `_syn_dict` 모듈 전역 캐시 대신
    DB(synonym_groups) → Redis Cache-Aside(runtime:synonyms_v1)에서 빌드한 dict를
    `normalize_query(query, syn_dict)`에 직접 전달한다. vendor/rag 코드 0 수정.
    """
    from rag.run_qa import apply_scaling_rules, generate_rule_answer, normalize_query  # type: ignore[import-untyped]

    await ensure_initialized()
    syn_dict = await _get_synonyms_dict()

    def _run():
        query = apply_scaling_rules(question_text)
        if syn_dict:
            query = normalize_query(query, syn_dict)
        logger.info("rag.query_runner.call", synonym_groups=len(syn_dict))
        return generate_rule_answer(query)

    return await asyncio.to_thread(_run)


async def _get_synonyms_dict() -> dict[str, list[str]]:
    """동의어 사전 Cache-Aside (Redis DB 3 `runtime:synonyms_v1`).

    miss / Redis 실패 시 DB 풀스캔으로 빌드. DB도 비었으면 vendor의 fallback JSON.
    """
    from api.src.services.synonym_service import (
        RUNTIME_CACHE_KEY,
        RUNTIME_CACHE_TTL_SEC,
        build_synonyms_dict_from_db,
    )

    cached_raw: str | None = None
    try:
        r = aioredis.from_url(
            settings.redis_url,
            db=REDIS_DB_RUNTIME_CONFIG,
            decode_responses=True,
        )
        async with r:
            cached_raw = await r.get(RUNTIME_CACHE_KEY)
    except Exception as exc:
        logger.warning("rag.synonyms.redis_get_failed", error=str(exc))

    if cached_raw:
        try:
            return json.loads(cached_raw)
        except Exception:
            logger.warning("rag.synonyms.cache_decode_failed")

    # DB 풀스캔
    from api.src.models.base import async_session_factory

    try:
        async with async_session_factory() as session:
            d = await build_synonyms_dict_from_db(session)
    except Exception as exc:
        logger.warning("rag.synonyms.db_build_failed", error=str(exc))
        d = {}

    if not d:
        # DB가 비어 있으면 vendor fallback JSON을 로드 (vendor 코드 변경 없이 dict만 가져옴)
        try:
            from rag.run_qa import get_syn_dict  # type: ignore[import-untyped]

            vendor_dict = get_syn_dict() or {}
            if vendor_dict:
                logger.warning(
                    "rag.synonyms.fallback_to_vendor",
                    reason="db_empty",
                    vendor_count=len(vendor_dict),
                )
                return vendor_dict
        except Exception as exc:
            logger.warning("rag.synonyms.vendor_fallback_failed", error=str(exc))

    if d:
        try:
            r = aioredis.from_url(
                settings.redis_url,
                db=REDIS_DB_RUNTIME_CONFIG,
                decode_responses=True,
            )
            async with r:
                await r.set(
                    RUNTIME_CACHE_KEY,
                    json.dumps(d, ensure_ascii=False),
                    ex=RUNTIME_CACHE_TTL_SEC,
                )
        except Exception as exc:
            logger.warning("rag.synonyms.redis_set_failed", error=str(exc))

    return d


async def _load_runtime_params() -> dict:
    """Redis DB 3에서 런타임 구성을 읽는다. 실패 시 기본값 반환."""
    from api.src.services.runtime_config_service import (
        ALLOWED_CHAT_MODELS,
        DEFAULT_CHAT_MODEL,
    )

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
                "runtime:chat_model",
            )
        chat_model_raw = keys[8]
        chat_model = (
            chat_model_raw
            if chat_model_raw in ALLOWED_CHAT_MODELS
            else DEFAULT_CHAT_MODEL
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
            "chat_model": chat_model,
        }
    except Exception as e:
        logger.warning("query_runner.runtime_params_load_failed", error=str(e))
        return {
            "rag_k": 5,
            "rag_temperature": 0.0,
            "max_tokens": 1024,
            "chat_model": DEFAULT_CHAT_MODEL,
        }


async def stream_rag_answer(
    query: str,
    on_complete: callable,
) -> AsyncIterator[str]:
    """RAG 체인을 streaming으로 실행해 토큰 단위로 yield한다.

    asyncio.to_thread + Queue 패턴 사용 (Story 2.1 패턴과 동일).
    on_complete(usage, full_text, docs) 콜백은 스트림 종료 시 qa_logs UPDATE용.
      - docs: list[dict] — RetrievalQA가 top-k로 가져온 문서들의 직렬화.
              관리자 감사 용도(qa_logs.retrieved_docs)로만 저장하며,
              SSE 응답이나 사용자 노출에는 절대 사용하지 않는다 (ADR-0002 보강).

    return_source_documents=True 로 두지만, 결과 dict 의 'result' 필드만
    토큰 스트림으로 흘리고 'source_documents' 는 콜백으로만 전달한다.
    """
    from rag.run_qa import get_retriever  # type: ignore[import-untyped]
    from langchain_classic.chains import RetrievalQA
    from langchain_core.prompts import PromptTemplate

    t0 = time.perf_counter()
    await ensure_initialized()
    runtime = await _load_runtime_params()
    t_runtime_loaded_ms = int((time.perf_counter() - t0) * 1000)

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
    docs_holder: list[list[dict]] = []
    exc_holder: list[BaseException] = []
    first_token_perf: list[float] = []

    def _run_sync() -> None:
        """동기 스레드에서 RetrievalQA를 실행하고 토큰을 Queue에 넣는다."""
        try:
            from langchain_core.callbacks.base import BaseCallbackHandler

            class _QueueCallbackHandler(BaseCallbackHandler):
                def on_llm_new_token(self, token: str, **kwargs) -> None:
                    if not first_token_perf:
                        first_token_perf.append(time.perf_counter())
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
                model_name=runtime.get("chat_model"),
            )

            chain = RetrievalQA.from_chain_type(
                llm=llm,
                chain_type="stuff",
                retriever=retriever,
                return_source_documents=True,
                chain_type_kwargs={
                    "prompt": PromptTemplate.from_template(prompt_template_str)
                },
            )

            with capture_usage() as usage:
                result = with_retry(chain.invoke)({"query": query})
            usage_holder.append(usage)
            # 관리자 감사용 — SSE/사용자 응답에는 흘리지 않고 docs_holder에만 적재
            raw_docs = result.get("source_documents", []) if isinstance(result, dict) else []
            docs_holder.append(_serialize_source_documents(raw_docs))
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
    docs = docs_holder[0] if docs_holder else []

    # 진단용: stream_rag_answer 진입부터 OpenAI 첫 토큰 도착까지의 elapsed.
    # runtime 로드 시간과 분리해서 본다(= retriever + LLM TTFT).
    if first_token_perf:
        ttft_ms = int((first_token_perf[0] - t0) * 1000)
        logger.info(
            "rag.stream.ttft_ms",
            runtime_load_ms=t_runtime_loaded_ms,
            llm_ttft_ms=ttft_ms - t_runtime_loaded_ms,
            total_ttft_ms=ttft_ms,
            total_tokens=usage.total_tokens,
        )

    on_complete(usage, full_text, docs)
