"""QA 서비스 — echo(Story 2.1) + stream(Story 2.2 SSE streaming)."""

import asyncio
import json
import time
from collections.abc import AsyncIterator
from decimal import Decimal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.integrations.openai.client import TokenUsage, _RETRY_EXCEPTIONS
from api.src.models.qa_log import QALog
from api.src.models.user import User
from api.src.rag_integration import query_runner
from api.src.schemas.qa import QAEchoResponse

logger = structlog.get_logger(__name__)

_ECHO_ANSWER = "[placeholder] 스트리밍은 Story 2.2에서 구현됩니다"


class QAService:
    async def echo(
        self,
        db: AsyncSession,
        user: User,
        question_text: str,
    ) -> QAEchoResponse:
        log = QALog(
            user_id=user.id,
            question_text=question_text,
            answer_text=_ECHO_ANSWER,
            rule_matched=False,
        )
        db.add(log)
        await db.flush()
        await db.refresh(log)
        qa_log_id = log.id
        await db.commit()

        logger.info("qa.echo.completed", user_id=user.id, qa_log_id=qa_log_id)

        return QAEchoResponse(
            qa_log_id=qa_log_id,
            question_text=question_text,
            rule_matched=False,
            answer_text=_ECHO_ANSWER,
        )

    async def stream(
        self,
        db: AsyncSession,
        user: User,
        question_text: str,
    ) -> AsyncIterator[dict]:
        """SSE 이벤트를 yield하는 async generator.

        yield 형식: {"event": "token", "data": json.dumps(...)} — sse-starlette 호환.
        AC-4: 요청 시작 시 즉시 INSERT → 종료 시 UPDATE 패턴.
        AC-7: GeneratorExit(클라이언트 단절)은 finally 블록에서 처리.
        AC-8: question_text/answer_text/delta는 절대 logger에 전달 금지 (PII).
        """
        from rag.run_qa import (
            apply_scaling_rules,
            normalize_query,
            generate_rule_answer,
            get_syn_dict,
            extract_procedures,
        )

        t0 = time.perf_counter()
        aborted = False

        # AC-4: 요청 시작 시 즉시 INSERT (취소 추적 가능)
        trace_id = structlog.contextvars.get_contextvars().get("trace_id")
        log = QALog(
            user_id=user.id,
            question_text=question_text,
            answer_text=None,
            rule_matched=False,
            trace_id=trace_id,
        )
        db.add(log)
        await db.flush()
        await db.refresh(log)
        qa_log_id = log.id
        await db.commit()  # 별도 트랜잭션 — 스트리밍 중 락 회피

        try:
            # RAG 자산 호출 — vendor/rag CLI 순서 보존 (ADR-0002 §결정 1·2)
            await query_runner.ensure_initialized()
            scaled = await asyncio.to_thread(apply_scaling_rules, question_text)
            syn_dict = await asyncio.to_thread(get_syn_dict)
            normalized = await asyncio.to_thread(normalize_query, scaled, syn_dict)
            rule_answer = await asyncio.to_thread(generate_rule_answer, normalized)
            procedures = await asyncio.to_thread(extract_procedures, normalized)

            # AC-2 분기 조건 (원본 CLI 기준, ADR-0002 §결정 1)
            use_rule = (
                "장애인" in normalized
                and "가산" in normalized
                and rule_answer is not None
            )

            if use_rule:
                # 룰 응답 경로: rule_matched → token 1회 → done
                yield {"event": "rule_matched", "data": json.dumps({"procedure_count": len(procedures)})}
                yield {"event": "token", "data": json.dumps({"delta": rule_answer})}
                accumulated = rule_answer
                usage = TokenUsage(0, 0, 0, 0.0)
            else:
                # RAG 경로: stream_rag_answer async iter → token 다회 → done
                accumulated_chunks: list[str] = []
                usage_holder: list[TokenUsage] = []

                def _on_complete(u: TokenUsage, full: str) -> None:
                    usage_holder.append(u)

                async for token in query_runner.stream_rag_answer(normalized, _on_complete):
                    accumulated_chunks.append(token)
                    yield {"event": "token", "data": json.dumps({"delta": token})}

                accumulated = "".join(accumulated_chunks)
                usage = usage_holder[0] if usage_holder else TokenUsage(0, 0, 0, 0.0)

            latency_ms = int((time.perf_counter() - t0) * 1000)

            # AC-4: qa_logs UPDATE
            log.answer_text = accumulated
            log.rule_matched = use_rule
            log.input_tokens = usage.input_tokens
            log.output_tokens = usage.output_tokens
            log.cost_usd = Decimal(str(usage.cost_usd))
            log.latency_ms = latency_ms
            await db.commit()

            yield {
                "event": "done",
                "data": json.dumps({
                    "qa_log_id": qa_log_id,
                    "total_tokens": usage.total_tokens,
                    "cost_usd": float(usage.cost_usd),
                    "latency_ms": latency_ms,
                    "rule_matched": use_rule,
                }),
            }

            # AC-8: structlog (question_text/answer_text/delta 절대 금지)
            logger.info(
                "qa.stream.completed",
                qa_log_id=qa_log_id,
                user_id=user.id,
                subscription_status=user.subscription_status,
                latency_ms=latency_ms,
                total_tokens=usage.total_tokens,
                cost_usd=float(usage.cost_usd),
                rule_matched=use_rule,
                procedure_count=len(procedures) if use_rule else 0,
            )

        except GeneratorExit:
            # AC-7: 클라이언트 단절 처리
            aborted = True
            latency_ms = int((time.perf_counter() - t0) * 1000)
            log.latency_ms = latency_ms
            await db.commit()
            logger.info(
                "qa.stream.aborted",
                qa_log_id=qa_log_id,
                reason="client_disconnect",
            )
            raise

        except Exception as exc:
            # AC-6: tenacity 최종 실패 또는 기타 예외
            latency_ms = int((time.perf_counter() - t0) * 1000)
            log.latency_ms = latency_ms
            await db.commit()

            code = "OPENAI_TIMEOUT" if isinstance(exc, _RETRY_EXCEPTIONS) else "INTERNAL_ERROR"
            message = (
                "답변 생성이 일시 지연됩니다. 잠시 후 다시 시도해주세요"
                if code == "OPENAI_TIMEOUT"
                else "내부 오류가 발생했습니다. 잠시 후 다시 시도해주세요"
            )
            yield {"event": "error", "data": json.dumps({"code": code, "message": message})}
            logger.error("qa.stream.failed", qa_log_id=qa_log_id, error=str(exc), exc_info=True)
