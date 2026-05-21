"""career_tasks.annual_increment 단위 테스트.

mock session 기반으로:
- 대상 0건 (모두 올해 last_increment_year) → incremented_count=0, UPDATE 호출 안 함.
- 대상 N건 → SELECT count + UPDATE 1회 호출, commit, engine dispose.
- now_kst() 의 연도 값이 응답 / SQL 가드값에 그대로 반영.

ORM expression 정확성은 PG 통합 테스트 영역. 본 테스트는 흐름·멱등성 가드만 검증.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.src.workers import career_tasks


def _make_session() -> MagicMock:
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    return session


def _async_session_factory_returning(session: MagicMock) -> MagicMock:
    factory = MagicMock()

    class _Ctx:
        async def __aenter__(self_inner):
            return session

        async def __aexit__(self_inner, *exc):
            return False

    factory.return_value = _Ctx()
    return factory


def _kst_dt(year: int) -> MagicMock:
    dt = MagicMock(spec=datetime)
    dt.year = year
    return dt


@pytest.mark.asyncio
class TestAnnualIncrement:
    async def _run(
        self,
        *,
        current_year: int,
        target_count: int,
        update_rowcount: int | None = None,
    ) -> dict:
        """target_count=0 이면 UPDATE 호출 자체가 일어나지 않아야 한다."""
        session = _make_session()

        # 1) SELECT count
        count_result = MagicMock()
        count_result.scalar_one = MagicMock(return_value=target_count)

        # 2) UPDATE (대상 있을 때만)
        update_result = MagicMock()
        update_result.rowcount = (
            target_count if update_rowcount is None else update_rowcount
        )

        side: list = [count_result]
        if target_count > 0:
            side.append(update_result)
        session.execute.side_effect = side

        engine = MagicMock()
        engine.dispose = AsyncMock()

        with (
            patch.object(career_tasks, "create_async_engine", return_value=engine),
            patch.object(
                career_tasks,
                "async_sessionmaker",
                return_value=_async_session_factory_returning(session),
            ),
            patch.object(
                career_tasks, "now_kst", return_value=_kst_dt(current_year)
            ),
        ):
            result = await career_tasks._annual_increment_async()
        return {"result": result, "session": session, "engine": engine}

    async def test_no_targets_returns_zero(self):
        """모두 올해 last_increment_year로 셋 돼 있으면 0건 처리(멱등성)."""
        outcome = await self._run(current_year=2027, target_count=0)
        assert outcome["result"]["incremented_count"] == 0
        assert outcome["result"]["current_year"] == 2027
        # SELECT count 1회만 호출, UPDATE/commit 없음
        assert outcome["session"].execute.await_count == 1
        outcome["session"].commit.assert_not_called()
        outcome["engine"].dispose.assert_awaited_once()

    async def test_targets_increment_and_commit(self):
        """대상 N건 → SELECT + UPDATE 호출, commit/dispose 보장."""
        outcome = await self._run(current_year=2027, target_count=3)
        assert outcome["result"]["incremented_count"] == 3
        assert outcome["result"]["current_year"] == 2027
        # SELECT count + UPDATE = 2회
        assert outcome["session"].execute.await_count == 2
        outcome["session"].commit.assert_awaited_once()
        outcome["engine"].dispose.assert_awaited_once()

    async def test_current_year_reflected(self):
        """now_kst() 의 연도가 응답 current_year 에 그대로 반영."""
        outcome = await self._run(current_year=2030, target_count=1)
        assert outcome["result"]["current_year"] == 2030

    async def test_engine_disposed_even_on_exception(self):
        """SELECT 단계 예외 시에도 engine.dispose 가 호출되어야 한다."""
        session = _make_session()
        session.execute.side_effect = RuntimeError("boom")

        engine = MagicMock()
        engine.dispose = AsyncMock()

        with (
            patch.object(career_tasks, "create_async_engine", return_value=engine),
            patch.object(
                career_tasks,
                "async_sessionmaker",
                return_value=_async_session_factory_returning(session),
            ),
            patch.object(career_tasks, "now_kst", return_value=_kst_dt(2027)),
            pytest.raises(RuntimeError),
        ):
            await career_tasks._annual_increment_async()

        engine.dispose.assert_awaited_once()
