"""X-Trace-Id 미들웨어 — 요청·응답 양방향으로 trace_id를 주입하고
structlog contextvars에 바인딩하여 로그 호출 시 자동 첨부한다.
"""

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from ulid import ULID


class TraceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        trace_id = request.headers.get("X-Trace-Id") or str(ULID())
        request.state.trace_id = trace_id

        # structlog contextvars에 바인딩 — 이후 모든 logger.info 호출에 trace_id 자동 첨부
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(trace_id=trace_id)

        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()

        response.headers["X-Trace-Id"] = trace_id
        return response
