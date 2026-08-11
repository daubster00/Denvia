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
    """preflight 결과 — 스트림이 done 이벤트 + 팝업 신호 + 체감 지연 catch-up 에 사용."""

    throttled: bool          # 이번 호출 시점에 anomaly throttle 적용 중인지
    throttle_just_applied: bool  # 이번 호출에서 새로 throttle 이 적용되었는지 (팝업 트리거)
    # throttle_just_applied=True 일 때 어떤 탐지가 trigger 했는지 — 프론트 팝업 문구 분기에 사용.
    # 값: "rapid_followup_questions" | "repeated_question" | None
    throttle_anomaly_type: str | None = None
    # 체감 지연 정책 — stream() 첫 토큰 emit 직전까지 도달해야 할 perf_counter 절대 시각.
    # 관리자 설정 "딜레이"는 "사용자가 질문 보낸 시점 → 첫 토큰 도착 시점"의 총 경과로 해석한다.
    # AI 생성에 걸린 시간이 이미 deadline 을 넘었다면 catch-up 생략, 부족하면 잔여만큼만 sleep.
    # None ⇒ catch-up 불필요 (admin 우회 또는 delay=0).
    deadline_perf: float | None = None
    delay_seconds: float = 0.0     # 적용된 총 딜레이(초). 진단 로그용.
    delay_source: str = ""         # "user_override"|"runtime"|"default"|"anomaly_throttle"|"paid_skip"|"runtime_disabled"


async def catch_up_to_deadline(pr: PreflightResult | None, *, user_id: int | None = None) -> None:
    """첫 토큰 emit 직전 호출. deadline 까지 남은 시간만큼만 sleep (없으면 즉시 반환).

    이 함수가 "AI 생성 시간 = 관리자 딜레이" 인 경우를 깔끔히 0초로 떨어지게 만든다.
    """
    if pr is None or pr.deadline_perf is None:
        return
    remaining = pr.deadline_perf - time.perf_counter()
    if remaining <= 0:
        logger.info(
            "qa.perceived_delay.skipped",
            user_id=user_id,
            delay_seconds=pr.delay_seconds,
            source=pr.delay_source,
            overrun_ms=int(-remaining * 1000),
        )
        return
    logger.info(
        "qa.perceived_delay.catchup",
        user_id=user_id,
        delay_seconds=pr.delay_seconds,
        source=pr.delay_source,
        catchup_ms=int(remaining * 1000),
    )
    await asyncio.sleep(remaining)


class QAService:
    async def preflight(
        self,
        *,
        user: User,
        redis_quota: Redis,
        redis_runtime: Redis,
        db: AsyncSession | None = None,
        question_text: str | None = None,
        ip: str | None = None,
        t_received: float | None = None,
    ) -> PreflightResult:
        """Quota INCR + 체감 지연 deadline 계산. EventSourceResponse 반환 전에 호출 (HTTPException 429 가능).

        admin 사용자: quota·delay 모두 우회 (개발/지원 트래픽).
        pro 사용자: delay 미적용, 내부 안전 상한(pro_internal_cap)만 검증.
        free 사용자: quota INCR → 한도 검증 → deadline 계산만 (실제 sleep 은 stream() 이 첫 토큰 직전에 수행).

        rapid_followup_questions 탐지(편차 +1) — 답변 완료 후 3초 이내 후속
        질문 연속 3회. 임계 도달 시 users.anomaly_throttled_at 채워 다음 질의부터
        runtime:anomaly_throttle_{free,pro}_delay 만큼 sleep.

        repeated_question 탐지 — 동일 텍스트(trim 일치) 연속 3회. 임계 도달 시
        rapid_followup 과 동일 조치(즉시 throttle + 자동 actioned).

        t_received: 라우터가 요청 진입 시점에 캡쳐한 perf_counter. None 이면 이 함수 진입 시점을 기준으로 한다.
            "사용자가 질문을 보낸 시점부터 첫 토큰 도착까지" 가 관리자 딜레이값이 되도록 catch-up deadline 의 기준점.
        """
        if user.subscription_status == "admin":
            return PreflightResult(
                throttled=False,
                throttle_just_applied=False,
                throttle_anomaly_type=None,
                deadline_perf=None,
                delay_seconds=0.0,
                delay_source="paid_skip",
            )

        t0 = time.perf_counter()
        # 체감 지연 기준점: 라우터가 캡쳐한 시각이 있으면 그것, 없으면 preflight 진입 시점.
        # 라우터 → preflight 사이의 quota/anomaly 처리 시간도 "사용자 체감 지연" 에 포함되어야 정확.
        t_anchor = t_received if t_received is not None else t0

        throttle_just_applied = False
        throttle_anomaly_type: str | None = None
        # db 가 주어진 경우에만 anomaly 탐지/플래그 갱신 수행 — 단위 테스트(fakeredis 만 사용) 호환.
        if db is not None:
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
            if rapid_just_applied:
                throttle_anomaly_type = "rapid_followup_questions"
            elif repeated_just_applied:
                throttle_anomaly_type = "repeated_question"

            # 주의 — 트리거 질문(이번 호출에서 throttle 이 새로 적용된 그 질문) 자체에는
            # throttle delay 를 걸지 않는다. 사용자에게 "이 답변까지는 평소 속도로 받고,
            # 답변이 끝나는 순간 알림이 뜨며, 그 다음 질문부터 속도가 느려진다" 는 직관을 준다.
            # 다음 요청에서 get_current_user 가 DB 에서 anomaly_throttled_at 을 새로 읽어
            # 자연스럽게 throttle 분기가 켜진다. show_popup 은 throttle_just_applied 그대로 사용.
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

        # anomaly throttle 분기 — 트리거 질문(throttle_just_applied=True) 자체는 무조건 제외한다.
        # "이 답변까지는 평소 속도 + 답변 끝나면 알림, 그 다음 질문부터 throttle" 정책의 가드.
        # 트리거 질문에서는 user.anomaly_throttled_at 가 어떤 경로로든 채워졌더라도 delay 분기 차단.
        throttle_active = (
            user.anomaly_throttled_at is not None
            and not throttle_just_applied
        )
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

        t_preflight_done_ms = int((time.perf_counter() - t0) * 1000)
        delay_float = float(delay)
        # 체감 지연 deadline: 사용자 질문 접수 시각(t_anchor) + 관리자 딜레이.
        # stream() 이 첫 토큰 emit 직전에 catch_up_to_deadline() 으로 도달 보장.
        # delay 가 0 이면 catch-up 불필요 → None.
        deadline_perf = (t_anchor + delay_float) if delay_float > 0 else None
        if delay_float > 0:
            logger.info(
                "qa.perceived_delay.scheduled",
                user_id=user.id,
                delay_seconds=delay_float,
                source=dsrc,
                preflight_elapsed_ms=int((time.perf_counter() - t_anchor) * 1000),
            )

        # 진단용 elapsed breakdown (TTFT 추적). PII 없음.
        logger.info(
            "qa.preflight.timings_ms",
            user_id=user.id,
            subscription_status=user.subscription_status,
            anomaly_ms=t_anomaly_ms,
            quota_ms=t_quota_ms,
            preflight_done_ms=t_preflight_done_ms,
            total_ms=int((time.perf_counter() - t0) * 1000),
            free_delay_seconds=delay_float,
            throttled=throttle_active,
        )

        return PreflightResult(
            throttled=throttle_active,
            throttle_just_applied=throttle_just_applied,
            throttle_anomaly_type=throttle_anomaly_type,
            deadline_perf=deadline_perf,
            delay_seconds=delay_float,
            delay_source=dsrc,
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
        device_type: str | None = None,
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
            extract_procedures,
            get_periodontal_result,
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
            device_type=device_type,  # #141 — 접속 기기(mobile/pc/unknown)
        )
        db.add(log)
        await db.flush()
        await db.refresh(log)
        qa_log_id = log.id
        await db.commit()  # 별도 트랜잭션 — 스트리밍 중 락 회피
        t_log_insert_ms = int((time.perf_counter() - t0) * 1000)

        # #141 — 생성 스레드가 완성 답변을 만든 순간(연결 끊김 여부 무관) 호출되는 콜백.
        # 이벤트 루프에 백그라운드 저장 코루틴을 스케줄한다(스레드→루프, fire-and-forget).
        # 유저가 끊겨 아래 정상 경로 UPDATE 가 못 돌아도 완성 답변이 DB에 남는다.
        loop = asyncio.get_running_loop()

        def _persist_full_from_thread(
            full_text: str,
            usage_bg: TokenUsage,
            docs_bg: list[dict] | None = None,
            prompt_bg: str | None = None,
        ) -> None:
            try:
                latency_bg = int((time.perf_counter() - t0) * 1000)
                # #142 — 끊김 저장 경로도 정상 경로와 동일한 관리자 감사정보를 남긴다.
                # normalized 는 스트리밍 시작(=이 콜백 호출) 전에 이미 확정돼 클로저로 안전.
                asyncio.run_coroutine_threadsafe(
                    self._guarded_persist_full(
                        qa_log_id,
                        full_text,
                        usage_bg,
                        latency_bg,
                        retrieved_docs=docs_bg or [],
                        prompt_text=prompt_bg,
                        normalized_query=normalized,
                    ),
                    loop,
                )
            except Exception as exc:  # pragma: no cover - 스케줄 실패는 극히 드묾
                logger.warning(
                    "qa.stream.persist_schedule_failed", qa_log_id=qa_log_id, error=str(exc)
                )

        try:
            # RAG 자산 호출 — vendor/rag CLI 순서 보존 (ADR-0002 §결정 1·2)
            await query_runner.ensure_initialized()
            t_init_ms = int((time.perf_counter() - t0) * 1000)
            scaled = await asyncio.to_thread(apply_scaling_rules, question_text)
            # 게시판 #105: vendor 파일 기반 get_syn_dict 대신 DB(synonym_groups)→Redis
            # 기반 dict를 사용해 관리자 동의어 편집이 라이브 챗봇에 즉시 반영되게 한다.
            syn_dict = await query_runner.get_synonyms_dict()
            normalized = await asyncio.to_thread(normalize_query, scaled, syn_dict)
            rule_answer = await asyncio.to_thread(generate_rule_answer, normalized)
            procedures = await asyncio.to_thread(extract_procedures, normalized)
            # 게시판 #139/#140 — 치주낭측정검사 횟수 자동산정(최우선 결정형 우회).
            # 트리거 a(치주낭)·b(치식)·c(몇/회/횟수) 3요인이 모두 걸릴 때만 not-None.
            periodontal_result = await asyncio.to_thread(get_periodontal_result, normalized)
            t_prep_done_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(
                "qa.stream.prep_timings_ms",
                qa_log_id=qa_log_id,
                user_id=user.id,
                device_type=device_type,  # #141 — 끊김 진단용 접속 기기
                log_insert_ms=t_log_insert_ms,
                ensure_init_ms=t_init_ms - t_log_insert_ms,
                rag_prep_5_steps_ms=t_prep_done_ms - t_init_ms,
                total_before_llm_ms=t_prep_done_ms,
            )

            # AC-2 분기 조건 (원본 CLI 기준, ADR-0002 §결정 1)
            # 우선순위(클라이언트 139 순서): 치주낭측정 → 장애인가산 룰 → RAG.
            use_periodontal = periodontal_result is not None
            use_rule = (
                not use_periodontal
                and "장애인" in normalized
                and "가산" in normalized
                and rule_answer is not None
            )
            # 결정형 우회(치주낭·장애인가산)는 rule_matched=True 로 집계한다.
            # 치주낭은 LLM 을 태우지만(계산값 그대로 출력) 성격상 규칙 기반 답변이다.
            rule_matched_flag = use_periodontal or use_rule

            retrieved_docs_payload: list[dict] = []
            # 관리자 질문 상세 패널 — LLM 에 실제로 들어간 최종 프롬프트.
            # 장애인가산 룰 경로는 LLM 호출 자체가 없으므로 None 유지(치주낭은 프롬프트 기록).
            prompt_text_payload: str | None = None

            if use_periodontal:
                # 치주낭측정 경로: 계산값(count)을 build_periodontal_llm_prompt 로 감싸
                # LLM 스트리밍(RAG 검색 없음). UI 는 RAG 와 동일하게 token 다회 → done.
                # (장애인 전용 rule_matched 이벤트/procedure_count 는 쏘지 않는다.)
                count, detail = periodontal_result
                accumulated_chunks_p: list[str] = []
                usage_holder_p: list[TokenUsage] = []
                docs_holder_p: list[list[dict]] = []
                prompt_holder_p: list[str | None] = []

                def _on_complete_p(
                    u: TokenUsage,
                    full: str,
                    docs: list[dict],
                    prompt: str | None = None,
                ) -> None:
                    usage_holder_p.append(u)
                    docs_holder_p.append(docs)
                    prompt_holder_p.append(prompt)

                async for token in query_runner.stream_periodontal_answer(
                    question_text, count, detail, _on_complete_p,
                    on_thread_complete=_persist_full_from_thread,
                ):
                    if not first_token_logged:
                        await catch_up_to_deadline(preflight_result, user_id=user.id)
                        logger.info(
                            "qa.stream.first_token_ms",
                            qa_log_id=qa_log_id,
                            user_id=user.id,
                            path="periodontal",
                            ttft_ms=int((time.perf_counter() - t0) * 1000),
                        )
                        first_token_logged = True
                    accumulated_chunks_p.append(token)
                    yield {"event": "token", "data": json.dumps({"delta": token})}

                accumulated = "".join(accumulated_chunks_p)
                usage = usage_holder_p[0] if usage_holder_p else TokenUsage(0, 0, 0, 0.0)
                retrieved_docs_payload = docs_holder_p[0] if docs_holder_p else []
                prompt_text_payload = prompt_holder_p[0] if prompt_holder_p else None
            elif use_rule:
                # 룰 응답 경로: rule_matched → token 1회 → done
                # 체감 지연 보장 — 첫 사용자 가시 이벤트(rule_matched) 직전에 deadline 까지 대기.
                await catch_up_to_deadline(preflight_result, user_id=user.id)
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
                prompt_holder: list[str | None] = []

                def _on_complete(
                    u: TokenUsage,
                    full: str,
                    docs: list[dict],
                    prompt: str | None = None,
                ) -> None:
                    usage_holder.append(u)
                    docs_holder.append(docs)
                    prompt_holder.append(prompt)

                async for token in query_runner.stream_rag_answer(
                    normalized, _on_complete, on_thread_complete=_persist_full_from_thread
                ):
                    if not first_token_logged:
                        # 체감 지연 보장 — 사용자가 보게 될 첫 토큰 emit 직전에 deadline 까지 대기.
                        await catch_up_to_deadline(preflight_result, user_id=user.id)
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
                prompt_text_payload = prompt_holder[0] if prompt_holder else None

            latency_ms = int((time.perf_counter() - t0) * 1000)

            # AC-4: qa_logs UPDATE
            log.answer_text = accumulated
            log.rule_matched = rule_matched_flag
            log.input_tokens = usage.input_tokens
            log.output_tokens = usage.output_tokens
            log.cost_usd = Decimal(str(usage.cost_usd))
            log.latency_ms = latency_ms
            log.status = "completed"
            # #141 — 여기까지 왔으면 클라가 연결돼 답변을 정상 수신 중이다. delivered=True 로
            # 마킹해 재생 대상에서 제외한다(백그라운드 guarded persist 는 delivered=False 로
            # 남기지만, 이 UPDATE 가 최종 권위로 True 를 확정한다).
            log.delivered = True
            # 관리자 감사용 — 동의어 치환 후 쿼리와 top-k 문서 (rule 경로면 docs는 빈 리스트)
            log.normalized_query = normalized
            log.retrieved_docs = retrieved_docs_payload
            # LLM 에 실제 들어간 최종 프롬프트(템플릿 + 질문 + 컨텍스트 치환 완료).
            # 룰 경로는 LLM 호출 자체가 없어 None.
            log.prompt_text = prompt_text_payload
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
                    "rule_matched": rule_matched_flag,
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
                rule_matched=rule_matched_flag,
                path="periodontal" if use_periodontal else ("rule" if use_rule else "rag"),
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

        except query_runner.FirstTokenTimeoutError:
            # 게시판 #112 후속 — 첫 토큰 45초 상한 초과. 추론이 길어 첫 글자조차 못 낸
            # 무거운 질문(전악 치식 나열 등)이 무한 로딩으로 남던 것을 확실히 끊는다.
            # latency_ms 를 기록해 리퍼가 청소하는 'in_progress' 고아(latency NULL)와 구분한다.
            latency_ms = int((time.perf_counter() - t0) * 1000)
            log.latency_ms = latency_ms
            log.status = "error"
            await db.commit()
            yield {
                "event": "error",
                "data": json.dumps({
                    "code": "SLOW_QUESTION",
                    "message": "질문이 복잡해 답변이 지연되고 있어요. 잠시 후 다시 시도해주세요.",
                }),
            }
            logger.warning(
                "qa.stream.first_token_timeout",
                qa_log_id=qa_log_id,
                user_id=user.id,
                latency_ms=latency_ms,
            )

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

    async def _guarded_persist_full(
        self,
        qa_log_id: int,
        full_text: str,
        usage: TokenUsage,
        latency_ms: int,
        *,
        retrieved_docs: list[dict] | None = None,
        prompt_text: str | None = None,
        normalized_query: str | None = None,
    ) -> None:
        """#141 — 백그라운드 스레드가 완성한 답변을, 아직 확정 안 된(in_progress) 행에
        한해 저장한다. 유저 연결이 끊겨 정상 경로 UPDATE 가 못 돈 경우의 안전망.
        delivered=False 로 남겨 재시도 재생 대상이 되게 한다. 정상 전송된 행
        (status!='in_progress')은 WHERE 조건에서 걸러져 건드리지 않는다(멱등)."""
        from sqlalchemy import text as _sql_text

        from api.src.models.base import async_session_factory

        try:
            async with async_session_factory() as s:
                res = await s.execute(
                    _sql_text(
                        "UPDATE qa_logs SET answer_text=:ans, status='completed', "
                        "delivered=false, latency_ms=:lat, input_tokens=:it, "
                        "output_tokens=:ot, cost_usd=:cost, "
                        "retrieved_docs=cast(:docs as jsonb), prompt_text=:prompt, "
                        "normalized_query=:nq "
                        "WHERE id=:id AND status='in_progress'"
                    ),
                    {
                        "ans": full_text,
                        "lat": latency_ms,
                        "it": usage.input_tokens,
                        "ot": usage.output_tokens,
                        "cost": str(usage.cost_usd),
                        "docs": json.dumps(retrieved_docs or []),
                        "prompt": prompt_text,
                        "nq": normalized_query,
                        "id": qa_log_id,
                    },
                )
                await s.commit()
            if res.rowcount:
                # rowcount>0 = 정상 경로가 아직 확정 못 한 행을 백그라운드가 저장 = 끊김 케이스.
                logger.info("qa.stream.persisted_undelivered", qa_log_id=qa_log_id)
        except Exception as exc:  # pragma: no cover - 백그라운드 저장 실패는 로그만
            logger.warning(
                "qa.stream.guarded_persist_failed", qa_log_id=qa_log_id, error=str(exc)
            )

    async def find_replayable(
        self,
        db: AsyncSession,
        *,
        user: User,
        question_text: str,
    ) -> QALog | None:
        """#141 — 최근(3분 이내) 같은 질문에 대해 '완성됐지만 전송 못 한'(delivered=False)
        답변이 있으면 반환한다. 있으면 재시도 시 OpenAI 재호출·횟수 차감 없이 재생한다."""
        from sqlalchemy import select

        cutoff = datetime.now(timezone.utc) - timedelta(minutes=3)
        stmt = (
            select(QALog)
            .where(
                QALog.user_id == user.id,
                QALog.question_text == question_text,
                QALog.status == "completed",
                QALog.delivered.is_(False),
                QALog.created_at >= cutoff,
            )
            .order_by(QALog.created_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def stream_saved(self, db: AsyncSession, log: QALog) -> AsyncIterator[dict]:
        """#141 — DB에 저장된 완성 답변을 그대로 재생(SSE)한다. OpenAI 호출·횟수 차감 없음.
        재생 즉시 delivered=True 로 마킹해 중복 재생을 막는다."""
        log.delivered = True
        await db.commit()

        answer = log.answer_text or ""
        logger.info(
            "qa.stream.replayed", qa_log_id=log.id, user_id=log.user_id, chars=len(answer)
        )
        # 프론트 타자기 애니메이션이 살아있도록 저장 답변을 한 토큰으로 흘려보낸다.
        if answer:
            yield {"event": "token", "data": json.dumps({"delta": answer})}
        yield {
            "event": "done",
            "data": json.dumps({
                "qa_log_id": log.id,
                "total_tokens": (log.input_tokens or 0) + (log.output_tokens or 0),
                "cost_usd": 0.0,
                "latency_ms": 0,
                "rule_matched": bool(log.rule_matched),
                "replayed": True,
            }),
        }
