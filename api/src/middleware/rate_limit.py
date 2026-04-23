"""slowapi 레이트 리밋 미들웨어 래퍼 — 429 표준 에러 변환."""

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from fastapi import Request
from fastapi.responses import JSONResponse

from api.src.settings import settings, REDIS_DB_RATE_LIMIT

# 전역 Limiter 인스턴스 — main.py에서 app.state.limiter에 주입
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=f"{settings.redis_url}/{REDIS_DB_RATE_LIMIT}",
)


async def ratelimit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """429 응답을 Denvia 표준 에러 포맷으로 변환한다."""
    trace_id = getattr(request.state, "trace_id", None)
    return JSONResponse(
        status_code=429,
        content={
            "code": "RATE_LIMITED",
            "message": "잠시 후 다시 시도해주세요.",
            "trace_id": trace_id,
        },
        headers={"Retry-After": "60"},
    )


__all__ = ["limiter", "ratelimit_handler", "SlowAPIMiddleware", "RateLimitExceeded"]
