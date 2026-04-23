"""감사 로그 미들웨어 골격 — Story 5.1에서 구체화 예정."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        # TODO: Story 5.1에서 감사 로그 기록 로직 추가
        return response
