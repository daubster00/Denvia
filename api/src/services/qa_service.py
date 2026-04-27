"""QA 서비스 — echo(Story 2.1) + stream(Story 2.2) + preflight/quota(Story 2.3)."""

import asyncio
import json
import time
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import structlog
from fastapi import HTTPException
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.integrations.openai.client import TokenUsage, _RETRY_EXCEPTIONS
from api.src.models.qa_log import QALog
from api.src.models.user import User
from api.src.rag_integration import query_runner
from api.src.schemas.qa import QAEchoResponse

logger = structlog.get_logger(__name__)

# ── KST 상수 ──────────────────────────────────────────────────────────────────
KST = ZoneInfo("Asia/Seoul")

DEFAULT_FREE_DAILY_QUOTA = 10
DEFAULT_FREE_DELAY_SECONDS = 0
DEFAULT_PRO_INTERNAL_CAP = 500


# ── quota 키·날짜 헬퍼 ─────────────────────────────────────────────────────────

def _today_key_kst(user_id: int) -> str:
    return f"quota:user:{user_id}:{datetime.now(tz=KST).strftime('%Y-%m-%d')}"


def _next_kst_midnight_iso() -> str:
    now = datetime.now(tz=KST)
    nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return nxt.isoformat()


# ── Redis 조회 헬퍼 ────────────────────────────────────────────────────────────

async def _resolve_int_or_none(redis_runtime: Redis, key: str) -> int | None:
    raw = await redis_runtime.get(key)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


async def _resolve_bool(redis_runtime: Redis, key: str, default: bool = True) -> bool:
    raw = await redis_runtime.get(key)
    if raw is None:
        return default
    return str(raw).lower() not in ("0", "false", "off", "no")


# ── 한도/지연 결정 ─────────────────────────────────────────────────────────────

async def _resolve_daily_limit(user: User, redis_runtime: Redis) -> tuple[int, str]:
    """우선순위: users.daily_quota_override > runtime:free_daily_quota > 10. (limit, source) 반환."""
    if user.subscription_status == "pro":
        cap = await _resolve_int_or_none(redis_runtime, "runtime:pro_internal_cap")
        return (cap if cap is not None else DEFAULT_PRO_INTERNAL_CAP, "pro_internal")
    if user.daily_quota_override is not None:
        return (user.daily_quota_override, "user_override")
    runtime_val = await _resolve_int_or_none(redis_runtime, "runtime:free_daily_quota")
    if runtime_val is not None:
        return (runtime_val, "runtime")
    return (DEFAULT_FREE_DAILY_QUOTA, "default")


async def _resolve_delay(user: User, redis_runtime: Redis) -> tuple[int, str]:
    """무료 지연 결정. pro/admin은 0초 강제. 개별 override > 전역 enabled > runtime delay > default."""
    if user.subscription_status in ("pro", "admin"):
        return (0, "paid_skip")
    if user.free_delay_override is not None:
        return (user.free_delay_override, "user_override")
    enabled = await _resolve_bool(redis_runtime, "runtime:free_delay_enabled", default=True)
    if not enabled:
        return (0, "runtime_disabled")
    runtime_val = await _resolve_int_or_none(redis_runtime, "runtime:free_delay")
    if runtime_val is not None:
        return (runtime_val, "runtime")
    return (DEFAULT_FREE_DELAY_SECONDS, "default")

_ECHO_ANSWER = "[placeholder] 스트리밍은 Story 2.2에서 구현됩니다"


class QAService:
    async def preflight(
        self,
        *,
        user: User,
        redis_quota: Redis,
        redis_runtime: Redis,
    ) -> None:
        """Quota INCR + 의도적 지연. EventSourceResponse 반환 전에 호출 (HTTPException 429 가능).

        admin 사용자: quota·delay 모두 우회 (개발/지원 트래픽).
        pro 사용자: delay 미적용, 내부 안전 상한(pro_internal_cap)만 검증.
        free 사용자: quota INCR → 한도 검증 → sleep.
        """
        if user.subscription_status == "admin":
            return

        key = _today_key_kst(user.id)
        used = await redis_quota.incr(key)
        if used == 1:
            await redis_quota.expire(key, 86400)

        limit, src = await _resolve_daily_limit(user, redis_runtime)

        logger.debug(
            "qa.quota.resolved",
            user_id=user.id,
            source=src,
            daily_limit=limit,
            used_today=used,
        )

        if used > limit:
            is_pro_internal = user.subscription_status == "pro"
            code = (
                "QUOTA_EXCEEDED_INTERNAL_SAFETY_LIMIT"
                if is_pro_internal
                else "QUOTA_EXCEEDED"
            )
            message = (
                "일시적 시스템 보호 제한에 도달했습니다. 고객문의로 연락주세요"
                if is_pro_internal
                else "오늘의 무료 질문 한도를 모두 사용했습니다."
            )
            show_upgrade = (
                False
                if is_pro_internal
                else await _resolve_bool(redis_runtime, "runtime:show_upgrade_prompt", default=True)
            )
            show_subscribe = (
                False
                if is_pro_internal
                else await _resolve_bool(redis_runtime, "runtime:show_subscribe_button", default=True)
            )
            event_name = (
                "qa.quota.exceeded_internal" if is_pro_internal else "qa.quota.exceeded"
            )
            logger.warning(
                event_name,
                user_id=user.id,
                subscription_status=user.subscription_status,
                daily_limit=limit,
                used_today=used,
            )
            raise HTTPException(
                status_code=429,
                detail={
                    "code": code,
                    "message": message,
                    "daily_limit": limit,
                    "used_today": used,
                    "reset_at": _next_kst_midnight_iso(),
                    "show_upgrade_prompt": show_upgrade,
                    "show_subscribe_button": show_subscribe,
                },
            )

        logger.info(
            "qa.quota.consumed",
            user_id=user.id,
            subscription_status=user.subscription_status,
            used_today=used,
            daily_limit=limit,
            remaining=limit - used,
        )

        delay, _dsrc = await _resolve_delay(user, redis_runtime)
        if delay > 0:
            logger.info("qa.free_delay.applied", user_id=user.id, delay_seconds=delay)
            await asyncio.sleep(delay)

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
