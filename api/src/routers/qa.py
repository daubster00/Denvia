"""QA 라우터 — POST /api/v1/qa/echo (Story 2.1) + POST /api/v1/qa/stream (Story 2.2)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from api.src.deps.auth import get_current_user
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
) -> EventSourceResponse:
    """유료/무료 공통 SSE Q&A 스트림.

    Story 2.2: 유료 경로(즉시 스트리밍).
    Story 2.3: 무료 경로(quota 검증 + 의도적 지연)는 본 메서드 진입 전에 추가됨.
    """
    return EventSourceResponse(
        _qa_service.stream(db=db, user=user, question_text=body.question_text),
        media_type="text/event-stream",
    )
