"""Story 10.4 — `/admin/accounts/logs` 통합 테스트.

검증 항목 (AC-1·3·5·7):
- master/operator 권한 분기 (403 ADMIN_LOG_FORBIDDEN_ACTOR)
- cursor pagination (limit+1 fetch → next_cursor)
- 필터: action_in, target_id, from_at/to_at
- 422: limit out of range, from_at > to_at
- diff 응답 REDACTED 마스킹
- xlsx export + X-Truncated 헤더
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest
from httpx import ASGITransport, AsyncClient

from api.src.main import app
from api.src.models.base import get_session
from api.src.settings import settings


# ── 픽스처 빌더 ────────────────────────────────────────────────────────────────


def _make_admin_jwt(user_id: int = 1) -> str:
    payload = {
        "sub": str(user_id),
        "aud": "denvia-admin",
        "exp": int(time.time()) + 3600,
    }
    return pyjwt.encode(
        payload, settings.denvia_jwt_secret, algorithm=settings.denvia_jwt_algorithm
    )


def _make_admin(user_id: int, grade: str = "master") -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.email = f"admin{user_id}@denvia.local"
    user.role = "admin"
    user.subscription_status = "free"
    user.segment = None
    user.withdrawn_at = None
    user.admin_grade = grade
    user.must_reset_password = False
    return user


def _make_audit_row(
    *,
    id_: int,
    actor_user_id: int,
    target_id: int | None = None,
    action: str = "admin.account.approved",
    diff: dict | None = None,
    created_at: datetime | None = None,
) -> MagicMock:
    log = MagicMock()
    log.id = id_
    log.actor_user_id = actor_user_id
    log.action = action
    log.target_type = "user" if target_id is not None else None
    log.target_id = target_id
    log.diff_json = diff
    log.ip = "127.0.0.1"
    log.ua = "pytest"
    log.trace_id = uuid.uuid4()
    log.created_at = created_at or datetime(2026, 5, 27, 12, 0, 0, tzinfo=timezone.utc)
    return log


def _scalars_result(items: list) -> MagicMock:
    """`db.execute(...).scalars().all()` 패턴 mock."""
    scalars_mock = MagicMock()
    scalars_mock.all = MagicMock(return_value=items)
    result = MagicMock()
    result.scalars = MagicMock(return_value=scalars_mock)
    return result


def _scalar_one_or_none(value) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=value)
    return result


def _rows_result(rows: list[tuple]) -> MagicMock:
    """`db.execute(select(User.id, User.email)).all()` → 튜플(.id, .email) 리스트."""
    out = []
    for uid, email in rows:
        m = MagicMock()
        m.id = uid
        m.email = email
        # iteration support for dict({row.id: row.email for row in result})
        m.__iter__ = lambda self=m: iter([self.id, self.email])
        out.append(m)
    # The service iterates `for row in result` directly
    result = MagicMock()
    result.__iter__ = lambda self: iter(out)
    return result


def _override_session(session: MagicMock):
    async def gen():
        yield session

    app.dependency_overrides[get_session] = gen
    return gen


@pytest.mark.asyncio
class TestAdminLogsList:
    """GET /api/v1/admin/accounts/logs — 6 시나리오 (AC-1·3·5)."""

    async def _make_client(self):
        return AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        )

    async def test_master_lists_all_logs_200(self):
        token = _make_admin_jwt(user_id=1)
        master = _make_admin(1, "master")

        log1 = _make_audit_row(
            id_=100, actor_user_id=1, target_id=42, action="admin.account.approved"
        )
        log2 = _make_audit_row(
            id_=99, actor_user_id=1, target_id=43, action="admin.account.blocked"
        )

        session = MagicMock()
        # master visible=None → _visible_actor_ids 호출 안 함
        # list_logs: stmt 실행 (logs) → actor_email_map → target_preview_map
        session.execute = AsyncMock(side_effect=[
            _scalars_result([log1, log2]),  # main logs query
            _rows_result([(1, "admin1@denvia.local")]),  # actor emails
            _rows_result([(42, "u42@denvia.local"), (43, "u43@denvia.local")]),  # targets
        ])

        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=master)):
            _override_session(session)
            try:
                async with await self._make_client() as client:
                    res = await client.get(
                        "/api/v1/admin/accounts/logs?limit=10",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()

        assert res.status_code == 200, res.text
        body = res.json()
        assert len(body["items"]) == 2
        assert body["next_cursor"] is None
        assert body["items"][0]["action"] == "admin.account.approved"
        assert body["items"][0]["actor_email"] == "admin1@denvia.local"
        assert body["items"][0]["target_preview"] == "u42@denvia.local"
        assert body["items"][0]["has_diff"] is False

    async def test_operator_other_operator_actor_id_blocked_403(self):
        """operator → 다른 operator id 입력 → 403 ADMIN_LOG_FORBIDDEN_ACTOR."""
        token = _make_admin_jwt(user_id=10)
        op = _make_admin(10, "operator")

        session = MagicMock()
        # _visible_actor_ids 호출(operator) → [10, 21] (self + sub_op)
        session.execute = AsyncMock(side_effect=[
            _scalars_result([10, 21]),  # _visible_actor_ids
        ])

        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=op)):
            _override_session(session)
            try:
                async with await self._make_client() as client:
                    res = await client.get(
                        "/api/v1/admin/accounts/logs?actor_id=11",  # 다른 operator
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()

        assert res.status_code == 403
        assert res.json()["code"] == "ADMIN_LOG_FORBIDDEN_ACTOR"

    async def test_operator_system_actor_id_blocked_403(self):
        """operator → actor_id=system 입력 → 403 (시스템은 master 전용)."""
        token = _make_admin_jwt(user_id=10)
        op = _make_admin(10, "operator")

        session = MagicMock()
        # _visible_actor_ids → [10] / 이어 system 가드 단계에서 403
        session.execute = AsyncMock(side_effect=[
            _scalars_result([10]),
        ])

        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=op)):
            _override_session(session)
            try:
                async with await self._make_client() as client:
                    res = await client.get(
                        "/api/v1/admin/accounts/logs?actor_id=system",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()

        assert res.status_code == 403
        assert res.json()["code"] == "ADMIN_LOG_FORBIDDEN_ACTOR"

    async def test_operator_no_actor_id_auto_filters_to_visible(self):
        """operator → actor_id 미지정 → 자동 필터 (본인+sub_op 만 응답)."""
        token = _make_admin_jwt(user_id=10)
        op = _make_admin(10, "operator")

        log_sub = _make_audit_row(
            id_=50, actor_user_id=21, target_id=42, action="user.permission_edit"
        )

        session = MagicMock()
        session.execute = AsyncMock(side_effect=[
            _scalars_result([10, 21]),  # _visible_actor_ids
            _scalars_result([log_sub]),  # main logs query
            _rows_result([(21, "subop@denvia.local")]),
            _rows_result([(42, "u42@denvia.local")]),
        ])

        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=op)):
            _override_session(session)
            try:
                async with await self._make_client() as client:
                    res = await client.get(
                        "/api/v1/admin/accounts/logs?limit=5",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()

        assert res.status_code == 200
        body = res.json()
        assert len(body["items"]) == 1
        assert body["items"][0]["actor_user_id"] == 21
        assert body["items"][0]["actor_email"] == "subop@denvia.local"

    async def test_cursor_pagination_returns_next_cursor(self):
        """limit=2 + 3건 반환 → next_cursor 발급."""
        token = _make_admin_jwt(user_id=1)
        master = _make_admin(1, "master")

        logs = [
            _make_audit_row(
                id_=300 - i,
                actor_user_id=1,
                action="admin.account.approved",
                created_at=datetime(2026, 5, 27, 12, 0, 0, tzinfo=timezone.utc),
            )
            for i in range(3)
        ]

        session = MagicMock()
        session.execute = AsyncMock(side_effect=[
            _scalars_result(logs),  # 3건 반환 (limit+1)
            _rows_result([(1, "admin1@denvia.local")]),
            _rows_result([]),
        ])

        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=master)):
            _override_session(session)
            try:
                async with await self._make_client() as client:
                    res = await client.get(
                        "/api/v1/admin/accounts/logs?limit=2",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()

        assert res.status_code == 200
        body = res.json()
        assert len(body["items"]) == 2
        assert body["next_cursor"] is not None

    async def test_invalid_range_returns_422(self):
        """from_at > to_at → 422 INVALID_RANGE."""
        token = _make_admin_jwt(user_id=1)
        master = _make_admin(1, "master")

        session = MagicMock()
        session.execute = AsyncMock(return_value=_scalars_result([]))

        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=master)):
            _override_session(session)
            try:
                async with await self._make_client() as client:
                    res = await client.get(
                        "/api/v1/admin/accounts/logs"
                        "?from_at=2026-05-27T23:59:59%2B00:00"
                        "&to_at=2026-05-27T00:00:00%2B00:00",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()

        assert res.status_code == 422
        assert res.json()["code"] == "INVALID_RANGE"

    async def test_invalid_limit_returns_422(self):
        """limit > 200 → FastAPI Query(le=200) 가 422."""
        token = _make_admin_jwt(user_id=1)
        master = _make_admin(1, "master")

        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=master)):
            async with await self._make_client() as client:
                res = await client.get(
                    "/api/v1/admin/accounts/logs?limit=300",
                    cookies={"denvia_admin_session": token},
                )

        assert res.status_code == 422


@pytest.mark.asyncio
class TestAdminLogDiff:
    """GET /api/v1/admin/accounts/logs/{id}/diff — 2 시나리오 (AC-4·5)."""

    async def _make_client(self):
        return AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        )

    async def test_master_gets_diff_with_password_hash_redacted(self):
        """master 가 operator 가 남긴 로그 diff 조회 → REDACTED 마스킹된 200."""
        token = _make_admin_jwt(user_id=1)
        master = _make_admin(1, "master")

        log = _make_audit_row(
            id_=500,
            actor_user_id=10,  # operator 의 로그 (master actor 가 아님)
            target_id=42,
            action="admin.account.approved",
            diff={
                "before": {"admin_grade": "pending", "password_hash": "old_hash"},
                "after": {"admin_grade": "sub_operator"},
            },
        )

        session = MagicMock()
        # 1) log fetch  2) log.actor 의 admin_grade 조회 (master 제외 가드)
        session.execute = AsyncMock(side_effect=[
            _scalar_one_or_none(log),
            _scalar_one_or_none("operator"),
        ])

        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=master)):
            _override_session(session)
            try:
                async with await self._make_client() as client:
                    res = await client.get(
                        "/api/v1/admin/accounts/logs/500/diff",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()

        assert res.status_code == 200
        body = res.json()
        assert body["id"] == 500
        assert body["diff_json"]["before"]["password_hash"] == "***REDACTED***"
        assert body["diff_json"]["before"]["admin_grade"] == "pending"
        assert body["diff_json"]["after"]["admin_grade"] == "sub_operator"

    async def test_operator_cannot_view_master_log_diff_404(self):
        """operator 가 master actor 의 로그 diff 직접 조회 → 404 (master 제외 정책).

        목록에서 안 보이는 로그는 직접 조회도 동일하게 숨김(404 — 존재 자체를 노출 X).
        """
        token = _make_admin_jwt(user_id=10)
        op = _make_admin(10, "operator")

        log = _make_audit_row(
            id_=501, actor_user_id=1, action="admin.account.approved"
        )  # actor=1 (master), non-system action

        session = MagicMock()
        # 1) log fetch  2) log.actor 의 admin_grade='master' → 404
        session.execute = AsyncMock(side_effect=[
            _scalar_one_or_none(log),
            _scalar_one_or_none("master"),
        ])

        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=op)):
            _override_session(session)
            try:
                async with await self._make_client() as client:
                    res = await client.get(
                        "/api/v1/admin/accounts/logs/501/diff",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()

        assert res.status_code == 404
        assert res.json()["code"] == "AUDIT_LOG_NOT_FOUND"

    async def test_master_cannot_view_own_non_system_log_diff_404(self):
        """master 가 본인 (master actor) 의 일반 액션 로그 diff 조회 → 404.

        마스터 활동 이력은 노출하지 않는 정책. 시스템 자동 액션만 예외.
        """
        token = _make_admin_jwt(user_id=1)
        master = _make_admin(1, "master")

        log = _make_audit_row(
            id_=502, actor_user_id=1, action="admin.account.approved"
        )

        session = MagicMock()
        session.execute = AsyncMock(side_effect=[
            _scalar_one_or_none(log),
            _scalar_one_or_none("master"),
        ])

        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=master)):
            _override_session(session)
            try:
                async with await self._make_client() as client:
                    res = await client.get(
                        "/api/v1/admin/accounts/logs/502/diff",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()

        assert res.status_code == 404
        assert res.json()["code"] == "AUDIT_LOG_NOT_FOUND"

    async def test_master_can_view_system_coded_master_log_diff_200(self):
        """master actor 로 저장된 시스템 코드(`_SYSTEM_ACTION_CODES`) 로그는 예외적으로 조회 허용.

        시스템 자동 액션이 첫 admin=master 로 INSERT 되는 한계 때문에, system 필터
        분기에서 보여줘야 하므로 diff 조회도 허용한다.
        """
        token = _make_admin_jwt(user_id=1)
        master = _make_admin(1, "master")

        log = _make_audit_row(
            id_=503, actor_user_id=1, action="user.block_auto_expired"
        )

        session = MagicMock()
        session.execute = AsyncMock(side_effect=[
            _scalar_one_or_none(log),
            _scalar_one_or_none("master"),
        ])

        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=master)):
            _override_session(session)
            try:
                async with await self._make_client() as client:
                    res = await client.get(
                        "/api/v1/admin/accounts/logs/503/diff",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()

        assert res.status_code == 200
        assert res.json()["id"] == 503


@pytest.mark.asyncio
class TestAdminLogsExport:
    """GET /api/v1/admin/accounts/logs/export.xlsx — 2 시나리오 (AC-7)."""

    async def _make_client(self):
        return AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        )

    async def test_export_returns_xlsx_with_content_disposition(self):
        token = _make_admin_jwt(user_id=1)
        master = _make_admin(1, "master")

        log = _make_audit_row(id_=600, actor_user_id=1, action="admin.account.approved")
        session = MagicMock()
        session.execute = AsyncMock(side_effect=[
            _scalars_result([log]),
            _rows_result([(1, "admin1@denvia.local")]),
            _rows_result([]),
        ])

        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=master)):
            _override_session(session)
            try:
                async with await self._make_client() as client:
                    res = await client.get(
                        "/api/v1/admin/accounts/logs/export.xlsx",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()

        assert res.status_code == 200
        assert (
            res.headers["content-type"]
            == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert "attachment" in res.headers["content-disposition"]
        assert "admin_logs_" in res.headers["content-disposition"]
        # X-Truncated 헤더는 1행밖에 없으니 없어야 함
        assert res.headers.get("x-truncated") is None
        # xlsx 매직 바이트 (zip = PK)
        assert res.content[:2] == b"PK"

    async def test_export_truncated_header_when_over_limit(self):
        """10,001 행 시드 → X-Truncated: true 헤더."""
        token = _make_admin_jwt(user_id=1)
        master = _make_admin(1, "master")

        # _MAX_EXPORT_ROWS + 1 = 10001 — mock 으로 빠르게 시뮬레이션
        many_logs = [
            _make_audit_row(id_=i, actor_user_id=1, action="admin.account.approved")
            for i in range(10_001)
        ]

        session = MagicMock()
        session.execute = AsyncMock(side_effect=[
            _scalars_result(many_logs),
            _rows_result([(1, "admin1@denvia.local")]),
            _rows_result([]),
        ])

        with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=master)):
            _override_session(session)
            try:
                async with await self._make_client() as client:
                    res = await client.get(
                        "/api/v1/admin/accounts/logs/export.xlsx",
                        cookies={"denvia_admin_session": token},
                    )
            finally:
                app.dependency_overrides.clear()

        assert res.status_code == 200
        assert res.headers.get("x-truncated") == "true"
