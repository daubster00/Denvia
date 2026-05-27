"""QA 서비스 — echo(Story 2.1) + stream(Story 2.2) + preflight/quota(Story 2.3)."""

import asyncio
import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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
from api.src.services import anomaly_service, runtime_config_service

logger = structlog.get_logger(__name__)

# ── KST 상수 ──────────────────────────────────────────────────────────────────
KST = ZoneInfo("Asia/Seoul")

DEFAULT_FREE_DAILY_QUOTA = 10
DEFAULT_FREE_DELAY_SECONDS: Decimal = Decimal("0")
DEFAULT_PRO_INTERNAL_CAP = 500
# Pro 월 질문 한도 — 관리자(컨텐츠→서비스 토글)에서 편집. 기본 500/월.
DEFAULT_PRO_MONTHLY_QUOTA = 500
# admin은 preflight에서 quota/delay 모두 우회한다(qa_service.preflight 참고).
# /me/quota 응답에서도 일반 limit 계산을 타지 않도록 충분히 큰 sentinel을 사용해
# UI가 "제한된 값"으로 오해하지 않게 한다.
ADMIN_UNLIMITED_LIMIT = 999_999


# ── quota 키·날짜 헬퍼 ─────────────────────────────────────────────────────────

def _today_key_kst(user_id: int) -> str:
    return f"quota:user:{user_id}:{datetime.now(tz=KST).strftime('%Y-%m-%d')}"


def _month_key_kst(user_id: int) -> str:
    """Pro 월 한도용 INCR 키 — KST 월초 기준 분리. 자정 리셋과 독립적으로 누적."""
    return f"quota:user:{user_id}:month:{datetime.now(tz=KST).strftime('%Y-%m')}"


def _next_kst_midnight_iso() -> str:
    now = datetime.now(tz=KST)
    nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return nxt.isoformat()


def _next_kst_month_start_iso() -> str:
    """다음 달 1일 00:00 KST ISO 8601 — Pro 월 한도 리셋 안내용."""
    now = datetime.now(tz=KST)
    if now.month == 12:
        nxt = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        nxt = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return nxt.isoformat()


def _seconds_until_next_kst_month() -> int:
    """월간 카운터 TTL — 다음 달 1일 00:00 KST 까지의 초. Redis EXPIRE 인자."""
    now = datetime.now(tz=KST)
    if now.month == 12:
        nxt = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        nxt = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return int((nxt - now).total_seconds())


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


async def _resolve_pro_monthly_limit(redis_runtime: Redis) -> int:
    """Pro 월 한도 — 관리자(컨텐츠→서비스 토글) 설정값. 미설정/손상 시 기본 500."""
    raw = await _resolve_int_or_none(redis_runtime, "runtime:pro_monthly_quota")
    return raw if raw is not None else DEFAULT_PRO_MONTHLY_QUOTA


async def _resolve_delay(user: User, redis_runtime: Redis) -> tuple[Decimal, str]:
    """무료 지연 결정. pro/admin은 0초 강제. 개별 override > 전역 enabled > runtime delay > default.

    Story 6.3 — 반환 타입을 ``tuple[Decimal, str]``로 확장 (0.1초 정밀도).
    개별 override는 ORM에서 ``Decimal`` 값으로 들어오고, runtime/default는 ``Decimal`` 승격.
    """
    if user.subscription_status in ("pro", "admin"):
        return (Decimal("0"), "paid_skip")
    if user.free_delay_override is not None:
        return (user.free_delay_override, "user_override")
    enabled = await _resolve_bool(redis_runtime, "runtime:free_delay_enabled", default=True)
    if not enabled:
        return (Decimal("0"), "runtime_disabled")
    runtime_val = await _resolve_int_or_none(redis_runtime, "runtime:free_delay")
    if runtime_val is not None:
        return (Decimal(runtime_val), "runtime")
    return (DEFAULT_FREE_DELAY_SECONDS, "default")

_ECHO_ANSWER = "[placeholder] 스트리밍은 Story 2.2에서 구현됩니다"


@dataclass(frozen=True)
class PreflightResult:
    """preflight 결과 — 스트림이 done 이벤트 + 팝업 신호에 사용."""

    throttled: bool          # 이번 호출 시점에 anomaly throttle 적용 중인지
    throttle_just_applied: bool  # 이번 호출에서 새로 throttle 이 적용되었는지 (팝업 트리거)
    # throttle_just_applied=True 일 때 어떤 탐지가 trigger 했는지 — 프론트 팝업 문구 분기에 사용.
    # 값: "rapid_followup_questions" | "repeated_question" | None
    throttle_anomaly_type: str | None = None


class QAService:
    async def preflight(
        self,
        *,
        user: User,
        redis_quota: Redis,
        redis_runtime: Redis,
        db: AsyncSession,
        question_text: str | None = None,
        ip: str | None = None,
    ) -> PreflightResult:
        """Quota INCR + 의도적 지연. EventSourceResponse 반환 전에 호출 (HTTPException 429 가능).

        admin 사용자: quota·delay 모두 우회 (개발/지원 트래픽).
        pro 사용자: delay 미적용, 내부 안전 상한(pro_internal_cap)만 검증.
        free 사용자: quota INCR → 한도 검증 → sleep.

        rapid_followup_questions 탐지(편차 +1) — 답변 완료 후 3초 이내 후속
        질문 연속 3회. 임계 도달 시 users.anomaly_throttled_at 채워 다음 질의부터
        runtime:anomaly_throttle_{free,pro}_delay 만큼 sleep.

        repeated_question 탐지 — 동일 텍스트(trim 일치) 연속 3회. 임계 도달 시
        rapid_followup 과 동일 조치(즉시 throttle + 자동 actioned).
        """
        if user.subscription_status == "admin":
            return PreflightResult(
                throttled=False,
                throttle_just_applied=False,
                throttle_anomaly_type=None,
            )

        t0 = time.perf_counter()

        # rapid_followup_questions 탐지 (답변 직후 3초 이내 연속 3회)
        rapid_just_applied = await anomaly_service.check_rapid_followup_questions(
            user_id=user.id,
            subscription_status=user.subscription_status,
            redis_quota=redis_quota,
            db=db,
            ip=ip,
        )

        # repeated_question 탐지 (동일 텍스트 연속 3회) — question_text 제공 시에만.
        repeated_just_applied = False
        if question_text is not None:
            repeated_just_applied = await anomaly_service.check_repeated_question(
                user_id=user.id,
                subscription_status=user.subscription_status,
                question_text=question_text,
                redis_quota=redis_quota,
                db=db,
                ip=ip,
            )

        # 두 hook 중 하나라도 새로 throttle 을 걸었으면 팝업 트리거.
        # rapid_followup 이 먼저 평가되므로 동시 trigger 가능성은 낮지만, 둘 다 True 면
        # rapid 를 우선한다 — 답변 직후 3초 패턴이 더 명확한 신호.
        throttle_just_applied = rapid_just_applied or repeated_just_applied
        throttle_anomaly_type: str | None = None
        if rapid_just_applied:
            throttle_anomaly_type = "rapid_followup_questions"
        elif repeated_just_applied:
            throttle_anomaly_type = "repeated_question"

        if throttle_just_applied:
            # 메모리상 user 객체에도 반영 — 아래 throttle 분기에서 즉시 사용.
            user.anomaly_throttled_at = datetime.now(tz=timezone.utc)

        try:
            await db.commit()
        except Exception:
            await db.rollback()
        t_anomaly_ms = int((time.perf_counter() - t0) * 1000)

        key = _today_key_kst(user.id)
        used = await redis_quota.incr(key)
        if used == 1:
            await redis_quota.expire(key, 86400)

        limit, src = await _resolve_daily_limit(user, redis_runtime)
        t_quota_ms = int((time.perf_counter() - t0) * 1000) - t_anomaly_ms

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

        # Pro 사용자 월 한도 검증 — 관리자 설정(runtime:pro_monthly_quota) 기준.
        # 일 한도(pro_internal_cap)는 시스템 보호용 일일 상한이고, 월 한도가 상품 기획상의 한도다.
        # 두 카운터는 독립이며, 월 한도 초과 시 사용자 친화 메시지로 429.
        if user.subscription_status == "pro":
            month_key = _month_key_kst(user.id)
            used_month = await redis_quota.incr(month_key)
            if used_month == 1:
                await redis_quota.expire(month_key, _seconds_until_next_kst_month())
            monthly_limit = await _resolve_pro_monthly_limit(redis_runtime)
            if used_month > monthly_limit:
                logger.warning(
                    "qa.quota.exceeded_monthly",
                    user_id=user.id,
                    subscription_status="pro",
                    monthly_limit=monthly_limit,
                    used_month=used_month,
                )
                raise HTTPException(
                    status_code=429,
                    detail={
                        "code": "QUOTA_EXCEEDED_MONTHLY",
                        "message": "이번달 질문 한도를 모두 사용했습니다.",
                        "monthly_limit": monthly_limit,
                        "used_month": used_month,
                        "reset_at": _next_kst_month_start_iso(),
                        "show_upgrade_prompt": False,
                        "show_subscribe_button": False,
                    },
                )
            logger.info(
                "qa.quota.consumed_monthly",
                user_id=user.id,
                used_month=used_month,
                monthly_limit=monthly_limit,
                remaining_month=monthly_limit - used_month,
            )

        delay, dsrc = await _resolve_delay(user, redis_runtime)

        # 신규 — 사용자에게 anomaly throttle 이 적용 중이면 throttle delay 로 override.
        # max(base_delay, throttle_delay) — throttle 이 항상 더 길거나 같게 보장.
        throttle_active = user.anomaly_throttled_at is not None
        if throttle_active:
            throttle_delay, throttle_enabled = (
                await runtime_config_service.resolve_anomaly_throttle_delay(
                    redis_runtime,
                    subscription_status=user.subscription_status,
                )
            )
            if throttle_enabled and throttle_delay > delay:
                delay = throttle_delay
                dsrc = "anomaly_throttle"

        t_before_sleep_ms = int((time.perf_counter() - t0) * 1000)
        if delay > 0:
            delay_float = float(delay)
            logger.info(
                "qa.free_delay.applied",
                user_id=user.id,
                delay_seconds=delay_float,
                source=dsrc,
            )
            await asyncio.sleep(delay_float)

        # 진단용 elapsed breakdown (TTFT 추적). PII 없음.
        logger.info(
            "qa.preflight.timings_ms",
            user_id=user.id,
            subscription_status=user.subscription_status,
            anomaly_ms=t_anomaly_ms,
            quota_ms=t_quota_ms,
            pre_sleep_ms=t_before_sleep_ms,
            total_ms=int((time.perf_counter() - t0) * 1000),
            free_delay_seconds=float(delay) if delay > 0 else 0.0,
            throttled=throttle_active,
        )

        return PreflightResult(
            throttled=throttle_active,
            throttle_just_applied=throttle_just_applied,
            throttle_anomaly_type=throttle_anomaly_type,
        )

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
            status="completed",
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
        *,
        redis_quota: Redis | None = None,
        preflight_result: PreflightResult | None = None,
    ) -> AsyncIterator[dict]:
        """SSE 이벤트를 yield하는 async generator.

        yield 형식: {"event": "token", "data": json.dumps(...)} — sse-starlette 호환.
        AC-4: 요청 시작 시 즉시 INSERT → 종료 시 UPDATE 패턴.
        AC-7: 클라이언트 단절은 GeneratorExit 또는 asyncio.CancelledError로 전달될 수 있다.
            asyncio.CancelledError는 BaseException 하위라 except Exception에 잡히지 않으므로
            GeneratorExit과 함께 명시적으로 처리해 status='aborted' commit을 보장한다.
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
        first_token_logged = False

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
        t_log_insert_ms = int((time.perf_counter() - t0) * 1000)

        try:
            # RAG 자산 호출 — vendor/rag CLI 순서 보존 (ADR-0002 §결정 1·2)
            await query_runner.ensure_initialized()
            t_init_ms = int((time.perf_counter() - t0) * 1000)
            scaled = await asyncio.to_thread(apply_scaling_rules, question_text)
            syn_dict = await asyncio.to_thread(get_syn_dict)
            normalized = await asyncio.to_thread(normalize_query, scaled, syn_dict)
            rule_answer = await asyncio.to_thread(generate_rule_answer, normalized)
            procedures = await asyncio.to_thread(extract_procedures, normalized)
            t_prep_done_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(
                "qa.stream.prep_timings_ms",
                qa_log_id=qa_log_id,
                user_id=user.id,
                log_insert_ms=t_log_insert_ms,
                ensure_init_ms=t_init_ms - t_log_insert_ms,
                rag_prep_5_steps_ms=t_prep_done_ms - t_init_ms,
                total_before_llm_ms=t_prep_done_ms,
            )

            # AC-2 분기 조건 (원본 CLI 기준, ADR-0002 §결정 1)
            use_rule = (
                "장애인" in normalized
                and "가산" in normalized
                and rule_answer is not None
            )

            retrieved_docs_payload: list[dict] = []

            if use_rule:
                # 룰 응답 경로: rule_matched → token 1회 → done
                yield {"event": "rule_matched", "data": json.dumps({"procedure_count": len(procedures)})}
                logger.info(
                    "qa.stream.first_token_ms",
                    qa_log_id=qa_log_id,
                    user_id=user.id,
                    path="rule",
                    ttft_ms=int((time.perf_counter() - t0) * 1000),
                )
                first_token_logged = True
                yield {"event": "token", "data": json.dumps({"delta": rule_answer})}
                accumulated = rule_answer
                usage = TokenUsage(0, 0, 0, 0.0)
            else:
                # RAG 경로: stream_rag_answer async iter → token 다회 → done
                accumulated_chunks: list[str] = []
                usage_holder: list[TokenUsage] = []
                docs_holder: list[list[dict]] = []

                def _on_complete(u: TokenUsage, full: str, docs: list[dict]) -> None:
                    usage_holder.append(u)
                    docs_holder.append(docs)

                async for token in query_runner.stream_rag_answer(normalized, _on_complete):
                    if not first_token_logged:
                        logger.info(
                            "qa.stream.first_token_ms",
                            qa_log_id=qa_log_id,
                            user_id=user.id,
                            path="rag",
                            ttft_ms=int((time.perf_counter() - t0) * 1000),
                        )
                        first_token_logged = True
                    accumulated_chunks.append(token)
                    yield {"event": "token", "data": json.dumps({"delta": token})}

                accumulated = "".join(accumulated_chunks)
                usage = usage_holder[0] if usage_holder else TokenUsage(0, 0, 0, 0.0)
                retrieved_docs_payload = docs_holder[0] if docs_holder else []

            latency_ms = int((time.perf_counter() - t0) * 1000)

            # AC-4: qa_logs UPDATE
            log.answer_text = accumulated
            log.rule_matched = use_rule
            log.input_tokens = usage.input_tokens
            log.output_tokens = usage.output_tokens
            log.cost_usd = Decimal(str(usage.cost_usd))
            log.latency_ms = latency_ms
            log.status = "completed"
            # 관리자 감사용 — 동의어 치환 후 쿼리와 top-k 문서 (rule 경로면 docs는 빈 리스트)
            log.normalized_query = normalized
            log.retrieved_docs = retrieved_docs_payload
            await db.commit()

            # 신규 — 이상탐지 throttle 상태 전달. 무료 사용자는 throttle_just_applied=True 면
            # 프론트에서 팝업을 띄운다 (유료는 팝업 노출 없음).
            throttle_payload: dict = {}
            if preflight_result is not None:
                throttle_payload = {
                    "throttled": preflight_result.throttled,
                    "throttle_just_applied": preflight_result.throttle_just_applied,
                    "show_popup": (
                        preflight_result.throttle_just_applied
                        and user.subscription_status == "free"
                    ),
                    # 프론트에서 팝업 문구를 케이스별로 분기하기 위해 trigger 타입 동봉.
                    # rapid_followup_questions | repeated_question | null.
                    "anomaly_type": preflight_result.throttle_anomaly_type,
                }

            yield {
                "event": "done",
                "data": json.dumps({
                    "qa_log_id": qa_log_id,
                    "total_tokens": usage.total_tokens,
                    "cost_usd": float(usage.cost_usd),
                    "latency_ms": latency_ms,
                    "rule_matched": use_rule,
                    **throttle_payload,
                }),
            }

            # 신규 — 다음 후속 질의 탐지를 위한 답변 완료 시각 기록.
            if redis_quota is not None:
                await anomaly_service.record_stream_done(
                    user_id=user.id,
                    subscription_status=user.subscription_status,
                    redis_quota=redis_quota,
                )

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

        except (GeneratorExit, asyncio.CancelledError) as exc:
            # AC-7: 클라이언트 단절/요청 취소 처리
            # GeneratorExit: 소비자가 aclose() 또는 close() 호출 시
            # asyncio.CancelledError: FastAPI/Starlette가 요청 취소 시 generator로 전달
            # 둘 다 BaseException 하위이므로 일반 except Exception 블록에 잡히지 않는다.
            aborted = True
            latency_ms = int((time.perf_counter() - t0) * 1000)
            log.latency_ms = latency_ms
            log.status = "aborted"
            await db.commit()
            logger.info(
                "qa.stream.aborted",
                qa_log_id=qa_log_id,
                reason="client_disconnect",
                exc_type=type(exc).__name__,
            )
            raise

        except Exception as exc:
            # AC-6: tenacity 최종 실패 또는 기타 예외
            latency_ms = int((time.perf_counter() - t0) * 1000)
            log.latency_ms = latency_ms
            log.status = "error"
            await db.commit()

            code = "OPENAI_TIMEOUT" if isinstance(exc, _RETRY_EXCEPTIONS) else "INTERNAL_ERROR"
            message = (
                "답변 생성이 일시 지연됩니다. 잠시 후 다시 시도해주세요"
                if code == "OPENAI_TIMEOUT"
                else "내부 오류가 발생했습니다. 잠시 후 다시 시도해주세요"
            )
            yield {"event": "error", "data": json.dumps({"code": code, "message": message})}
            logger.error("qa.stream.failed", qa_log_id=qa_log_id, error=str(exc), exc_info=True)
