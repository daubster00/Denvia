"""X-Trace-Id 미들웨어 — 요청·응답 양방향으로 UUID v7 trace_id를 주입한다."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from ulid import ULID


class TraceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # 클라이언트가 전달한 trace_id가 없으면 새로 생성
        trace_id = request.headers.get("X-Trace-Id") or str(ULID())
        request.state.trace_id = trace_id

        response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        return response
