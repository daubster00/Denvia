"""감사 로그 미들웨어 — Story 5.1 완성."""

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from api.src.models.base import async_session_factory
from api.src.models.audit_log import AuditLog
from api.src.utils.jwt import (
    JWTDecodeError,
    SessionExpired,
    decode_admin_session_jwt,
)

logger = structlog.get_logger()


class AuditMiddleware(BaseHTTPMiddleware):
    WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
    ADMIN_PREFIX = "/api/v1/admin/"

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        if (
            request.method in self.WRITE_METHODS
            and request.url.path.startswith(self.ADMIN_PREFIX)
            and response.status_code < 400  # 4xx 응답은 INSERT 안 함 (Story 8.1 보강)
        ):
            await self._record(request)

        return response

    async def _record(self, request: Request) -> None:
        try:
            # 멱등 PATCH 등으로 라우터가 명시적으로 audit 기록을 건너뛰도록 표식한 경우 skip.
            if getattr(request.state, "audit_skip", False):
                return
            # /api/v1/admin/* 경로의 actor는 관리자 세션 쿠키에서 추출
            cookie = request.cookies.get("denvia_admin_session")
            if not cookie:
                return
            try:
                payload = decode_admin_session_jwt(cookie)
                actor_user_id = int(payload["sub"])
            except (JWTDecodeError, SessionExpired, KeyError, ValueError):
                return  # 인증 오류는 라우터에서 이미 처리됨

            action = getattr(request.state, "audit_action", None) or (
                f"{request.method.lower()}.{request.url.path.rstrip('/').rsplit('/', 1)[-1]}"
            )
            trace_id = getattr(request.state, "trace_id", None)
            forwarded_for = request.headers.get("X-Forwarded-For")
            client_ip = (
                forwarded_for.split(",")[0].strip()
                if forwarded_for
                else (request.client.host if request.client else None)
            )
            ua = request.headers.get("User-Agent")
            # Story 8.1 보강: target_type / target_id / diff_json 읽기
            target_type = getattr(request.state, "audit_target_type", None)
            target_id = getattr(request.state, "audit_target_id", None)
            diff_json = getattr(request.state, "audit_diff", None)

            async with async_session_factory() as db:
                db.add(
                    AuditLog(
                        actor_user_id=actor_user_id,
                        action=action,
                        target_type=target_type,
                        target_id=target_id,
                        diff_json=diff_json,
                        ip=client_ip,
                        ua=ua,
                        trace_id=trace_id,
                    )
                )
                await db.commit()
        except Exception:
            logger.error("audit_log_insert_failed", exc_info=True)
