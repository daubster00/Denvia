"""Story 9.1 — retention_tasks.delete_old_payments 단위 테스트.

DELETE 쿼리가 실행되고, structlog가 deleted 카운트를 기록하는지 검증한다.
실제 DB 동작(5년 cutoff 자체)은 PostgreSQL의 INTERVAL 산술에 위임 —
본 테스트는 SQL 텍스트와 호출 흐름만 검증한다.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.src.workers import retention_tasks


def _async_session_factory(session: MagicMock) -> MagicMock:
    factory = MagicMock()

    class _Ctx:
        async def __aenter__(self_inner):
            return session

        async def __aexit__(self_inner, *exc):
            return False

    factory.return_value = _Ctx()
    return factory


@pytest.mark.asyncio
class TestDeleteOldPayments:
    async def test_executes_delete_with_5_year_interval(self) -> None:
        session = MagicMock()
        result = MagicMock()
        result.rowcount = 3
        session.execute = AsyncMock(return_value=result)
        session.commit = AsyncMock()

        with patch(
            "api.src.models.base.async_session_factory",
            _async_session_factory(session),
        ):
            out = await retention_tasks._delete_old_payments_async()

        assert out == {"deleted": 3}
        session.commit.assert_awaited_once()
        # SQL 본문에 5 years 간격이 포함되어야 함
        call = session.execute.await_args
        sql_text = str(call.args[0])
        assert "DELETE FROM payments" in sql_text
        assert "5 years" in sql_text

    async def test_zero_deleted_when_no_old_rows(self) -> None:
        session = MagicMock()
        result = MagicMock()
        result.rowcount = 0
        session.execute = AsyncMock(return_value=result)
        session.commit = AsyncMock()

        with patch(
            "api.src.models.base.async_session_factory",
            _async_session_factory(session),
        ):
            out = await retention_tasks._delete_old_payments_async()
        assert out == {"deleted": 0}
