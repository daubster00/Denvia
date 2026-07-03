"""Denvia FastAPI 애플리케이션 진입점."""

import sentry_sdk
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from api.src.middleware.audit import AuditMiddleware
from api.src.middleware.session_refresh import SessionRefreshMiddleware
from api.src.middleware.trace import TraceMiddleware
from api.src.middleware.rate_limit import limiter, ratelimit_handler, SlowAPIMiddleware, RateLimitExceeded
from api.src.routers import health
from api.src.routers import me
from api.src.routers import auth
from api.src.routers import qa
from api.src.routers import events as client_events
from api.src.routers.admin import accounts as admin_accounts
from api.src.routers.admin import auth as admin_auth
from api.src.routers.admin import grade_permissions as admin_grade_permissions
from api.src.routers.admin import grades as admin_grades
from api.src.routers.admin import events as admin_events
from api.src.routers.admin import audit_logs as admin_audit_logs
from api.src.routers.admin import prompts as admin_prompts
from api.src.routers.admin import rag as admin_rag
from api.src.routers.admin import synonyms as admin_synonyms
from api.src.routers.admin import budget as admin_budget
from api.src.routers.admin import analytics as admin_analytics
from api.src.routers.admin import users as admin_users
from api.src.routers.admin import anomaly as admin_anomaly
from api.src.routers.admin import support as admin_support
from api.src.routers.admin import content as admin_content
from api.src.routers.admin import inbox_trash as admin_inbox_trash
from api.src.routers.admin import finance as admin_finance
from api.src.routers.admin import payments as admin_payments
from api.src.routers.admin import killswitch as admin_killswitch
from api.src.routers.admin import seo as admin_seo
from api.src.routers.admin import board as admin_board
from api.src.routers.admin import qa_review as admin_qa_review
from api.src.routers.admin import openai_warmup as admin_openai_warmup
from api.src.routers.admin import alimtalk as admin_alimtalk
from api.src.routers import billing as billing_router
from api.src.routers import support as support_router
from api.src.settings import settings


# PII 스크러빙 프로세서 — 이메일·휴대폰·비밀번호를 로그에서 마스킹
def _scrub_pii(event, hint):
    """Sentry 이벤트에서 PII 필드를 제거한다."""
    for key in ("email", "phone", "password", "password_hash"):
        if key in event.get("extra", {}):
            event["extra"][key] = "[REDACTED]"
    return event


# Sentry 초기화
if settings.sentry_dsn_api:
    sentry_sdk.init(
        dsn=settings.sentry_dsn_api,
        environment=settings.sentry_environment,
        integrations=[StarletteIntegration(), FastApiIntegration()],
        before_send=_scrub_pii,
        send_default_pii=False,
    )

# structlog 설정
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ]
)

_log = structlog.get_logger()

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from api.scripts.seed_admin import seed_admin
        await seed_admin()
    except Exception:
        _log.exception("lifespan.seed_admin.failed")

    # RAG 인덱스 사전 로드 — 첫 사용자 질문에서 발생하던 수 초 지연 제거.
    # 실패해도 부팅은 진행(인덱스 없는 CI/일부 환경 대비) → 첫 질문 시 lazy init으로 자연 복구.
    try:
        import time as _time
        from api.src.rag_integration import query_runner

        _t0 = _time.perf_counter()
        await query_runner.ensure_initialized()
        _log.info(
            "lifespan.rag_preload.completed",
            elapsed_ms=int((_time.perf_counter() - _t0) * 1000),
        )
    except Exception:
        _log.exception("lifespan.rag_preload.failed")

    # OpenAI 워밍업 자동 복원 — Redis(runtime:openai_warmup_enabled) 가 1 이면 부팅 직후 재가동.
    # 이전 in-memory only 시절: 컨테이너 재시작/재배포마다 토글이 silently OFF → 관리자는 ON 으로
    # 인지한 채 cold path 를 맞았다. 2026-05-29 부터 영속화 + 자동 복원으로 해결.
    try:
        from api.src.services import openai_warmup_service

        if await openai_warmup_service.is_persisted_enabled():
            await openai_warmup_service.start(persist=False)
            _log.info("lifespan.openai_warmup.auto_resumed")
    except Exception:
        _log.exception("lifespan.openai_warmup.auto_resume_failed")

    yield

    # OpenAI 워밍업 루프 정리 — 종료 시 task 만 cancel, Redis 영속화 상태는 유지(다음 부팅에 복원).
    try:
        from api.src.services import openai_warmup_service

        await openai_warmup_service.stop(persist=False)
    except Exception:
        _log.exception("lifespan.openai_warmup.stop_failed")


app = FastAPI(title="Denvia API", version="0.1.0", lifespan=lifespan)

# slowapi Limiter 주입
app.state.limiter = limiter

# 미들웨어 등록 (바깥쪽부터 순서: cors → rate_limit → audit → session_refresh → trace)
# session_refresh는 응답 직전에 세션 쿠키를 다시 set 하므로 trace보다 바깥에 둠.
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(AuditMiddleware)
app.add_middleware(SessionRefreshMiddleware)
app.add_middleware(TraceMiddleware)
# CORS — 프론트 origin만 허용, credentials:include 필요 (JWT 쿠키)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.oauth_web_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Trace-Id", "Content-Disposition", "X-Truncated"],
)


@app.exception_handler(RateLimitExceeded)
async def _ratelimit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return await ratelimit_handler(request, exc)


@app.exception_handler(HTTPException)
async def _http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """HTTPException의 detail을 Denvia 표준 에러 포맷으로 변환한다.
    FastAPI 기본 {"detail": ...} 포맷 사용 금지 (architecture.md §416).
    Story 2.3: details 필드 지원 추가 (quota 초과 등 추가 정보 전달).

    AUTH_SESSION_SUPERSEDED 응답에는 죽은 쿠키 만료 헤더(denvia_session, denvia_csrf)를
    동봉한다. httponly 쿠키는 JS 가 못 지우므로, 서버가 만료시키지 않으면 클라이언트가
    같은 쿠키로 계속 요청을 보내 무한 401 → /?login=superseded 리다이렉트 루프가 발생한다.
    """
    trace_id = getattr(request.state, "trace_id", None)
    detail = exc.detail

    if isinstance(detail, dict):
        code = detail.get("code", "UNKNOWN_ERROR")
        message = detail.get("message", str(exc.detail))
        extras = {k: v for k, v in detail.items() if k not in ("code", "message")}
    else:
        code = "UNKNOWN_ERROR"
        message = str(detail) if detail else "알 수 없는 오류가 발생했습니다."
        extras = {}

    body: dict = {"code": code, "message": message, "trace_id": trace_id}
    if extras:
        body["details"] = extras

    response = JSONResponse(
        status_code=exc.status_code,
        content=body,
        headers=getattr(exc, "headers", None),
    )

    if code == "AUTH_SESSION_SUPERSEDED":
        secure = settings.environment.lower() in {"production", "staging"}
        response.set_cookie(
            key="denvia_session",
            value="",
            httponly=True,
            secure=secure,
            samesite="lax",
            path="/",
            max_age=0,
        )
        response.set_cookie(
            key="denvia_csrf",
            value="",
            httponly=False,
            secure=secure,
            samesite="lax",
            path="/",
            max_age=0,
        )

    return response


# 라우터 등록
app.include_router(health.router)
app.include_router(me.router)
app.include_router(auth.router)
app.include_router(qa.router)
app.include_router(client_events.router)
app.include_router(admin_auth.router, prefix="/api/v1")
app.include_router(admin_accounts.router, prefix="/api/v1")
app.include_router(admin_grade_permissions.router, prefix="/api/v1")
app.include_router(admin_grades.router, prefix="/api/v1")
app.include_router(admin_events.router, prefix="/api/v1")
app.include_router(admin_audit_logs.router, prefix="/api/v1")
app.include_router(admin_rag.router, prefix="/api/v1")
app.include_router(admin_prompts.router, prefix="/api/v1")
app.include_router(admin_synonyms.router, prefix="/api/v1")
app.include_router(admin_budget.router, prefix="/api/v1")
app.include_router(admin_analytics.router, prefix="/api/v1")
app.include_router(admin_users.router, prefix="/api/v1")
app.include_router(admin_anomaly.router, prefix="/api/v1")
app.include_router(admin_support.router, prefix="/api/v1")
app.include_router(admin_content.router, prefix="/api/v1")
app.include_router(admin_inbox_trash.router, prefix="/api/v1")
app.include_router(admin_finance.router, prefix="/api/v1")
app.include_router(admin_payments.router, prefix="/api/v1")
app.include_router(admin_killswitch.router, prefix="/api/v1")
app.include_router(admin_seo.router, prefix="/api/v1")
app.include_router(admin_board.router, prefix="/api/v1")
app.include_router(admin_qa_review.router, prefix="/api/v1")
app.include_router(admin_openai_warmup.router, prefix="/api/v1")
app.include_router(admin_alimtalk.router, prefix="/api/v1")
app.include_router(billing_router.router, prefix="/api/v1")
app.include_router(support_router.router)

# 정적 자산 — 팝업 이미지 (Story 7.2 v2). 디렉터리는 첫 업로드 시 자동 생성됨.
from api.src.services.popup_service import POPUP_IMAGE_DIR  # noqa: E402

POPUP_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
app.mount(
    "/static/popup-images",
    StaticFiles(directory=str(POPUP_IMAGE_DIR)),
    name="popup-images",
)

# 정적 자산 — SEO 설정 자산(파비콘/OG 이미지). 첫 업로드 시 자동 생성됨.
from api.src.services.seo_service import SEO_ASSET_DIR  # noqa: E402

SEO_ASSET_DIR.mkdir(parents=True, exist_ok=True)
app.mount(
    "/static/seo-assets",
    StaticFiles(directory=str(SEO_ASSET_DIR)),
    name="seo-assets",
)

# 정적 자산 — 1:1 문의 첨부 이미지 (0030). 첫 업로드 시 자동 생성됨.
from api.src.services.support_service import INQUIRY_IMAGE_DIR  # noqa: E402

INQUIRY_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
app.mount(
    "/static/inquiry-images",
    StaticFiles(directory=str(INQUIRY_IMAGE_DIR)),
    name="inquiry-images",
)

# 정적 자산 — CS 답변 본문 에디터 업로드 이미지. 첫 업로드 시 자동 생성됨.
from api.src.services.admin_support_service import SUPPORT_REPLY_IMAGE_DIR  # noqa: E402

SUPPORT_REPLY_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
app.mount(
    "/static/support-reply-images",
    StaticFiles(directory=str(SUPPORT_REPLY_IMAGE_DIR)),
    name="support-reply-images",
)

# 정적 자산 — 관리자 수정요청 게시판 본문 이미지 (0040). 첫 업로드 시 자동 생성됨.
from api.src.services.admin_board_service import BOARD_IMAGE_DIR  # noqa: E402

BOARD_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
app.mount(
    "/static/admin-board-images",
    StaticFiles(directory=str(BOARD_IMAGE_DIR)),
    name="admin-board-images",
)

# 정적 자산 — 관리자 수정요청 게시판 첨부 파일 (0064). 첫 업로드 시 자동 생성됨.
from api.src.services.admin_board_service import BOARD_ATTACHMENT_DIR  # noqa: E402

BOARD_ATTACHMENT_DIR.mkdir(parents=True, exist_ok=True)
app.mount(
    "/static/admin-board-attachments",
    StaticFiles(directory=str(BOARD_ATTACHMENT_DIR)),
    name="admin-board-attachments",
)
