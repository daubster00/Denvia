"""QA 라우터 — POST /api/v1/qa/echo (Story 2.1) + POST /api/v1/qa/stream (Story 2.2/2.3) + POST /api/v1/qa/feedback (Story 2.4)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from redis.asyncio import Redis as AsyncRedis
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from api.src.deps.auth import get_current_user
from api.src.deps.redis import get_redis_quota, get_redis_runtime
from api.src.models.base import get_session
from api.src.models.user import User
from api.src.schemas.qa import FeedbackCreateRequest, FeedbackResponse, QAEchoRequest, QAEchoResponse, QAStreamRequest
from api.src.services.killswitch_service import is_any_total_block_active, is_auto_free_only_active
from api.src.services.qa_feedback_service import upsert_feedback
from api.src.services.qa_service import QAService

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
    # Story 5.2: 수동 비상 정지 (전체 차단) — admin/pro 관계없이 모든 사용자 차단
    if await is_any_total_block_active(db):
        raise HTTPException(
            status_code=503,
            detail={
                "code": "SERVICE_KILL_SWITCH",
                "message": "비상 정지가 활성화되어 일시적으로 질의가 중단되었습니다.",
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

    await _qa_service.preflight(
        user=user,
        redis_quota=redis_quota,
        redis_runtime=redis_runtime,
    )
    return EventSourceResponse(
        _qa_service.stream(db=db, user=user, question_text=body.question_text),
        media_type="text/event-stream",
    )


@router.post("/feedback", response_model=FeedbackResponse, status_code=200)
async def qa_feedback(
    body: FeedbackCreateRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> FeedbackResponse:
    return await upsert_feedback(db=db, user=user, qa_log_id=body.qa_log_id, rating=body.rating)
