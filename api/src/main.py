"""Denvia FastAPI 애플리케이션 진입점."""

import sentry_sdk
import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from api.src.middleware.audit import AuditMiddleware
from api.src.middleware.trace import TraceMiddleware
from api.src.middleware.rate_limit import limiter, ratelimit_handler, SlowAPIMiddleware, RateLimitExceeded
from api.src.routers import health
from api.src.routers import me
from api.src.routers import auth
from api.src.routers import qa
from api.src.routers.admin import events as admin_events
from api.src.routers.admin import audit_logs as admin_audit_logs
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

app = FastAPI(title="Denvia API", version="0.1.0")

# slowapi Limiter 주입
app.state.limiter = limiter

# 미들웨어 등록 (바깥쪽부터 순서: cors → rate_limit → audit → trace)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(AuditMiddleware)
app.add_middleware(TraceMiddleware)
# CORS — 프론트 origin만 허용, credentials:include 필요 (JWT 쿠키)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.oauth_web_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Trace-Id"],
)


@app.exception_handler(RateLimitExceeded)
async def _ratelimit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return await ratelimit_handler(request, exc)


@app.exception_handler(HTTPException)
async def _http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """HTTPException의 detail을 Denvia 표준 에러 포맷으로 변환한다.
    FastAPI 기본 {"detail": ...} 포맷 사용 금지 (architecture.md §416).
    Story 2.3: details 필드 지원 추가 (quota 초과 등 추가 정보 전달).
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

    return JSONResponse(
        status_code=exc.status_code,
        content=body,
        headers=getattr(exc, "headers", None),
    )


# 라우터 등록
app.include_router(health.router)
app.include_router(me.router)
app.include_router(auth.router)
app.include_router(qa.router)
app.include_router(admin_events.router, prefix="/api/v1")
app.include_router(admin_audit_logs.router, prefix="/api/v1")
