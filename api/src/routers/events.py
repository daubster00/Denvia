"""클라이언트 이벤트 로그 라우터 — Story 2.5.

POST /api/v1/events/client: 클라이언트 측 이벤트를 structlog에만 기록.
DB 쓰기 없음. 인증 필수(로그인 사용자 전용).
"""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends
from fastapi.responses import Response

from api.src.deps.auth import get_current_user
from api.src.models.user import User
from api.src.schemas.events import ClientEventRequest

router = APIRouter(prefix="/api/v1/events", tags=["events"])

logger = structlog.get_logger(__name__)


@router.post("/client", status_code=204, response_class=Response)
async def log_client_event(
    body: ClientEventRequest,
    user: Annotated[User, Depends(get_current_user)],
) -> None:
    """클라이언트 이벤트를 structlog에 기록한다. DB 쓰기 없음."""
    logger.info(
        body.event,
        user_id=user.id,
        client_trace_id=body.trace_id,
    )
