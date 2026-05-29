"""Admin OpenAI 워밍업 라우터.

GET   /api/v1/admin/openai-warmup/status   현재 루프 상태(가동 여부·마지막 핑·통계)
POST  /api/v1/admin/openai-warmup/start    90초 주기 핑 루프 시작
POST  /api/v1/admin/openai-warmup/stop     핑 루프 정지

접근 제어:
- 마스터는 항상 통과 (require_admin_page 내부에서 master 단락 평가).
- operator/sub_operator/커스텀 등급은 등급별 페이지 권한 매트릭스에서
  /admin/feature/openai-warmup 행이 ON 일 때만 통과.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api.src.deps.auth import require_admin_page
from api.src.middleware.rate_limit import limiter
from api.src.models.user import User
from api.src.services import openai_warmup_service

logger = structlog.get_logger(__name__)


# 매트릭스의 1차 라우트 — admin_grade_permission_service.ADMIN_PAGE_ROUTES 와 동일 키.
WARMUP_FEATURE_ROUTE = "/admin/feature/openai-warmup"


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
    dependencies=[Depends(require_admin_page(WARMUP_FEATURE_ROUTE))],
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
    admin: Annotated[User, Depends(require_admin_page(WARMUP_FEATURE_ROUTE))],
) -> WarmupStatusResponse:
    return _to_response(openai_warmup_service.status())


@router.post("/start", response_model=WarmupStatusResponse)
@limiter.limit("10/minute")
async def start_warmup(
    request: Request,
    admin: Annotated[User, Depends(require_admin_page(WARMUP_FEATURE_ROUTE))],
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
    # persist=True — 관리자 명시 토글이므로 Redis 에 ON 키 저장. 재시작 후 자동 복원의 기준.
    s = await openai_warmup_service.start(persist=True)
    logger.info(
        "admin.openai_warmup.start",
        actor_user_id=admin.id,
        running=s.running,
        model=s.model,
    )
    return _to_response(s)


@router.post("/stop", response_model=WarmupStatusResponse)
@limiter.limit("10/minute")
async def stop_warmup(
    request: Request,
    admin: Annotated[User, Depends(require_admin_page(WARMUP_FEATURE_ROUTE))],
) -> WarmupStatusResponse:
    # persist=True — 관리자 명시 OFF 토글이므로 Redis 키 삭제. 이후 재시작에서도 OFF 유지.
    s = await openai_warmup_service.stop(persist=True)
    logger.info("admin.openai_warmup.stop", actor_user_id=admin.id, running=s.running)
    return _to_response(s)


__all__ = ["router"]
