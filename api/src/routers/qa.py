"""QA 라우터 — POST /api/v1/qa/echo (Story 2.1) + POST /api/v1/qa/stream (Story 2.2/2.3) + POST /api/v1/qa/feedback (Story 2.4)."""

import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from redis.asyncio import Redis as AsyncRedis
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from api.src.deps.auth import get_current_user
from api.src.deps.redis import get_redis_quota, get_redis_runtime
from api.src.models.base import get_session
from api.src.models.user import User
from api.src.schemas.qa import FeedbackCreateRequest, FeedbackResponse, QAEchoRequest, QAEchoResponse, QAStreamRequest
from api.src.services import runtime_config_service
from api.src.services.chat_history_service import (
    HistoryState,
    history_context_key,
    load_verified_turns,
    resolve_history_state,
)
from api.src.services.killswitch_service import is_any_total_block_active, is_auto_free_only_active
from api.src.services.prompt_config_service import DEFAULT_QUESTION_CHARS
from api.src.services.qa_feedback_service import upsert_feedback
from api.src.services.qa_service import QAService
from api.src.utils.device import classify_device

router = APIRouter(prefix="/api/v1/qa", tags=["qa"])

_qa_service = QAService()


@router.post("/echo", response_model=QAEchoResponse, status_code=200)
async def qa_echo(
    body: QAEchoRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> QAEchoResponse:
    return await _qa_service.echo(db=db, user=user, question_text=body.question_text)


@router.post("/stream")
async def qa_stream(
    body: QAStreamRequest,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_session)],
    redis_quota: Annotated[AsyncRedis, Depends(get_redis_quota)],
    redis_runtime: Annotated[AsyncRedis, Depends(get_redis_runtime)],
) -> EventSourceResponse:
    """유료/무료 공통 SSE Q&A 스트림.

    Story 2.3: SSE 응답 시작 전 quota 검증 + 의도적 지연.
    Story 5.2: kill-switch 게이트 — manual_total(전체) / auto_free_only(무료만) 우선 검사.
    HTTPException(429/503) raise 시 글로벌 핸들러가 표준 에러 JSON으로 변환.
    echo 엔드포인트는 dev/CI 호환을 위해 preflight 미적용.

    AC-7 grep 결과: manual_total 분기가 Story 2.2/2.3에 미존재 → 본 스토리에서 신규 추가.
    """
    # Story 5.2 + Story 9.2: 수동 비상 정지 (전체 차단) — admin/pro 관계없이 모든 사용자 차단
    # 에러 코드는 spec(AC-7) 일관성을 위해 KILLSWITCH_ACTIVE 사용 (이전: SERVICE_KILL_SWITCH).
    if await is_any_total_block_active(db):
        raise HTTPException(
            status_code=503,
            detail={
                "code": "KILLSWITCH_ACTIVE",
                "message": "서비스가 일시 중단되었습니다. 재개 시 알림톡으로 안내드립니다.",
            },
        )

    # Story 5.2: 예산 소진 자동 차단 — 무료 사용자만
    if user.subscription_status == "free" and await is_auto_free_only_active(db):
        raise HTTPException(
            status_code=429,
            detail={
                "code": "BUDGET_HARD_CAP_REACHED",
                "message": "이번 달 예산 소진으로 무료 질의가 일시 중단되었습니다. "
                           "다음 달 재개 또는 Pro 구독을 고려해주세요",
            },
        )

    # #85 — 사용자 질문 입력 글자수 상한 검증. 상한은 관리자 페이지(모델 파라미터)에서
    # 설정하며 Redis runtime:max_question_chars 에 반영된다. 시스템 프롬프트는 별도
    # 변수(PROMPT_MODULES)라 question_text 에 포함되지 않으므로 자동으로 카운트에서 빠진다.
    max_q_chars_raw = await redis_runtime.get("runtime:max_question_chars")
    try:
        max_q_chars = (
            int(max_q_chars_raw)
            if max_q_chars_raw is not None
            else DEFAULT_QUESTION_CHARS
        )
    except (TypeError, ValueError):
        max_q_chars = DEFAULT_QUESTION_CHARS
    if len(body.question_text) > max_q_chars:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "QUESTION_TOO_LONG",
                "message": f"질문은 최대 {max_q_chars}자까지 입력할 수 있습니다.",
                "max_question_chars": max_q_chars,
                "received": len(body.question_text),
            },
        )

    # 대화 이어가기(#149 · 검수 P0-2) — 이전 대화는 **여기서 한 번** 서버 로그로 검증한다.
    # 브라우저는 qa_log_id 만 보내고, 질문·답변 본문은 서버가 자기 기록에서 읽는다.
    # 검증을 통과한 턴 id 로 맥락 지문(context key)을 만들어 아래 두 곳에 쓴다.
    #   1) 전송 실패 답변 재생이 **같은 맥락일 때만** 일어나게 (검수 P0-1)
    #   2) 이번 답변 행에 기록해 다음 재시도의 비교 기준이 되게
    #
    # 3차 검수 P1-2 — **킬 스위치를 먼저 읽는다.** 예전에는 킬 스위치와 무관하게 맥락을
    # 조회하고 지문을 만들어, "앞선 대화를 참고해서 답변하기" 를 꺼도
    #   ① 질문마다 최대 30행을 쓸데없이 조회했고
    #   ② 맥락을 **쓰지 않고** 만든 답변에 지문이 찍혀, 나중에 킬 스위치를 다시 켜고
    #      재시도하면 그 답변이 "같은 맥락" 으로 재생됐다(= P0-1 이 막으려던 실패 재발).
    # 꺼져 있으면 예전 1문1답으로 **완전히** 복귀한다.
    history_enabled = True
    try:
        history_enabled = (
            await runtime_config_service.get_chat_history_config(redis_runtime)
        ).enabled
    except Exception:
        # 설정을 못 읽었다 → 기능이 켜져 있다고 보고 진행한다. 그 경우의 안전 처리
        # (조각 질문 되묻기)는 qa_service._prepare_history 가 담당한다.
        history_enabled = True

    if history_enabled:
        history_turns, accepted_turn_ids = await load_verified_turns(
            db, user_id=user.id, turn_ids=body.history_turn_ids
        )
        context_key = history_context_key(accepted_turn_ids)
        # 재수정 P0-3 — "맥락 요청 안 함" 과 "요청했지만 전부 거부됨" 은 다른 상태다.
        # 후자(REJECTED)를 첫 질문처럼 다루면 ① 조각 질문이 그대로 검색되고
        # ② 저장 답변 재생이 다른 대화의 답변을 자동 재생한다.
        history_state = resolve_history_state(body.history_turn_ids, accepted_turn_ids)
    else:
        history_turns, accepted_turn_ids = [], []
        context_key = None
        history_state = HistoryState.NONE

    # #141 — 재시도 재생: 직전(3분 이내)에 완성됐지만 연결이 끊겨 전송 못 한 같은 질문
    # 답변이 있으면, OpenAI 재호출·질문 횟수 차감 없이 저장분을 그대로 재생한다.
    # 재수정 P1-1 — 조회·갱신을 분리하지 않고 **조건부 UPDATE ... RETURNING** 으로
    # 재생 권한을 선점한다. 동시 요청 2개가 같은 행을 재생하던 결함 차단.
    replay_claim = await _qa_service.claim_replayable(
        db,
        user=user,
        question_text=body.question_text,
        history_context_key=context_key,
        explicit_retry=body.retry,
        history_state=history_state,
    )
    if replay_claim is not None:
        return EventSourceResponse(
            _qa_service.stream_saved(db=db, claim=replay_claim),
            media_type="text/event-stream",
        )

    # 체감 지연 기준점 — 요청 진입 시점을 잡아 preflight 로 넘긴다.
    # "사용자 질문 보낸 시점 → 첫 토큰 도착" 총 경과가 관리자 딜레이값이 되도록 stream() 이 catch-up.
    t_received = time.perf_counter()
    ip = request.client.host if request.client else None
    # #141 — 접속 기기 기록(mobile/pc/unknown). 연결 끊김이 어느 기기에서 잦은지 진단용.
    device_type = classify_device(request.headers.get("user-agent"))
    preflight = await _qa_service.preflight(
        user=user,
        redis_quota=redis_quota,
        redis_runtime=redis_runtime,
        db=db,
        question_text=body.question_text,
        ip=ip,
        t_received=t_received,
    )
    return EventSourceResponse(
        _qa_service.stream(
            db=db,
            user=user,
            question_text=body.question_text,
            redis_quota=redis_quota,
            redis_runtime=redis_runtime,
            preflight_result=preflight,
            device_type=device_type,
            # 대화 이어가기(#149) — 서버가 검증한 턴만 넘긴다(설정값으로 다시 잘라 쓴다).
            history_turns=history_turns,
            history_context_key=context_key,
            history_state=history_state,
        ),
        media_type="text/event-stream",
    )


@router.post("/feedback", response_model=FeedbackResponse, status_code=200)
async def qa_feedback(
    body: FeedbackCreateRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> FeedbackResponse:
    return await upsert_feedback(db=db, user=user, qa_log_id=body.qa_log_id, rating=body.rating)
