"""QA 라우터 — POST /api/v1/qa/echo (Story 2.1) + POST /api/v1/qa/stream (Story 2.2/2.3)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from redis.asyncio import Redis as AsyncRedis
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from api.src.deps.auth import get_current_user
from api.src.deps.redis import get_redis_quota, get_redis_runtime
from api.src.models.base import get_session
from api.src.models.user import User
from api.src.schemas.qa import QAEchoRequest, QAEchoResponse, QAStreamRequest
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
    HTTPException(429) raise 시 글로벌 핸들러가 표준 에러 JSON으로 변환.
    echo 엔드포인트는 dev/CI 호환을 위해 preflight 미적용.
    """
    await _qa_service.preflight(
        user=user,
        redis_quota=redis_quota,
        redis_runtime=redis_runtime,
    )
    return EventSourceResponse(
        _qa_service.stream(db=db, user=user, question_text=body.question_text),
        media_type="text/event-stream",
    )
