"""Story 4.6 — `/api/v1/admin/alimtalk` 관리자 알림톡 관리 라우터.

6 엔드포인트:
- GET    /summary                — 템플릿별 통계 + 합계
- GET    /logs                   — 템플릿별 발송 로그 (cursor)
- GET    /test-recipient         — 테스트 수신 번호 마스킹 조회
- PUT    /test-recipient         — 테스트 수신 번호 등록/변경 (master/operator)
- DELETE /test-recipient         — 테스트 수신 번호 해제 (master/operator)
- POST   /test-send              — 임의 template 1건 테스트 발송

권한 (AC-9):
- GET/POST → master / operator / sub_operator (sub_operator 는 `/admin/alimtalk` 페이지
  매트릭스 통과 시만 — `require_admin_page` 데코레이터로 게이트).
- PUT/DELETE /test-recipient → master / operator 만 (sub_operator 는 조회만).

audit_logs INSERT 는 AuditMiddleware 가 처리한다.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as aioredis

from api.src.deps.auth import require_admin_grade, require_admin_page
from api.src.deps.redis import get_redis_rate_limit, get_redis_runtime
from api.src.integrations.messaging.adapters import get_adapter
from api.src.integrations.messaging.port import MessagingProvider
from api.src.middleware.audit_actions import (
    AUDIT_ALIMTALK_TEST_RECIPIENT_UPDATED,
    AUDIT_ALIMTALK_TEST_SEND_DISPATCHED,
    audit_action,
)
from api.src.models.base import get_session
from api.src.models.user import User
from api.src.schemas.admin.alimtalk import (
    AlimtalkLogListResponse,
    AlimtalkSummaryResponse,
    TestRecipientResponse,
    TestRecipientUpdateRequest,
    TestSendRequest,
    TestSendResponse,
)
from api.src.services import admin_alimtalk_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin/alimtalk", tags=["admin-alimtalk"])

_PAGE_ROUTE = "/admin/alimtalk"


def _get_messaging_provider() -> MessagingProvider:
    """MESSAGING_PROVIDER 환경변수에 맞는 어댑터 인스턴스를 반환."""
    return get_adapter()


# ── GET /summary ─────────────────────────────────────────────────────────


@router.get("/summary", response_model=AlimtalkSummaryResponse)
async def get_summary(
    admin: User = Depends(require_admin_page(_PAGE_ROUTE)),
    _grade_check: User = Depends(
        require_admin_grade("master", "operator", "sub_operator")
    ),
    db: AsyncSession = Depends(get_session),
) -> AlimtalkSummaryResponse:
    data = await admin_alimtalk_service.get_summary(db)
    return AlimtalkSummaryResponse(**data)


# ── GET /logs ────────────────────────────────────────────────────────────


@router.get("/logs", response_model=AlimtalkLogListResponse)
async def list_logs(
    template_code: str = Query(..., min_length=1, max_length=120),
    status: str = Query("all", pattern="^(sent|failed|all)$"),
    cursor: str | None = Query(None),
    limit: int = Query(100, ge=1, le=200),
    page: int | None = Query(None, ge=1),
    per_page: int | None = Query(None, ge=1, le=100),
    admin: User = Depends(require_admin_page(_PAGE_ROUTE)),
    _grade_check: User = Depends(
        require_admin_grade("master", "operator", "sub_operator")
    ),
    db: AsyncSession = Depends(get_session),
) -> AlimtalkLogListResponse:
    data = await admin_alimtalk_service.list_logs(
        db,
        template_code=template_code,
        status=status,
        cursor=cursor,
        limit=limit,
        page=page,
        per_page=per_page,
    )
    return AlimtalkLogListResponse(**data)


# ── GET /test-recipient ──────────────────────────────────────────────────


@router.get("/test-recipient", response_model=TestRecipientResponse)
async def get_test_recipient(
    admin: User = Depends(require_admin_page(_PAGE_ROUTE)),
    _grade_check: User = Depends(
        require_admin_grade("master", "operator", "sub_operator")
    ),
    redis_runtime: aioredis.Redis = Depends(get_redis_runtime),
) -> TestRecipientResponse:
    data = await admin_alimtalk_service.get_test_recipient(redis_runtime)
    return TestRecipientResponse(**data)


# ── PUT /test-recipient (master/operator only) ───────────────────────────


@router.put("/test-recipient", response_model=TestRecipientResponse)
@audit_action(AUDIT_ALIMTALK_TEST_RECIPIENT_UPDATED)
async def set_test_recipient(
    request: Request,
    body: TestRecipientUpdateRequest,
    admin: User = Depends(require_admin_grade("master", "operator")),
    redis_runtime: aioredis.Redis = Depends(get_redis_runtime),
) -> TestRecipientResponse:
    payload, audit_diff = await admin_alimtalk_service.set_test_recipient(
        redis_runtime, admin, body.phone
    )
    request.state.audit_target_type = "config"
    request.state.audit_target_id = None
    request.state.audit_diff = audit_diff
    return TestRecipientResponse(**payload)


# ── DELETE /test-recipient (master/operator only) ────────────────────────


@router.delete("/test-recipient", status_code=204)
@audit_action(AUDIT_ALIMTALK_TEST_RECIPIENT_UPDATED)
async def clear_test_recipient(
    request: Request,
    admin: User = Depends(require_admin_grade("master", "operator")),
    redis_runtime: aioredis.Redis = Depends(get_redis_runtime),
) -> None:
    audit_diff = await admin_alimtalk_service.clear_test_recipient(redis_runtime, admin)
    request.state.audit_target_type = "config"
    request.state.audit_target_id = None
    request.state.audit_diff = audit_diff
    return None


# ── POST /test-send ──────────────────────────────────────────────────────


@router.post("/test-send", response_model=TestSendResponse)
@audit_action(AUDIT_ALIMTALK_TEST_SEND_DISPATCHED)
async def dispatch_test_send(
    request: Request,
    body: TestSendRequest,
    admin: User = Depends(require_admin_page(_PAGE_ROUTE)),
    _grade_check: User = Depends(
        require_admin_grade("master", "operator", "sub_operator")
    ),
    db: AsyncSession = Depends(get_session),
    redis_runtime: aioredis.Redis = Depends(get_redis_runtime),
    redis_rl: aioredis.Redis = Depends(get_redis_rate_limit),
    provider: MessagingProvider = Depends(_get_messaging_provider),
) -> TestSendResponse:
    payload, audit_diff = await admin_alimtalk_service.dispatch_test_send(
        db,
        redis_runtime,
        redis_rl,
        provider,
        admin,
        body.template_code,
    )
    request.state.audit_target_type = "template"
    request.state.audit_target_id = None
    request.state.audit_diff = audit_diff
    return TestSendResponse(**payload)
