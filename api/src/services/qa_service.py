"""QA 서비스 — echo(Story 2.1) + stream(Story 2.2) + preflight/quota(Story 2.3)."""

import asyncio
import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

import structlog
from fastapi import HTTPException
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.integrations.openai.client import TokenUsage, _RETRY_EXCEPTIONS
from api.src.models.qa_log import QALog
from api.src.models.user import User
from api.src.rag_integration import query_runner
from api.src.rag_integration.question_completeness import (
    ANSWER_KIND_CLARIFICATION,
    CLARIFY_MESSAGE,
    needs_clarification,
)
from api.src.schemas.qa import QAEchoResponse
from api.src.services import anomaly_service, runtime_config_service
from api.src.services.chat_history_service import (
    ConversationTurn,
    HistoryState,
    _rollback_quietly,
    build_history_block,
    prepare_history,
)

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

# 저장 답변 재생 권한(claim)의 리스 길이(초) — 재수정 P1-1.
# 재생 중 연결이 끊기면 선점을 즉시 풀지만, 그 해제조차 못 돌아가는 경우(프로세스 종료
# 등)에 행이 영구히 잠기면 안 된다. 이 시간이 지난 선점은 만료로 보고 다시 가져간다.
# 저장 답변 1건을 흘려보내는 데 필요한 시간보다 넉넉하고, 사용자가 재시도를 기다릴 수
# 있는 범위여야 한다.
REPLAY_CLAIM_LEASE_SECONDS = 30


@dataclass(frozen=True)
class ReplayClaim:
    """저장 답변 재생 권한을 선점한 결과 (재수정 P1-1).

    ORM 엔티티를 그대로 들고 다니지 않는 이유: 재생 경로는 세션 상태에 의존하지 않고
    "선점 당시 읽은 값" 만으로 SSE 를 흘려보내야 한다(선점 UPDATE 와 같은 왕복에서
    RETURNING 으로 받은 값이다).

    - ``claim_token``: 이 선점의 소유자 표식. 해제·확정 시 **자기 선점만** 건드리게 한다.
    """

    qa_log_id: int
    claim_token: str
    answer_text: str | None
    input_tokens: int | None
    output_tokens: int | None
    rule_matched: bool
    user_id: int | None


@dataclass(frozen=True)
class HistoryPlan:
    """대화 이어가기 준비 결과 (#149 · 검수 P0-2·P0-3).

    - ``turns``: 프롬프트에 넣을 이전 대화. 비어 있으면 기존 단일 질문과 동일한 조립.
    - ``search_query``: RAG 검색에 쓸 완성된 질의. None 이면 이번 질문 원문을 쓴다.
    - ``usage``: 판단 단계(LLM 1회)의 토큰·비용. 호출하지 않았으면 None.
    - ``clarify``: True 면 검색·답변 생성을 하지 말고 되묻기 문구만 돌려준다.
    - ``state``: 이번 요청의 이전 대화 상태(none/verified/rejected — 재수정 P0-3).
      로그·진단용. 분기 자체는 호출부가 ``clarify``·``turns`` 로 한다.
    """

    turns: list[ConversationTurn] = field(default_factory=list)
    search_query: str | None = None
    usage: TokenUsage | None = None
    clarify: bool = False
    state: HistoryState = HistoryState.NONE


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


def _merge_usage(base: TokenUsage, extra: TokenUsage | None) -> TokenUsage:
    """토큰/비용 합산 — 질문 1건에 LLM 호출이 2회(판단 + 답변) 일어날 때 쓴다."""
    if extra is None:
        return base
    return TokenUsage(
        input_tokens=base.input_tokens + extra.input_tokens,
        output_tokens=base.output_tokens + extra.output_tokens,
        total_tokens=base.total_tokens + extra.total_tokens,
        cost_usd=base.cost_usd + extra.cost_usd,
    )


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

    async def _prepare_history(
        self,
        *,
        question_text: str,
        normalized: str,
        history_turns: list[ConversationTurn] | None,
        redis_runtime: Redis | None,
        syn_dict: dict | None,
        has_known_topic: bool = False,
        history_state: HistoryState = HistoryState.NONE,
    ) -> "HistoryPlan":
        """대화 이어가기 준비 — 쓸 이전 대화 / 검색용 질문 / 판단 비용 / 되묻기 여부.

        게시판 #149 의 ②·③ 과 결정 ①(A안 되묻기)을 담당한다.

        ``history_turns`` 는 **라우터가 서버 로그에서 읽어 검증을 끝낸** 턴 목록이다
        (검수 P0-2 — 브라우저가 보낸 과거 답변 문자열은 더 이상 받지 않는다).

        반환값 해석:
          - 이전 대화가 비어 있으면 기존 단일 질문 동작과 **완전히 동일**하다
            (검색 질문 None = 원문 사용, 판단 단계 호출 0회, 되묻기 없음).
          - ``related=False`` 로 판정되면 이전 대화를 버리고 새 질문만으로 처리한다.
            단, 그 질문이 혼자서는 뜻이 통하지 않는 조각이면 ``clarify=True`` 가 되고
            호출부는 RAG 검색을 하지 않고 되묻기 문구만 돌려준다 (결정 ① A안).

        **설정 조회 실패(Redis 장애) 처리 — 검수 P0-3.**
        예전에는 "이전 대화 없음 + 되묻기 없음" 으로 떨어져, 조각 질문이 그대로 검색됐다
        (안전장치가 꺼진 상태). 지금은 이전 대화가 딸려 온 요청이면 **안전 우선**으로
        조각 질문을 되묻고, 완결된 독립 질문만 단일 질문 경로로 보낸다.

        **검증 결과가 0개인 경우 — 재수정 P0-3.**
        ``history_state`` 가 ``REJECTED`` 면 요청은 분명히 맥락을 가리켰는데 그 id 가
        **전부 거부**된 상태다(다른 사용자 id / 삭제된 id / 오류·미전달·되묻기 턴).
        예전에는 이것이 "맥락 없는 첫 질문" 과 구분되지 않아 조각 질문이 그대로 RAG 로
        갔다. 지금은 조각 질문이면 RAG 를 호출하지 않고 되묻고, 완결된 독립 질문만
        기존 단일 질문 경로로 보낸다.
        """
        if not history_turns and history_state is not HistoryState.REJECTED:
            # 진짜로 맥락을 요청하지 않은 첫 질문 → 기존 동작 그대로.
            return HistoryPlan()

        if history_state is HistoryState.REJECTED:
            # 맥락 id 를 보냈는데 전부 거부됐다. 쓸 턴이 없으므로 판단 단계도 못 돌린다.
            return await self._plan_for_rejected_history(
                question_text=question_text,
                redis_runtime=redis_runtime,
                has_known_topic=has_known_topic,
            )

        if redis_runtime is None:
            # 설정을 읽을 수단이 없다(단위 테스트 등) → 기존 단일 질문 동작.
            return HistoryPlan()

        try:
            cfg = await runtime_config_service.get_chat_history_config(redis_runtime)
        except Exception as exc:
            # P0-3 — 판단 단계를 돌릴 설정을 못 읽었다. 맥락을 붙일 수도, 판정할 수도 없다.
            clarify = needs_clarification(
                question_text, has_known_topic=has_known_topic
            )
            logger.warning(
                "qa.history.config_failed", error=str(exc), clarify=clarify
            )
            return HistoryPlan(clarify=clarify)

        if not cfg.enabled:
            # 킬 스위치 — 예전 1문1답으로 완전 복귀(되묻기도 하지 않는다).
            return HistoryPlan()

        turns = await asyncio.to_thread(
            prepare_history,
            history_turns,
            max_turns=cfg.max_turns,
            max_tokens=cfg.max_tokens,
        )
        if not turns:
            return HistoryPlan()

        from api.src.rag_integration.query_rewriter import rewrite_query

        decision = await rewrite_query(
            question_text, turns, model_name=cfg.rewriter_model
        )
        if not decision.related:
            # 다른 주제(또는 판정 실패) → 이전 대화를 빼고 새 질문만으로 처리.
            # 단, 조각 질문이면 틀린 기준을 안내하는 대신 되묻는다 (결정 ① A안).
            clarify = needs_clarification(question_text, has_known_topic=has_known_topic)
            if clarify:
                logger.info(
                    "qa.history.clarify_asked",
                    turns=len(turns),
                    has_known_topic=has_known_topic,
                    question_len=len(question_text),
                )
            return HistoryPlan(usage=decision.usage, clarify=clarify)

        # 이어지는 질문 → 완성된 검색질의에도 본 질문과 동일한 전처리를 적용해
        # 검색 품질(스케일링 룰·동의어 치환)을 맞춘다.
        from rag.run_qa import apply_scaling_rules, normalize_query

        try:
            scaled = await asyncio.to_thread(apply_scaling_rules, decision.search_query)
            search_for_rag = await asyncio.to_thread(normalize_query, scaled, syn_dict)
        except Exception as exc:
            logger.warning("qa.history.normalize_failed", error=str(exc))
            search_for_rag = decision.search_query

        return HistoryPlan(
            turns=turns,
            search_query=(search_for_rag or normalized),
            usage=decision.usage,
        )

    async def _plan_for_rejected_history(
        self,
        *,
        question_text: str,
        redis_runtime: Redis | None,
        has_known_topic: bool,
    ) -> "HistoryPlan":
        """이전 대화를 요청했으나 **전부 거부**된 경우의 계획 (재수정 P0-3).

        거부 사유는 소유권 불일치(다른 사용자 id), 존재하지 않는 id(삭제), 오류·미전달
        턴, 되묻기 턴 등이다. 공통점은 **이어갈 맥락이 없다는 것을 서버가 안다**는 점이다.

        이 상태를 "첫 질문" 으로 취급하면 두 가지가 동시에 틀어진다.

        1. 조각 질문("몇 번까지 돼?")이 그대로 RAG 로 가 엉뚱한 항목의 기준이 나간다.
        2. 저장 답변 재생(#141)이 ``history_context_key IS NULL`` 후보에 걸려
           **다른 대화에서 만든 답변**을 자동 재생한다. (재생 차단은 라우터가 담당)

        그래서 여기서는 조각 질문이면 되묻고, 완결된 독립 질문이면 기존 단일 질문
        경로로 보낸다. 판단 단계(LLM)는 호출하지 않는다 — 넣을 맥락이 없으므로 비용 0.
        """
        # 킬 스위치가 꺼져 있으면 대화 이어가기 자체가 비활성이다 → 예전 1문1답 동작.
        # 설정을 못 읽으면 **안전 우선**으로 되묻기 판정을 그대로 적용한다.
        enabled = True
        if redis_runtime is not None:
            try:
                cfg = await runtime_config_service.get_chat_history_config(
                    redis_runtime
                )
                enabled = bool(cfg.enabled)
            except Exception as exc:
                # 설정을 못 읽었다 → 안전 우선으로 되묻기 판정을 그대로 적용한다.
                logger.warning(
                    "qa.history.config_failed",
                    error=str(exc),
                    state=HistoryState.REJECTED.value,
                )
        if not enabled:
            return HistoryPlan(state=HistoryState.REJECTED)

        clarify = needs_clarification(question_text, has_known_topic=has_known_topic)
        logger.info(
            "qa.history.all_ids_rejected",
            clarify=clarify,
            has_known_topic=has_known_topic,
            question_len=len(question_text),
        )
        if clarify:
            logger.info(
                "qa.history.clarify_asked",
                turns=0,
                state=HistoryState.REJECTED.value,
                has_known_topic=has_known_topic,
                question_len=len(question_text),
            )
        return HistoryPlan(clarify=clarify, state=HistoryState.REJECTED)

    async def stream(
        self,
        db: AsyncSession,
        user: User,
        question_text: str,
        *,
        redis_quota: Redis | None = None,
        redis_runtime: Redis | None = None,
        preflight_result: PreflightResult | None = None,
        device_type: str | None = None,
        history_turns: list[ConversationTurn] | None = None,
        history_context_key: str | None = None,
        history_state: HistoryState = HistoryState.NONE,
    ) -> AsyncIterator[dict]:
        """SSE 이벤트를 yield하는 async generator.

        yield 형식: {"event": "token", "data": json.dumps(...)} — sse-starlette 호환.
        AC-4: 요청 시작 시 즉시 INSERT → 종료 시 UPDATE 패턴.
        AC-7: 클라이언트 단절은 GeneratorExit 또는 asyncio.CancelledError로 전달될 수 있다.
            asyncio.CancelledError는 BaseException 하위라 except Exception에 잡히지 않으므로
            GeneratorExit과 함께 명시적으로 처리해 status='aborted' commit을 보장한다.
        AC-8: question_text/answer_text/delta는 절대 logger에 전달 금지 (PII).

        대화 이어가기(게시판 #149 · 검수 P0-2):
        ``history_turns`` 는 **라우터가 ``qa_logs`` 에서 읽어 소유권·완료·전달 여부까지
        검증한** 턴 목록(오래된 것 → 최신 순)이다. 브라우저가 보낸 과거 답변 문자열은
        받지 않는다. 서버는 여기서 다시 설정값(최근 N턴 / 토큰 상한)으로 잘라 쓴다.
        ``history_context_key`` 는 그 턴 목록의 지문으로, 이 답변 행에 기록해 두면
        전송 실패 답변 재생(#141)이 **같은 맥락일 때만** 일어난다(검수 P0-1).
        ``history_state`` 는 "맥락 요청 안 함(NONE) / 검증된 맥락 있음(VERIFIED) /
        id 를 보냈지만 전부 거부됨(REJECTED)" 세 상태를 구분한다(재수정 P0-3).
        RAG 경로에서만 사용하며, 룰/치주낭 결정형 경로는 기존대로 단일 질문으로 처리한다.
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
            # 검수 P0-1 — 이 답변을 만들 때 쓴 "검증된 이전 대화" 지문. 전송 실패 후
            # 재생은 같은 맥락일 때만 허용된다. 맥락 없는 요청이면 NULL.
            #
            # 3차 검수 P1-2 — INSERT 시점에는 **비워 둔다.** 요청이 맥락을 가리켰다고
            # 해서 그 맥락을 실제로 쓰는 것은 아니다(킬 스위치 OFF / 설정 조회 실패 /
            # 주제 전환으로 맥락 폐기 / 룰·치주낭 경로). 예전에는 요청 기준으로 찍어서,
            # "맥락 없이 만든 답변" 에 지문이 남고 나중에 그 답변이 "같은 맥락" 으로
            # 재생됐다. 아래 RAG 분기에서 **실제로 쓴 맥락이 있을 때만** 채운다.
            history_context_key=None,
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

        # 검수 P1-2·P1-4 — 끊김 저장 콜백이 참조할 값들. 콜백은 아래에서 정의되지만
        # 실제 호출은 RAG 분기 이후(판단 단계가 끝난 뒤)라, 리스트에 담아 넘긴다.
        #   rewrite_usage_holder: 판단 단계(#149 ③) 토큰·비용 → 끊겨도 합산해 저장
        #   audit_query_holder:   실제로 검색에 쓴 질의 → 관리자 감사 기록(normalized_query)
        rewrite_usage_holder: list[TokenUsage | None] = []
        audit_query_holder: list[str] = []
        #   context_key_holder: 이 답변이 **실제로 쓴** 이전 대화 지문 → 끊겨도 같은 값 저장
        #                       (3차 검수 P1-2 — 요청 기준 지문을 찍으면 안 된다)
        context_key_holder: list[str | None] = []

        def _persist_full_from_thread(
            full_text: str,
            usage_bg: TokenUsage,
            docs_bg: list[dict] | None = None,
            prompt_bg: str | None = None,
        ) -> None:
            try:
                latency_bg = int((time.perf_counter() - t0) * 1000)
                # #142 — 끊김 저장 경로도 정상 경로와 동일한 관리자 감사정보를 남긴다.
                # P1-2 — 판단 단계 비용이 빠지면 끊긴 질문만 과금이 축소 집계된다(예산 차단 왜곡).
                usage_total = _merge_usage(
                    usage_bg, rewrite_usage_holder[0] if rewrite_usage_holder else None
                )
                audit_query = audit_query_holder[0] if audit_query_holder else normalized
                asyncio.run_coroutine_threadsafe(
                    self._guarded_persist_full(
                        qa_log_id,
                        full_text,
                        usage_total,
                        latency_bg,
                        retrieved_docs=docs_bg or [],
                        prompt_text=prompt_bg,
                        normalized_query=audit_query,
                        # 3차 검수 P1-2 — 이 답변이 **실제로 쓴** 맥락 지문.
                        # 아직 결정되지 않았으면(판단 단계 전에 끊긴 경우) None.
                        history_context_key=(
                            context_key_holder[0] if context_key_holder else None
                        ),
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
            # 되묻기(#149 결정 ①)는 RAG 경로에서만 판정한다. 룰·치주낭 경로는 항상 False.
            needs_clarify = False
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
                #
                # 대화 이어가기(#149) — 이 경로에서만 적용한다.
                #   1) 설정(최근 N턴 / 토큰 상한)으로 **서버가 검증한** 이전 대화를 자른다.
                #   2) 이전 대화가 있으면 "이어지는 질문인가 + 검색용 질문" 을 1회 판정한다.
                #   3) 이어지지 않으면(또는 판정 실패) 이전 대화를 버리고 단일 질문으로 간다.
                #   4) 이어지지 않는데다 혼자서는 뜻이 통하지 않는 조각 질문이면
                #      (예: 앞 대화가 스케일링인데 "하얀색?") 틀린 기준을 안내하는 대신
                #      되묻는다 — 결정 ① A안(2026-11-02 사용자 선택).
                plan = await self._prepare_history(
                    question_text=question_text,
                    normalized=normalized,
                    history_turns=history_turns,
                    redis_runtime=redis_runtime,
                    syn_dict=syn_dict,
                    has_known_topic=bool(procedures),
                    # 재수정 P0-3 — "맥락 요청 안 함" 과 "요청했지만 전부 거부됨" 을
                    # 구분해 넘긴다. 후자는 조각 질문이면 되묻는다.
                    history_state=history_state,
                )
                search_for_rag = plan.search_query
                rewrite_usage = plan.usage
                needs_clarify = plan.clarify
                # 검수 P1-2 — 끊김 저장 콜백도 판단 단계 비용을 합산하도록 넘긴다.
                rewrite_usage_holder.append(rewrite_usage)
                # 검수 P1-4 — 관리자 감사에는 **실제로 검색에 쓴 질의**를 남긴다.
                audit_query_holder.append(search_for_rag or normalized)
                # 3차 검수 P1-2 — 지문은 **실제로 맥락을 쓴 경우에만** 남긴다.
                # 비교 기준은 "요청이 가리킨 검증된 턴 목록"(라우터가 만든 값)을 그대로
                # 쓴다 — 재생 선점은 요청 시점에 그 값으로 판단하므로 기준이 같아야 한다.
                # 다른 점은 "쓰지 않았으면 NULL" 뿐이다.
                used_context_key = history_context_key if plan.turns else None
                log.history_context_key = used_context_key
                context_key_holder.append(used_context_key)
                history_block = build_history_block(plan.turns)
                if needs_clarify:
                    # 되묻기 경로 — RAG 검색도, 답변 생성도 하지 않는다.
                    # 비용은 판단 단계 1회뿐이고 그 값은 아래에서 그대로 합산된다.
                    await catch_up_to_deadline(preflight_result, user_id=user.id)
                    logger.info(
                        "qa.stream.first_token_ms",
                        qa_log_id=qa_log_id,
                        user_id=user.id,
                        path="clarify",
                        ttft_ms=int((time.perf_counter() - t0) * 1000),
                    )
                    first_token_logged = True
                    yield {
                        "event": "token",
                        "data": json.dumps({"delta": CLARIFY_MESSAGE}),
                    }
                    accumulated = CLARIFY_MESSAGE
                    usage = _merge_usage(TokenUsage(0, 0, 0, 0.0), rewrite_usage)
                else:
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
                        normalized,
                        _on_complete,
                        on_thread_complete=_persist_full_from_thread,
                        search_query=search_for_rag,
                        history_block=history_block,
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
                    # 판단 단계(#149 ③)도 OpenAI 호출이다 — 질문 1건의 비용에 합산해야
                    # 월 예산 집계·kill-switch 가 실제 지출과 어긋나지 않는다.
                    usage = _merge_usage(usage, rewrite_usage)
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
            # 검수 P1-4 — 대화 이어가기에서 검색에 쓴 질의는 원문 정규화와 다르다.
            # 관리자 화면이 "실제로 무엇을 검색했는지" 를 보도록 실제 검색 질의를 남긴다.
            log.normalized_query = (
                audit_query_holder[0] if audit_query_holder else normalized
            )
            # 검수 P1-7 — 되묻기 응답은 종류를 구조적으로 표시한다. 이전 대화를 서버
            # 로그에서 다시 읽을 때 이 값으로 제외한다(문구 문자열 비교 금지).
            if needs_clarify:
                log.answer_kind = ANSWER_KIND_CLARIFICATION
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
                path=(
                    "periodontal"
                    if use_periodontal
                    else "rule"
                    if use_rule
                    else "clarify"
                    if needs_clarify
                    else "rag"
                ),
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
                # #142 후속 진단 — 클라이언트가 연결을 끊은 정확한 경과(ms)·기기·첫토큰 전송 여부.
                # 장문답변 '15초 컷' 가설 검증용: 이 값이 매번 ~15000ms 로 수렴하면 고정 타임아웃.
                elapsed_ms=latency_ms,
                device_type=device_type,
                first_token_sent=first_token_logged,
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
            # 2026-09-30 — 문구에서 "질문이 복잡해" 를 뺐다. 그날 장애는 질문 탓이 아니라
            # 바깥(LLM) 응답이 느려진 것이었는데, 사용자에게는 **당신 질문이 문제**라고
            # 읽혀 같은 질문을 계속 고쳐 던지게 만들었다(한 사람이 3회 반복).
            yield {
                "event": "error",
                "data": json.dumps({
                    "code": "SLOW_QUESTION",
                    "message": (
                        "답변이 시작되지 않아 중단했어요. "
                        "일시적인 지연일 수 있으니 잠시 후 다시 시도해주세요."
                    ),
                }),
            }
            logger.warning(
                "qa.stream.first_token_timeout",
                qa_log_id=qa_log_id,
                user_id=user.id,
                latency_ms=latency_ms,
            )
            await self._notify_admin_on_failure_burst(qa_log_id)

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
            await self._notify_admin_on_failure_burst(qa_log_id)

    @staticmethod
    async def _notify_admin_on_failure_burst(qa_log_id: int) -> None:
        """실패가 몰리면 관리자에게 알림톡 (2026-09-30 장애 후속).

        2026-09-30 에는 25분간 8건이 빈 화면으로 끝났는데 **고객이 알려 줄 때까지
        몰랐다.** 경고 로그만으로는 아무도 보지 않는다.

        본문은 `qa_alert_service` 참고 — 10분에 3건 이상일 때만, 구간당 1통.
        여기서 예외가 새어 나가면 이미 실패한 요청을 두 번 죽이는 꼴이라 전부 삼킨다.
        """
        try:
            from api.src.services.qa_alert_service import maybe_alert_admin_qa_failures

            await maybe_alert_admin_qa_failures(qa_log_id=qa_log_id)
        except Exception:
            logger.error("qa.failure_burst.hook_failed", qa_log_id=qa_log_id, exc_info=True)

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
        history_context_key: str | None = None,
    ) -> None:
        """#141 — 백그라운드 스레드가 완성한 답변을, 아직 확정 안 된(in_progress) 행에
        한해 저장한다. 유저 연결이 끊겨 정상 경로 UPDATE 가 못 돈 경우의 안전망.
        delivered=False 로 남겨 재시도 재생 대상이 되게 한다. 정상 전송된 행
        (status!='in_progress')은 WHERE 조건에서 걸러져 건드리지 않는다(멱등).

        3차 검수 P1-2 — ``history_context_key``(이 답변이 실제로 쓴 이전 대화 지문)도
        함께 저장한다. 이 값이 빠지면 **맥락을 반영해 만든 답변**이 지문 없이 남아,
        나중에 맥락 없는 첫 질문에 자동 재생된다(= 검수 P0-1 결함 재발).
        """
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
                        "normalized_query=:nq, history_context_key=:ck "
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
                        "ck": history_context_key,
                        "id": qa_log_id,
                    },
                )
                await s.commit()
            if res.rowcount:
                # rowcount>0 = 정상 경로가 아직 확정 못 한 행을 백그라운드가 저장 = 끊김 케이스.
                # #142 후속 — 생성 스레드가 답을 끝낸 경과(ms). aborted 로그의 elapsed_ms(클라
                # 단절 시각)와 대조하면 "클라가 몇 초에 끊었고, 서버는 몇 초에 끝냈는지" 분리 관찰.
                logger.info(
                    "qa.stream.persisted_undelivered",
                    qa_log_id=qa_log_id,
                    thread_finish_ms=latency_ms,
                )
        except Exception as exc:  # pragma: no cover - 백그라운드 저장 실패는 로그만
            logger.warning(
                "qa.stream.guarded_persist_failed", qa_log_id=qa_log_id, error=str(exc)
            )

    async def claim_replayable(
        self,
        db: AsyncSession,
        *,
        user: User,
        question_text: str,
        history_context_key: str | None = None,
        explicit_retry: bool = False,
        history_state: HistoryState = HistoryState.NONE,
    ) -> "ReplayClaim | None":
        """#141 — 최근(3분 이내) 같은 질문에 대해 '완성됐지만 전송 못 한'(delivered=False)
        답변의 **재생 권한을 원자적으로 선점**한다. 선점에 성공한 요청만 재생한다.

        **검수 P0-1 — 대화 맥락까지 같아야 재생한다.**

        예전에는 사용자·질문 문자열만 봤다. 그래서 스케일링 대화에서 만들어진
        "몇 번까지 돼?" 답변이, 몇 분 뒤 임플란트 대화의 똑같은 "몇 번까지 돼?" 질문에
        그대로 재생됐다(= 다른 항목의 청구 기준을 안내).

        **재수정 P1-1 — 조회와 전달 표시를 분리하지 않는다.**

        예전 구조는 ``find_replayable``(평범한 SELECT) → ``stream_saved``(delivered UPDATE)
        였다. 두 단계 사이에 틈이 있어 거의 동시에 들어온 요청 2개가 같은 행을 함께
        재생했다(재생은 횟수 차감이 없으므로 공짜로 복제된다). 지금은 조건부
        ``UPDATE ... RETURNING`` 으로 ``replay_claimed_at``(재생 권한 선점 시각)을
        NULL → now() 로 바꾸는 데 성공한 **단 하나**의 요청만 재생 권한을 얻는다.
        ``delivered=true``(사용자 전달 완료)는 **재생을 끝까지 마친 뒤**에만 확정한다.

        지금 규칙:
          - 맥락 없는 요청(첫 질문 등, ``history_state=NONE``)은 **기존과 동일하게**
            자동 재생한다. ``history_context_key IS NULL`` 인 답변만 후보가 된다.
          - 이전 대화가 딸린 요청(``VERIFIED``)은 ``history_context_key`` 가 **정확히
            같고**, 사용자가 명시적으로 재시도를 눌렀을 때(``explicit_retry=True``)만
            재생한다. 맥락이 다르면 재생하지 않고 정상 생성 경로로 간다.
          - **``REJECTED``(맥락 id 를 보냈지만 전부 거부됨)는 재생하지 않는다** —
            재수정 P0-3. 이 상태의 맥락 키는 NULL 이라, 허용하면 "맥락 없는 첫 질문"
            후보에 걸려 **다른 대화에서 만든 답변**이 자동 재생된다.
          - 맥락 키는 **서버가 검증한 턴 id** 로만 만든다(브라우저 문자열 금지 — P0-2).
        """
        from sqlalchemy import or_, select, update

        if history_state is HistoryState.REJECTED:
            # 이어갈 맥락이 없다는 것을 서버가 아는 상태. 첫 질문으로 취급하면 안 된다.
            logger.info(
                "qa.replay.skipped_rejected_history", user_id=user.id
            )
            return None

        if history_context_key is not None and not explicit_retry:
            # 맥락이 있는 질문은 사용자가 "다시 시도" 를 누른 경우에만 재생한다.
            return None

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=3)
        # 리스 만료 기준 — 연결이 끊겨 선점 해제가 못 돌아간 행도 이 시간이 지나면
        # 다시 가져갈 수 있다(행이 영구히 잠기지 않게).
        lease_cutoff = now - timedelta(seconds=REPLAY_CLAIM_LEASE_SECONDS)
        claim_token = uuid4().hex

        def _claimable():
            """선점 가능 조건 — 선점이 없거나 리스가 만료된 행."""
            return or_(
                QALog.replay_claimed_at.is_(None),
                QALog.replay_claimed_at < lease_cutoff,
            )

        candidate = (
            select(QALog.id)
            .where(
                QALog.user_id == user.id,
                QALog.question_text == question_text,
                QALog.status == "completed",
                QALog.delivered.is_(False),
                QALog.created_at >= cutoff,
                # 3차 검수 P2 — 되묻기 등 특수 응답은 재생 후보가 될 수 없다.
                # 지금은 되묻기 행이 (completed, delivered=False) 가 되지 않아 도달
                # 불가지만, 되묻기 경로에 백그라운드 저장이 추가되는 순간 되묻기 문구가
                # 재생된다. 가드를 미리 둔다(load_verified_turns 와 같은 기준).
                QALog.answer_kind.is_(None),
                (
                    QALog.history_context_key.is_(None)
                    if history_context_key is None
                    else QALog.history_context_key == history_context_key
                ),
                _claimable(),
            )
            .order_by(QALog.created_at.desc())
            .limit(1)
            .scalar_subquery()
        )

        # 조건부 UPDATE ... RETURNING — 동시 요청 중 **하나만** rowcount 1 이 된다.
        # (PostgreSQL READ COMMITTED: 두 번째 UPDATE 는 행 락에서 기다린 뒤 WHERE 를
        #  다시 평가하고, 그때는 replay_claimed_at 이 채워져 있어 0행이 된다.)
        stmt = (
            update(QALog)
            .where(
                QALog.id == candidate,
                QALog.delivered.is_(False),
                _claimable(),
            )
            .values(replay_claimed_at=now, replay_claim_token=claim_token)
            .returning(
                QALog.id,
                QALog.answer_text,
                QALog.input_tokens,
                QALog.output_tokens,
                QALog.rule_matched,
                QALog.user_id,
            )
            .execution_options(synchronize_session=False)
        )
        # 3차 검수 P2 — 재생은 "있으면 좋은" 최적화다. 선점 쿼리·커밋이 일시 실패하면
        # 예외를 올려 **질문 전체를 500 으로 끝내는** 대신, 재생을 포기하고 정상 생성
        # 경로로 내려보낸다(사용자는 답변을 받는다).
        try:
            row = (await db.execute(stmt)).first()
            await db.commit()
        except Exception as exc:
            logger.warning(
                "qa.replay.claim_failed", user_id=user.id, error=str(exc)
            )
            await _rollback_quietly(db, reason="replay_claim_failed")
            return None
        if row is None:
            return None

        logger.info(
            "qa.replay.claimed", qa_log_id=int(row.id), user_id=user.id
        )
        return ReplayClaim(
            qa_log_id=int(row.id),
            claim_token=claim_token,
            answer_text=row.answer_text,
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
            rule_matched=bool(row.rule_matched),
            user_id=row.user_id,
        )

    @staticmethod
    async def _release_replay_claim(db: AsyncSession, claim: "ReplayClaim") -> None:
        """재생이 끝까지 못 간 경우 선점을 **즉시** 해제한다 (재수정 P1-1).

        ``replay_claim_token`` 까지 비교해 **자기 선점만** 푼다. 토큰을 안 보고 풀면,
        리스가 만료돼 다른 요청이 이미 가져간 선점을 지워 중복 재생을 허용하게 된다.
        해제가 실패해도 리스 만료(기본 30초)로 다시 가져갈 수 있으므로 로그만 남긴다.
        """
        from sqlalchemy import update

        try:
            await db.execute(
                update(QALog)
                .where(
                    QALog.id == claim.qa_log_id,
                    QALog.replay_claim_token == claim.claim_token,
                    QALog.delivered.is_(False),
                )
                .values(replay_claimed_at=None, replay_claim_token=None)
                .execution_options(synchronize_session=False)
            )
            await db.commit()
            logger.info("qa.replay.claim_released", qa_log_id=claim.qa_log_id)
        except Exception as exc:  # pragma: no cover - 해제 실패는 리스로 복구된다
            logger.warning(
                "qa.replay.claim_release_failed",
                qa_log_id=claim.qa_log_id,
                error=str(exc),
            )

    @staticmethod
    async def _confirm_replay_delivered(db: AsyncSession, claim: "ReplayClaim") -> None:
        """재생을 끝까지 마친 뒤에만 ``delivered=true`` 를 확정한다 (재수정 P1-1)."""
        from sqlalchemy import update

        await db.execute(
            update(QALog)
            .where(
                QALog.id == claim.qa_log_id,
                QALog.replay_claim_token == claim.claim_token,
            )
            .values(delivered=True)
            .execution_options(synchronize_session=False)
        )
        await db.commit()
        logger.info("qa.replay.delivered", qa_log_id=claim.qa_log_id)

    async def stream_saved(
        self, db: AsyncSession, *, claim: "ReplayClaim"
    ) -> AsyncIterator[dict]:
        """#141 — DB에 저장된 완성 답변을 그대로 재생(SSE)한다. OpenAI 호출·횟수 차감 없음.

        재수정 P1-1 — 재생 권한은 ``claim_replayable`` 이 이미 선점해 두었다.
        ``delivered=true`` 는 **재생을 끝까지 마친 뒤**에만 확정하고, 중간에 연결이
        끊기면 선점을 풀어 다음 재시도가 바로 다시 가져갈 수 있게 한다.
        """
        answer = claim.answer_text or ""
        logger.info(
            "qa.stream.replayed",
            qa_log_id=claim.qa_log_id,
            user_id=claim.user_id,
            chars=len(answer),
        )
        try:
            # 프론트 타자기 애니메이션이 살아있도록 저장 답변을 한 토큰으로 흘려보낸다.
            if answer:
                yield {"event": "token", "data": json.dumps({"delta": answer})}
            yield {
                "event": "done",
                "data": json.dumps({
                    "qa_log_id": claim.qa_log_id,
                    "total_tokens": (claim.input_tokens or 0)
                    + (claim.output_tokens or 0),
                    "cost_usd": 0.0,
                    "latency_ms": 0,
                    "rule_matched": bool(claim.rule_matched),
                    "replayed": True,
                }),
            }
        except (GeneratorExit, asyncio.CancelledError):
            # 재생 중 연결이 끊겼다 → 전달되지 않았으므로 delivered 를 세우지 않고
            # 선점을 풀어 즉시 재시도가 가능하게 한다.
            await self._release_replay_claim(db, claim)
            raise
        except Exception:
            # 끊김이 아닌 오류(직렬화 실패 등)로 재생이 중단된 경우도 전달 실패다.
            # 리스 만료(30초)로도 회수되지만, 즉시 재시도가 가능하도록 여기서도 푼다.
            await self._release_replay_claim(db, claim)
            raise
        # 끝까지 보냈다 → 이제 전달 완료로 확정한다.
        #
        # 확정이 실패해도 **사용자에게는 이미 전부 보냈다.** 여기서 예외를 올리면
        # SSE 응답 뒷정리만 지저분해지고 사용자에게 돌아가는 이득이 없다. 확정에
        # 실패하면 delivered 가 false 로 남아 같은 답변이 한 번 더 재생될 수 있는데,
        # 재생은 질문 횟수 차감도 과금도 없으므로 안전한 실패 방향이다.
        try:
            await self._confirm_replay_delivered(db, claim)
        except Exception as exc:  # pragma: no cover - 확정 실패는 로그만
            logger.warning(
                "qa.replay.deliver_confirm_failed",
                qa_log_id=claim.qa_log_id,
                error=str(exc),
            )
