"""Admin OpenAI 워밍업 라우터 — 마스터 전용.

GET   /api/v1/admin/openai-warmup/status   현재 루프 상태(가동 여부·마지막 핑·통계)
POST  /api/v1/admin/openai-warmup/start    90초 주기 핑 루프 시작
POST  /api/v1/admin/openai-warmup/stop     핑 루프 정지

마스터 1인만 접근 — operator 도 보지 못한다 (운영상 비용 토글이므로 단일 책임자).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api.src.deps.auth import require_admin_grade
from api.src.middleware.rate_limit import limiter
from api.src.models.user import User
from api.src.services import openai_warmup_service

logger = structlog.get_logger(__name__)


class WarmupStatusResponse(BaseModel):
    running: bool
    started_at: datetime | None
    last_ping_at: datetime | None
    last_ping_latency_ms: int | None
    last_ping_ok: bool | None
    last_error: str | None
    total_pings: int
    total_failures: int
    interval_seconds: int
    model: str


router = APIRouter(
    prefix="/admin/openai-warmup",
    tags=["admin-openai-warmup"],
    dependencies=[Depends(require_admin_grade("master"))],
)


def _to_response(s: openai_warmup_service.WarmupStatus) -> WarmupStatusResponse:
    return WarmupStatusResponse(
        running=s.running,
        started_at=s.started_at,
        last_ping_at=s.last_ping_at,
        last_ping_latency_ms=s.last_ping_latency_ms,
        last_ping_ok=s.last_ping_ok,
        last_error=s.last_error,
        total_pings=s.total_pings,
        total_failures=s.total_failures,
        interval_seconds=s.interval_seconds,
        model=s.model,
    )


@router.get("/status", response_model=WarmupStatusResponse)
@limiter.limit("60/minute")
async def get_warmup_status(
    request: Request,
    admin: Annotated[User, Depends(require_admin_grade("master"))],
) -> WarmupStatusResponse:
    return _to_response(openai_warmup_service.status())


@router.post("/start", response_model=WarmupStatusResponse)
@limiter.limit("10/minute")
async def start_warmup(
    request: Request,
    admin: Annotated[User, Depends(require_admin_grade("master"))],
) -> WarmupStatusResponse:
    import os

    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "OPENAI_KEY_MISSING",
                "message": "OPENAI_API_KEY 환경변수가 설정되어 있지 않아 워밍업을 시작할 수 없습니다.",
            },
        )
    s = await openai_warmup_service.start()
    logger.info("admin.openai_warmup.start", actor_user_id=admin.id, running=s.running)
    return _to_response(s)


@router.post("/stop", response_model=WarmupStatusResponse)
@limiter.limit("10/minute")
async def stop_warmup(
    request: Request,
    admin: Annotated[User, Depends(require_admin_grade("master"))],
) -> WarmupStatusResponse:
    s = await openai_warmup_service.stop()
    logger.info("admin.openai_warmup.stop", actor_user_id=admin.id, running=s.running)
    return _to_response(s)


__all__ = ["router"]
