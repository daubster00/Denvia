"""Admin kill-switch 라우터 — Story 9.2 (A-502).

GET   /api/v1/admin/killswitch/status              auto/manual 모드 통합 상태 — 60/min
POST  /api/v1/admin/killswitch/manual/activate     수동 비상 정지 발동 — 5/min
POST  /api/v1/admin/killswitch/manual/deactivate   수동 비상 정지 해제 — 5/min

가드:
- require_admin (denvia_admin_session 쿠키 전용).
- 발동·해제는 audit 액션 자동 기록 (AuditMiddleware + @audit_action 데코레이터).
- 발동 시 admin:events publish — 프론트 SSE 구독자가 실시간 갱신.
- 해제 시 Celery enqueue — billing.extend_subscriptions_for_killswitch_duration.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.deps.auth import require_admin
from api.src.deps.redis import get_redis_client
from api.src.middleware.audit_actions import (
    AUDIT_KILLSWITCH_MANUAL_TOTAL_ACTIVATE,
    AUDIT_KILLSWITCH_MANUAL_TOTAL_DEACTIVATE,
)
from api.src.middleware.rate_limit import limiter
from api.src.models.base import get_session
from api.src.models.killswitch_state import MODE_MANUAL_TOTAL, KillswitchState
from api.src.models.user import User
from api.src.schemas.admin.killswitch import (
    AutoFreeOnlyStatus,
    KillswitchStatusResponse,
    ManualActivateRequest,
    ManualActivateResponse,
    ManualDeactivateResponse,
    ManualRequeueExtensionResponse,
    ManualTotalStatus,
)
from api.src.services.killswitch_service import (
    KillSwitchAlreadyActive,
    KillSwitchNotActive,
    activate_manual,
    deactivate_manual,
    get_status,
    publish_killswitch_event,
)
from api.src.utils.jwt import (
    JWTDecodeError,
    SessionExpired,
    decode_admin_session_jwt,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin/killswitch", tags=["admin-killswitch"])


def _admin_user_id_key(request: Request) -> str:
    cookie = request.cookies.get("denvia_admin_session")
    if not cookie:
        return get_remote_address(request)
    try:
        payload = decode_admin_session_jwt(cookie)
        return f"admin:{payload['sub']}"
    except (JWTDecodeError, SessionExpired, KeyError, Exception):
        return get_remote_address(request)


@router.get("/status", response_model=KillswitchStatusResponse)
@limiter.limit("60/minute", key_func=_admin_user_id_key)
async def get_killswitch_status(
    request: Request,
    response: Response,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> KillswitchStatusResponse:
    """auto/manual 두 모드 통합 상태 조회 — Cache-Control: no-store."""
    payload = await get_status(db)
    await db.commit()
    response.headers["Cache-Control"] = "no-store"
    logger.info(
        "admin.killswitch.status.viewed",
        actor_user_id=admin.id,
        trace_id=str(getattr(request.state, "trace_id", "")),
    )
    return KillswitchStatusResponse(
        auto_free_only=AutoFreeOnlyStatus(**payload["auto_free_only"]),
        manual_total=ManualTotalStatus(**payload["manual_total"]),
    )


@router.post("/manual/activate", response_model=ManualActivateResponse)
@limiter.limit("5/minute", key_func=_admin_user_id_key)
async def activate_manual_killswitch(
    request: Request,
    body: ManualActivateRequest,
    background_tasks: BackgroundTasks,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> ManualActivateResponse:
    """수동 전체 정지 발동 — 사유 4~500자 필수.

    트랜잭션 단일 commit:
      1) killswitch_states INSERT (manual_total)
      2) audit_logs (AuditMiddleware 자동 — request.state.audit_action 설정)
    응답 후 fire-and-forget: Redis admin:events publish.
    """
    try:
        row = await activate_manual(db, admin_id=admin.id, reason=body.reason)
    except KillSwitchAlreadyActive:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "KILLSWITCH_ALREADY_ACTIVE",
                "message": "이미 수동 비상 정지가 활성화되어 있습니다.",
            },
        )

    # audit 액션 + diff (사유 본문 그대로) — AuditMiddleware가 응답 후 INSERT.
    request.state.audit_action = AUDIT_KILLSWITCH_MANUAL_TOTAL_ACTIVATE
    request.state.audit_target_type = "killswitch_state"
    request.state.audit_target_id = row.id
    request.state.audit_diff = {"reason": body.reason}

    await db.commit()

    activated_iso = row.activated_at
    if activated_iso.tzinfo is None:
        activated_iso = activated_iso.replace(tzinfo=timezone.utc)

    # admin email 마스킹은 publish 페이로드에 포함 — 프론트 KillSwitchPanel 즉시 표시.
    from api.src.services.killswitch_service import _mask_email

    background_tasks.add_task(
        publish_killswitch_event,
        get_redis_client(),
        {
            "type": "killswitch_status",
            "mode": MODE_MANUAL_TOTAL,
            "active": True,
            "activated_at": activated_iso.isoformat(),
            "activated_by_admin_email": _mask_email(admin.email),
        },
    )
    logger.warning(
        "killswitch.manual_total.activate",
        actor_user_id=admin.id,
        killswitch_state_id=row.id,
        reason_length=len(body.reason),
    )
    return ManualActivateResponse(
        id=row.id,
        activated_at=activated_iso,
        mode=MODE_MANUAL_TOTAL,
        active=True,
    )


@router.post("/manual/deactivate", response_model=ManualDeactivateResponse)
@limiter.limit("5/minute", key_func=_admin_user_id_key)
async def deactivate_manual_killswitch(
    request: Request,
    background_tasks: BackgroundTasks,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> ManualDeactivateResponse:
    """수동 전체 정지 해제 — 정지 기간만큼 활성 유료 구독자 만료일 자동 연장 enqueue."""
    try:
        result = await deactivate_manual(db, admin_id=admin.id)
    except KillSwitchNotActive:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "KILLSWITCH_NOT_ACTIVE",
                "message": "활성화된 수동 비상 정지가 없습니다.",
            },
        )

    request.state.audit_action = AUDIT_KILLSWITCH_MANUAL_TOTAL_DEACTIVATE
    request.state.audit_target_type = "killswitch_state"
    request.state.audit_target_id = result.killswitch_state_id
    request.state.audit_diff = {"duration_seconds": result.duration_seconds}

    await db.commit()

    # Celery enqueue — 구독 기간 자동 연장 + 알림톡.
    # broker 장애로 실패하면 503을 반환하고 killswitch_state_id를 응답에 포함한다.
    # 운영자는 POST /admin/killswitch/manual/requeue-extension/{id}로 재시도할 수 있다.
    from api.src.workers.celery_app import celery_app
    try:
        extension_task = celery_app.send_task(
            "billing.extend_subscriptions_for_killswitch_duration",
            args=[result.killswitch_state_id],
        )
        extension_task_id = extension_task.id
    except Exception as exc:
        logger.error(
            "killswitch.manual_total.deactivate.enqueue_failed",
            actor_user_id=admin.id,
            killswitch_state_id=result.killswitch_state_id,
            duration_seconds=result.duration_seconds,
            error=str(exc),
        )
        raise HTTPException(
            status_code=503,
            detail={
                "code": "EXTENSION_ENQUEUE_FAILED",
                "message": (
                    "kill-switch 해제는 완료됐으나 구독 연장 작업 enqueue에 실패했습니다. "
                    "POST /admin/killswitch/manual/requeue-extension/"
                    f"{result.killswitch_state_id} 로 재시도해주세요."
                ),
                "killswitch_state_id": result.killswitch_state_id,
            },
        )

    background_tasks.add_task(
        publish_killswitch_event,
        get_redis_client(),
        {
            "type": "killswitch_status",
            "mode": MODE_MANUAL_TOTAL,
            "active": False,
        },
    )
    logger.warning(
        "killswitch.manual_total.deactivate",
        actor_user_id=admin.id,
        killswitch_state_id=result.killswitch_state_id,
        duration_seconds=result.duration_seconds,
        extension_task_id=extension_task_id,
    )
    return ManualDeactivateResponse(
        id=result.killswitch_state_id,
        deactivated_at=result.deactivated_at,
        duration_seconds=result.duration_seconds,
        extension_task_id=extension_task_id,
    )


@router.post(
    "/manual/requeue-extension/{state_id}",
    response_model=ManualRequeueExtensionResponse,
)
@limiter.limit("5/minute", key_func=_admin_user_id_key)
async def requeue_extension(
    request: Request,
    state_id: int,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> ManualRequeueExtensionResponse:
    """deactivate 시 broker 장애로 enqueue 실패한 구독 연장 작업을 재시도한다.

    deactivated_at이 설정된 manual_total 상태에 대해서만 허용한다.
    extend_active_subscriptions 태스크 자체가 audit_log 기반 멱등성을 보장하므로
    중복 호출해도 구독 기간이 이중으로 늘어나지 않는다.
    """
    ks_result = await db.execute(
        select(KillswitchState).where(
            KillswitchState.id == state_id,
            KillswitchState.mode == MODE_MANUAL_TOTAL,
            KillswitchState.deactivated_at.is_not(None),
        )
    )
    ks = ks_result.scalar_one_or_none()
    if ks is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "KILLSWITCH_STATE_NOT_FOUND",
                "message": "해당 killswitch 상태가 없거나 아직 해제되지 않았습니다.",
            },
        )

    from api.src.workers.celery_app import celery_app
    try:
        extension_task = celery_app.send_task(
            "billing.extend_subscriptions_for_killswitch_duration",
            args=[state_id],
        )
    except Exception as exc:
        logger.error(
            "killswitch.requeue_extension.failed",
            actor_user_id=admin.id,
            killswitch_state_id=state_id,
            error=str(exc),
        )
        raise HTTPException(
            status_code=503,
            detail={
                "code": "ENQUEUE_FAILED",
                "message": "Celery 브로커 장애로 재enqueue에 실패했습니다. 잠시 후 다시 시도해주세요.",
                "killswitch_state_id": state_id,
            },
        )

    logger.info(
        "killswitch.requeue_extension.success",
        actor_user_id=admin.id,
        killswitch_state_id=state_id,
        extension_task_id=extension_task.id,
    )
    return ManualRequeueExtensionResponse(id=state_id, extension_task_id=extension_task.id)


__all__ = ["router"]
