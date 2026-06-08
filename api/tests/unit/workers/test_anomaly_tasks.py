"""Story 6.2 — anomaly_tasks.expire_blocks 단위 테스트.

본 테스트는 _expire_blocks_async 의 SELECT/UPDATE/INSERT 흐름을 mock session으로 검증한다.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.src.middleware.audit_actions import AUDIT_USER_BLOCK_AUTO_EXPIRED
from api.src.models.audit_log import AuditLog
from api.src.services import admin_account_service
from api.src.workers import anomaly_tasks


@pytest.fixture
def stub_engine():
    engine = MagicMock()
    engine.dispose = AsyncMock()
    return engine


def _make_session() -> MagicMock:
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
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


def _row(
    id_: int,
    email: str = "u@example.com",
    pre_block_status: str | None = None,
) -> MagicMock:
    row = MagicMock()
    row.id = id_
    row.email = email
    row.pre_block_status = pre_block_status
    return row


@pytest.mark.asyncio
class TestExpireBlocks:
    async def _run(
        self,
        target_rows: list[MagicMock],
        actor_id: int | None = 1,
    ) -> dict:
        session = _make_session()
        # execute side_effect 순서:
        # 1) SELECT 만료 후보 (.all() 반환)
        # 2) (target_rows 비어있지 않으면) SELECT actor_user_id (scalar_one_or_none)
        # 3) UPDATE pro_ids (조건부 — pro 유저 존재 시)
        # 4) UPDATE free_ids (조건부 — free/None 유저 존재 시)
        select_target_result = MagicMock()
        select_target_result.all = MagicMock(return_value=target_rows)

        select_actor_result = MagicMock()
        select_actor_result.scalar_one_or_none = MagicMock(return_value=actor_id)

        side = [select_target_result]
        if target_rows:
            side.append(select_actor_result)
            # 최대 2개 UPDATE (pro / free) — 사용되지 않는 항목은 무시
            side.append(MagicMock())
            side.append(MagicMock())
        else:
            # Story 10.3 — 빈 target 경로에서도 admin 분기 진입 전에
            # _resolve_system_actor_id(session) 가 호출된다. (admin 분기는 patch 로 stub)
            side.append(select_actor_result)
        session.execute.side_effect = side

        engine = MagicMock()
        engine.dispose = AsyncMock()

        # Story 10.3 — _expire_blocks_async 가 _expire_admin_blocks 도 호출하므로
        # admin 분기를 통째로 patch 해 사용자 분기 mock 흐름에 간섭하지 않게 한다.
        # 별도 unit test(test_expire_admin_blocks_*) 가 admin 분기를 단독 검증.
        admin_branch_stub = AsyncMock(
            return_value={"expired_count": 0, "expired_ids": []}
        )
        with (
            patch.object(
                anomaly_tasks,
                "create_async_engine",
                return_value=engine,
            ),
            patch.object(
                anomaly_tasks,
                "async_sessionmaker",
                return_value=_async_session_factory_returning(session),
            ),
            patch.object(
                anomaly_tasks,
                "_expire_admin_blocks",
                new=admin_branch_stub,
            ),
            patch.object(
                admin_account_service,
                "expire_admin_blocks",
                new=AsyncMock(return_value={"expired_count": 0, "expired_ids": []}),
            ),
        ):
            result = await anomaly_tasks._expire_blocks_async()
        return {"result": result, "session": session, "engine": engine}

    async def test_no_targets_returns_zero(self):
        outcome = await self._run([])
        assert outcome["result"]["expired_count"] == 0
        outcome["session"].add.assert_not_called()
        outcome["session"].commit.assert_not_called()
        outcome["engine"].dispose.assert_awaited_once()

    async def test_single_target_inserts_audit_log(self):
        outcome = await self._run([_row(42, "blocked@x.com")])
        assert outcome["result"]["expired_count"] == 1
        # 1) audit_log + 차단해제 직후 commit, 2) inbox 발송 후 commit — 총 2회.
        assert outcome["session"].commit.await_count == 2
        added = outcome["session"].add.call_args_list
        assert len(added) == 1
        log = added[0].args[0]
        assert isinstance(log, AuditLog)
        assert log.action == AUDIT_USER_BLOCK_AUTO_EXPIRED
        assert log.target_type == "user"
        assert log.target_id == 42
        assert log.diff_json["before"]["subscription_status"] == "blocked"
        # pre_block_status=None → free로 복원
        assert log.diff_json["after"]["subscription_status"] == "free"
        assert log.actor_user_id == 1

    async def test_pro_user_restored_to_pro_on_expire(self):
        """pro 사용자가 차단 만료 시 free가 아닌 pro로 복원된다."""
        outcome = await self._run([_row(99, "pro@x.com", pre_block_status="pro")])
        assert outcome["result"]["expired_count"] == 1
        added = outcome["session"].add.call_args_list
        assert len(added) == 1
        log = added[0].args[0]
        assert log.diff_json["before"]["subscription_status"] == "blocked"
        assert log.diff_json["after"]["subscription_status"] == "pro"

    async def test_multiple_targets_insert_each_audit(self):
        rows = [_row(1), _row(2), _row(3)]
        outcome = await self._run(rows, actor_id=99)
        assert outcome["result"]["expired_count"] == 3
        assert outcome["session"].add.call_count == 3
        all_target_ids = [
            call.args[0].target_id for call in outcome["session"].add.call_args_list
        ]
        assert sorted(all_target_ids) == [1, 2, 3]
        for call in outcome["session"].add.call_args_list:
            assert call.args[0].actor_user_id == 99

    async def test_no_system_actor_returns_error(self):
        outcome = await self._run([_row(42)], actor_id=None)
        assert outcome["result"]["expired_count"] == 0
        assert outcome["result"].get("error") == "no_system_actor"
        outcome["session"].add.assert_not_called()
        outcome["session"].commit.assert_not_called()
