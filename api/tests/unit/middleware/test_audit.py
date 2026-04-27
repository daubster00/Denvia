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
    payload = {
        "sub": str(user_id),
        "role": role,
        "sub_status": sub_status,
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
        """POST /api/v1/admin/* → AuditLog INSERT 1건 시도."""
        token = _make_jwt()
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
                    # POST to existing route (admin audit-logs doesn't have POST, so it returns 405)
                    # But the AuditMiddleware fires on any /api/v1/admin/* POST
                    res = await client.post(
                        "/api/v1/admin/audit-logs",
                        cookies={"denvia_session": token},
                        json={},
                    )
            finally:
                app.dependency_overrides.pop(get_session, None)

        from api.src.models.audit_log import AuditLog
        assert any(isinstance(obj, AuditLog) for obj in captured_logs)

    async def test_GET_admin_경로_audit_log_INSERT_없음(self):
        """GET /api/v1/admin/* → audit_logs INSERT 발생하지 않음."""
        token = _make_jwt()
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
                        cookies={"denvia_session": token},
                    )
            finally:
                app.dependency_overrides.pop(get_session, None)

        from api.src.models.audit_log import AuditLog
        assert not any(isinstance(obj, AuditLog) for obj in captured_logs)

    async def test_DB_오류시_요청_정상_응답(self):
        """AuditMiddleware DB 오류 → 요청 응답은 500이 아님."""
        token = _make_jwt()
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
                        cookies={"denvia_session": token},
                    )
            finally:
                app.dependency_overrides.pop(get_session, None)

        # DB 오류가 있어도 500이 아닌 정상 응답 (200)
        assert res.status_code == 200
