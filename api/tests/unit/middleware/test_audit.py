"""AuditMiddleware 단위 테스트."""

import time
import pytest
import jwt as pyjwt
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch

from api.src.main import app
from api.src.settings import settings
from api.src.models.base import get_session


def _make_jwt(user_id: int = 99, role: str = "admin", sub_status: str = "free") -> str:
    if role == "admin":
        payload = {
            "sub": str(user_id),
            "aud": "denvia-admin",
            "exp": int(time.time()) + 3600,
        }
    else:
        payload = {
            "sub": str(user_id),
            "role": role,
            "sub_status": sub_status,
            "exp": int(time.time()) + 3600,
        }
    return pyjwt.encode(payload, settings.denvia_jwt_secret, algorithm=settings.denvia_jwt_algorithm)


def _make_admin_jwt(user_id: int = 99) -> str:
    """관리자 콘솔용 JWT (denvia_admin_session, aud=denvia-admin)."""
    payload = {
        "sub": str(user_id),
        "aud": "denvia-admin",
        "exp": int(time.time()) + 3600,
    }
    return pyjwt.encode(payload, settings.denvia_jwt_secret, algorithm=settings.denvia_jwt_algorithm)


def _admin_user_mock():
    user = MagicMock()
    user.id = 99
    user.email = "admin@denvia.local"
    user.role = "admin"
    user.subscription_status = "free"
    user.segment = None
    user.years_of_experience = None
    user.withdrawn_at = None
    user.must_reset_password = False
    user.current_session_id = None
    user.admin_grade = "master"
    return user


async def _mock_empty_db():
    """빈 결과를 반환하는 mock 세션 (audit-logs 조회용)."""
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = 0
    mock_result.scalars.return_value.all.return_value = []
    session = MagicMock()
    session.execute = AsyncMock(return_value=mock_result)
    yield session


class TestAuditMiddleware:
    async def test_POST_admin_경로_audit_log_INSERT(self):
        """POST /api/v1/admin/* 2xx 응답 → AuditLog INSERT 1건 시도."""
        import jwt as pyjwt
        from starlette.applications import Starlette
        from starlette.routing import Route
        from starlette.responses import JSONResponse
        from starlette.testclient import TestClient
        from api.src.middleware.audit import AuditMiddleware
        from api.src.settings import settings

        token = _make_admin_jwt()

        captured_logs: list = []

        def fake_session_factory():
            session = MagicMock()
            session.add = lambda obj: captured_logs.append(obj)
            session.commit = AsyncMock()

            class FakeCtx:
                async def __aenter__(self_inner):
                    return session

                async def __aexit__(self_inner, *a):
                    pass

            return FakeCtx()

        async def _dummy_view(req):
            return JSONResponse({"ok": True}, status_code=201)

        test_app = Starlette(
            routes=[Route("/api/v1/admin/dummy", _dummy_view, methods=["POST"])],
        )
        test_app.add_middleware(AuditMiddleware)

        with patch(
            "api.src.middleware.audit.async_session_factory",
            side_effect=fake_session_factory,
        ):
            client = TestClient(test_app, cookies={"denvia_admin_session": token})
            client.post("/api/v1/admin/dummy")

        from api.src.models.audit_log import AuditLog
        assert any(isinstance(obj, AuditLog) for obj in captured_logs)

    async def test_GET_admin_경로_audit_log_INSERT_없음(self):
        """GET /api/v1/admin/* → audit_logs INSERT 발생하지 않음."""
        token = _make_admin_jwt()
        user = _admin_user_mock()

        captured_logs: list = []

        def fake_session_factory():
            session = MagicMock()
            session.add = lambda obj: captured_logs.append(obj)
            session.commit = AsyncMock()

            class FakeCtx:
                async def __aenter__(self_inner):
                    return session

                async def __aexit__(self_inner, *a):
                    pass

            return FakeCtx()

        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)),
            patch(
                "api.src.middleware.audit.async_session_factory",
                side_effect=fake_session_factory,
            ),
        ):
            app.dependency_overrides[get_session] = _mock_empty_db
            try:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.get(
                        "/api/v1/admin/audit-logs",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.pop(get_session, None)

        from api.src.models.audit_log import AuditLog
        assert not any(isinstance(obj, AuditLog) for obj in captured_logs)

    async def test_DB_오류시_요청_정상_응답(self):
        """AuditMiddleware DB 오류 → 요청 응답은 500이 아님."""
        token = _make_admin_jwt()
        user = _admin_user_mock()

        async def exploding_session_factory():
            raise RuntimeError("DB 오류")

            class FakeCtx:  # noqa: unreachable
                async def __aenter__(self_inner):
                    return None

                async def __aexit__(self_inner, *a):
                    pass

            return FakeCtx()

        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)),
            patch(
                "api.src.middleware.audit.async_session_factory",
                side_effect=exploding_session_factory,
            ),
        ):
            app.dependency_overrides[get_session] = _mock_empty_db
            try:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.get(
                        "/api/v1/admin/audit-logs",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.pop(get_session, None)

        # DB 오류가 있어도 500이 아닌 정상 응답 (200)
        assert res.status_code == 200

    async def test_4xx_응답시_audit_log_INSERT_없음(self):
        """POST /api/v1/admin/* 가 4xx 응답(예: 405 Method Not Allowed)이면 INSERT 안 함 (Story 8.1 보강)."""
        token = _make_admin_jwt()
        user = _admin_user_mock()

        captured_logs: list = []

        def fake_session_factory():
            session = MagicMock()
            session.add = lambda obj: captured_logs.append(obj)
            session.commit = AsyncMock()

            class FakeCtx:
                async def __aenter__(self_inner):
                    return session

                async def __aexit__(self_inner, *a):
                    pass

            return FakeCtx()

        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)),
            patch(
                "api.src.middleware.audit.async_session_factory",
                side_effect=fake_session_factory,
            ),
        ):
            app.dependency_overrides[get_session] = _mock_empty_db
            try:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    # DELETE on audit-logs returns 405 — 4xx이므로 INSERT 없음
                    res = await client.delete(
                        "/api/v1/admin/audit-logs",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.pop(get_session, None)

        from api.src.models.audit_log import AuditLog
        # 4xx 응답 → INSERT 없음
        assert not any(isinstance(obj, AuditLog) for obj in captured_logs)

    async def test_target_type_target_id_diff_json_기록(self):
        """request.state에 audit_target_type/audit_target_id/audit_diff가 있으면 AuditLog에 반영 (Story 8.1 보강)."""
        token = _make_admin_jwt()
        user = _admin_user_mock()

        captured_logs: list = []

        def fake_session_factory():
            session = MagicMock()
            session.add = lambda obj: captured_logs.append(obj)
            session.commit = AsyncMock()

            class FakeCtx:
                async def __aenter__(self_inner):
                    return session

                async def __aexit__(self_inner, *a):
                    pass

            return FakeCtx()

        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)),
            patch(
                "api.src.middleware.audit.async_session_factory",
                side_effect=fake_session_factory,
            ),
        ):
            # 미들웨어가 request.state.audit_target_type 등을 읽는지 검증하기 위해
            # AuditMiddleware를 직접 테스트 (라우트 없이)
            from starlette.testclient import TestClient
            from starlette.applications import Starlette
            from starlette.routing import Route
            from starlette.responses import JSONResponse
            from api.src.middleware.audit import AuditMiddleware

            async def _dummy_view(req):
                req.state.audit_action = "test.action"
                req.state.audit_target_type = "test_resource"
                req.state.audit_target_id = 42
                req.state.audit_diff = {"key": "value"}
                return JSONResponse({"ok": True}, status_code=200)

            test_app = Starlette(
                routes=[Route("/api/v1/admin/test", _dummy_view, methods=["POST"])],
            )
            test_app.add_middleware(AuditMiddleware)

            client = TestClient(test_app, cookies={"denvia_admin_session": token})
            client.post("/api/v1/admin/test")

        from api.src.models.audit_log import AuditLog
        audit_entries = [obj for obj in captured_logs if isinstance(obj, AuditLog)]
        assert len(audit_entries) == 1
        entry = audit_entries[0]
        assert entry.target_type == "test_resource"
        assert entry.target_id == 42
        assert entry.diff_json == {"key": "value"}
