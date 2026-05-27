"""Story 6.5 — Admin 이상 이벤트 라우터.

GET  /admin/anomaly         — 분류·상태·기간 필터 + 페이지네이션 (audit-skip)
PATCH /admin/anomaly/{id}   — status='reviewed' 전이 (audit_logs INSERT)

특징:
- require_admin 가드, denvia_admin_session 쿠키 전용.
- slowapi 60/min 관리자 user_id 키 — IP 폴백 (6.1 패턴 동일).
- 'actioned' 전이는 본 라우터에서 거부 (422) — 차단 endpoint(6.2 PATCH /admin/users/{id}) 경유 only.
"""

from __future__ import annotations

from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from redis.asyncio import Redis as AsyncRedis
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.deps.auth import require_admin, require_admin_page
from api.src.deps.redis import get_redis_rate_limit
from api.src.middleware.audit_actions import AUDIT_ANOMALY_REVIEW
from api.src.middleware.rate_limit import limiter
from api.src.models.base import get_session
from api.src.models.user import User
from api.src.schemas.admin.anomaly import (
    AnomalyDetailResponse,
    AnomalyListResponse,
    AnomalyMarkReviewedRequest,
    AnomalyMarkReviewedResponse,
    AnomalyMemoUpdateRequest,
)
from api.src.schemas.admin.watch import (
    WatchToggleResponse,
    WatchedAccountListResponse,
)
from api.src.services import anomaly_service, anomaly_watch_service
from api.src.utils.jwt import (
    JWTDecodeError,
    SessionExpired,
    decode_admin_session_jwt,
)

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/admin/anomaly",
    tags=["admin-anomaly"],
    dependencies=[Depends(require_admin_page("/admin/anomaly"))],
)


def _admin_user_id_key(request: Request) -> str:
    """레이트 리밋 키 — 6.1 패턴 동일."""
    cookie = request.cookies.get("denvia_admin_session")
    if not cookie:
        return get_remote_address(request)
    try:
        payload = decode_admin_session_jwt(cookie)
        return f"admin:{payload['sub']}"
    except (JWTDecodeError, SessionExpired, KeyError):
        return get_remote_address(request)


def _parse_csv(value: str | None, allowed: tuple[str, ...]) -> list[str] | None:
    """콤마 구분 문자열을 검증·파싱. 빈 값/None → None, 허용 enum 외 값 → 422."""
    if value is None or value == "":
        return None
    parsed = [v.strip() for v in value.split(",") if v.strip()]
    invalid = [v for v in parsed if v not in allowed]
    if invalid:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "ANOMALY_FILTER_INVALID_VALUE",
                "message": f"허용되지 않는 값: {', '.join(invalid)}",
            },
        )
    return parsed


@router.get("", response_model=AnomalyListResponse)
@limiter.limit("60/minute", key_func=_admin_user_id_key)
async def list_anomalies(
    request: Request,
    type_in: str | None = Query(None, description="콤마 구분 5종 enum"),
    status_in: str | None = Query(
        None, description="콤마 구분 3종 enum. 기본값 'new' 단독."
    ),
    target_user_id: int | None = Query(None),
    from_dt: datetime | None = Query(None, alias="from"),
    to_dt: datetime | None = Query(None, alias="to"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
    redis_rl: AsyncRedis = Depends(get_redis_rate_limit),
) -> AnomalyListResponse:
    """epics AC-4 — 이상 이벤트 list. GET 전용 → audit_logs INSERT 없음."""
    types = _parse_csv(type_in, anomaly_service.ANOMALY_TYPES)
    statuses = _parse_csv(status_in, anomaly_service.ANOMALY_STATUSES)

    result = await anomaly_service.list_anomaly_events(
        db,
        type_in=types,
        status_in=statuses,
        target_user_id=target_user_id,
        from_dt=from_dt,
        to_dt=to_dt,
        page=page,
        per_page=per_page,
        redis_rl=redis_rl,
    )

    logger.info(
        "admin.anomaly.list",
        actor_user_id=admin.id,
        type_in=types,
        status_in=statuses,
        target_user_id=target_user_id,
        from_dt=from_dt.isoformat() if from_dt else None,
        to_dt=to_dt.isoformat() if to_dt else None,
        page=page,
        per_page=per_page,
        total=result["total"],
    )
    return AnomalyListResponse(**result)


@router.get("/watched", response_model=WatchedAccountListResponse)
@limiter.limit("60/minute", key_func=_admin_user_id_key)
async def list_watched_accounts(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> WatchedAccountListResponse:
    """주의 계정 리스트 — 별 모양 버튼으로 등록된 계정. 최근 등록 순.

    /{anomaly_id} 동적 경로보다 먼저 등록돼야 라우팅이 정상 동작한다.
    """
    result = await anomaly_watch_service.list_watched(
        db, page=page, per_page=per_page
    )
    logger.info(
        "admin.anomaly.watched.list",
        actor_user_id=admin.id,
        page=page,
        per_page=per_page,
        total=result["total"],
    )
    return WatchedAccountListResponse(**result)


@router.post("/{anomaly_id}/watch", response_model=WatchToggleResponse)
@limiter.limit("60/minute", key_func=_admin_user_id_key)
async def add_watch(
    request: Request,
    anomaly_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> WatchToggleResponse:
    """이상 이벤트의 target_user 를 주의 계정으로 등록 (별 활성화)."""
    result = await anomaly_watch_service.add_watch_from_anomaly(
        db, anomaly_id=anomaly_id, actor_admin_id=admin.id
    )
    await db.commit()
    request.state.audit_skip = True
    logger.info(
        "admin.anomaly.watch.added",
        actor_user_id=admin.id,
        anomaly_id=anomaly_id,
        target_user_id=result["user_id"],
    )
    return WatchToggleResponse(**result)


@router.delete("/users/{user_id}/watch", response_model=WatchToggleResponse)
@limiter.limit("60/minute", key_func=_admin_user_id_key)
async def remove_watch(
    request: Request,
    user_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> WatchToggleResponse:
    """주의 계정 해제 — 멱등."""
    result = await anomaly_watch_service.remove_watch(db, user_id=user_id)
    await db.commit()
    request.state.audit_skip = True
    logger.info(
        "admin.anomaly.watch.removed",
        actor_user_id=admin.id,
        target_user_id=user_id,
    )
    return WatchToggleResponse(**result)


@router.get("/{anomaly_id}", response_model=AnomalyDetailResponse)
@limiter.limit("60/minute", key_func=_admin_user_id_key)
async def get_anomaly(
    request: Request,
    anomaly_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
    redis_rl: AsyncRedis = Depends(get_redis_rate_limit),
) -> AnomalyDetailResponse:
    """상세 드로어용 — 단건 + 누적 통계 + 대상 사용자 현황.

    login_brute_force 의 Redis 자동 락아웃 상태도 함께 포함한다(redis_rl).
    """
    detail = await anomaly_service.get_anomaly_detail(
        db, anomaly_id=anomaly_id, redis_rl=redis_rl
    )
    logger.info(
        "admin.anomaly.detail",
        actor_user_id=admin.id,
        anomaly_id=anomaly_id,
    )
    return AnomalyDetailResponse(**detail)


@router.patch("/{anomaly_id}/memo", response_model=AnomalyDetailResponse)
@limiter.limit("60/minute", key_func=_admin_user_id_key)
async def patch_anomaly_memo(
    request: Request,
    anomaly_id: int,
    payload: AnomalyMemoUpdateRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> AnomalyDetailResponse:
    """관리자 메모 저장. 빈 문자열은 NULL 로 정규화.

    audit_logs INSERT 는 별도 액션을 만들지 않고 본 라우터에서 skip — 메모는 운영 흔적.
    """
    event = await anomaly_service.update_anomaly_memo(
        db, anomaly_id=anomaly_id, memo=payload.memo
    )
    await db.commit()
    request.state.audit_skip = True

    detail = await anomaly_service.get_anomaly_detail(db, anomaly_id=event.id)
    # memo 갱신 응답에는 Redis 락아웃 상태를 재조회하지 않는다 — 메모 저장은 락아웃과 무관하고,
    # 드로어 측에서 닫고 다시 열 때 GET /{id} 가 최신 상태를 가져온다.
    logger.info(
        "admin.anomaly.memo_updated",
        actor_user_id=admin.id,
        anomaly_id=anomaly_id,
        memo_len=len(payload.memo or ""),
    )
    return AnomalyDetailResponse(**detail)


@router.patch("/{anomaly_id}", response_model=AnomalyMarkReviewedResponse)
@limiter.limit("60/minute", key_func=_admin_user_id_key)
async def patch_anomaly(
    request: Request,
    anomaly_id: int,
    payload: AnomalyMarkReviewedRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> AnomalyMarkReviewedResponse:
    """epics AC-6 — status='reviewed' 전이.

    'actioned' 직접 변경 금지 — 차단 endpoint(6.2 PATCH /admin/users/{id}) 경유 only.
    """
    if payload.status != "reviewed":
        raise HTTPException(
            status_code=422,
            detail={
                "code": "ANOMALY_STATUS_INVALID",
                "message": "status는 'reviewed'만 지정 가능합니다.",
            },
        )

    transition = await anomaly_service.mark_anomaly_reviewed(
        db, anomaly_id=anomaly_id, actor_admin_id=admin.id
    )
    serialized = transition["event"]

    if transition["transitioned"]:
        request.state.audit_action = AUDIT_ANOMALY_REVIEW
        request.state.audit_target_type = "anomaly_event"
        request.state.audit_target_id = anomaly_id
        request.state.audit_diff = {
            "before": {"status": "new"},
            "after": {"status": "reviewed"},
        }
    else:
        # 멱등 PATCH (이미 reviewed) — 미들웨어가 audit_logs INSERT를 건너뛰도록 표식.
        request.state.audit_skip = True

    await db.commit()

    logger.info(
        "admin.anomaly.reviewed",
        actor_user_id=admin.id,
        anomaly_id=anomaly_id,
        transitioned=transition["transitioned"],
    )
    return AnomalyMarkReviewedResponse(**serialized)


__all__ = ["router"]
