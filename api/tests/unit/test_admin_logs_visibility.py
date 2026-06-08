"""Story 10.4 AC-3·AC-5 — `_visible_actor_ids` / `_assert_log_visible_to` 가드 12 케이스.

권한 분기:
- master         → 전체 가시 (visible = None)
- operator       → 본인 + 활성 sub_operator 만 (visible = [self_id, ...sub_ids])
- sub_operator   → 빈 리스트 (방어용)
- NULL 백필 누락 → 본인만 (보수적)

`_assert_log_visible_to(actor, log)` 가 master 통과, operator 가 본인/sub_operator 로그는 통과,
다른 actor 로그는 403 ADMIN_LOG_FORBIDDEN_ACTOR.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from api.src.services.admin_logs_service import (
    _assert_log_visible_to,
    _visible_actor_ids,
)


def _admin(user_id: int, grade: str | None) -> MagicMock:
    u = MagicMock()
    u.id = user_id
    u.role = "admin"
    u.withdrawn_at = None
    u.admin_grade = grade
    u.current_session_id = None
    return u


def _make_db_returning_ids(ids: list[int]):
    """db.execute(...).scalars().all() → ids 패턴 mock."""
    db = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = ids
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    db.execute = AsyncMock(return_value=result_mock)
    return db


def _log(actor_user_id: int) -> MagicMock:
    log = MagicMock()
    log.actor_user_id = actor_user_id
    return log


# ── _visible_actor_ids ────────────────────────────────────────────────────────


class TestVisibleActorIds:
    async def test_master_returns_None_for_full_visibility(self):
        master = _admin(1, "master")
        db = _make_db_returning_ids([])  # 호출 안 됨
        result = await _visible_actor_ids(db, master)
        assert result is None

    async def test_operator_returns_self_plus_sub_operators(self):
        op = _admin(10, "operator")
        # DB가 반환할 id 리스트 — 본인 + 2 sub_operator
        db = _make_db_returning_ids([10, 21, 22])
        result = await _visible_actor_ids(db, op)
        assert result == [10, 21, 22]
        db.execute.assert_awaited_once()

    async def test_operator_with_no_sub_operators_returns_only_self(self):
        op = _admin(10, "operator")
        db = _make_db_returning_ids([10])
        result = await _visible_actor_ids(db, op)
        assert result == [10]

    async def test_sub_operator_returns_empty_list(self):
        sub = _admin(30, "sub_operator")
        db = _make_db_returning_ids([])
        result = await _visible_actor_ids(db, sub)
        assert result == []

    async def test_null_grade_legacy_returns_self_only(self):
        legacy = _admin(99, None)
        db = _make_db_returning_ids([])
        result = await _visible_actor_ids(db, legacy)
        assert result == [99]


# ── _assert_log_visible_to ────────────────────────────────────────────────────


class TestAssertLogVisibleTo:
    async def test_master_passes_any_actor_log(self):
        master = _admin(1, "master")
        log = _log(actor_user_id=42)
        db = _make_db_returning_ids([])
        # 예외 없음
        await _assert_log_visible_to(db, master, log)

    async def test_operator_self_log_passes(self):
        op = _admin(10, "operator")
        log = _log(actor_user_id=10)
        db = _make_db_returning_ids([10, 21])  # self + sub_op
        await _assert_log_visible_to(db, op, log)

    async def test_operator_sub_operator_log_passes(self):
        op = _admin(10, "operator")
        log = _log(actor_user_id=21)
        db = _make_db_returning_ids([10, 21])
        await _assert_log_visible_to(db, op, log)

    async def test_operator_master_log_blocked_403(self):
        op = _admin(10, "operator")
        log = _log(actor_user_id=1)  # master id
        db = _make_db_returning_ids([10, 21])
        with pytest.raises(HTTPException) as exc:
            await _assert_log_visible_to(db, op, log)
        assert exc.value.status_code == 403
        assert exc.value.detail["code"] == "ADMIN_LOG_FORBIDDEN_ACTOR"

    async def test_operator_other_operator_log_blocked_403(self):
        op = _admin(10, "operator")
        log = _log(actor_user_id=11)  # 다른 operator id
        db = _make_db_returning_ids([10, 21])
        with pytest.raises(HTTPException) as exc:
            await _assert_log_visible_to(db, op, log)
        assert exc.value.status_code == 403
        assert exc.value.detail["code"] == "ADMIN_LOG_FORBIDDEN_ACTOR"

    async def test_operator_nonexistent_actor_id_blocked_403(self):
        """존재하지 않는 actor id → 가시성 우선 → 403 (404 아님 — enum 누설 방지)."""
        op = _admin(10, "operator")
        log = _log(actor_user_id=999999)
        db = _make_db_returning_ids([10, 21])
        with pytest.raises(HTTPException) as exc:
            await _assert_log_visible_to(db, op, log)
        assert exc.value.status_code == 403

    async def test_sub_operator_blocked_for_any_log(self):
        """sub_operator 는 visible=[] → 어떤 로그도 차단(방어용)."""
        sub = _admin(30, "sub_operator")
        log = _log(actor_user_id=30)
        db = _make_db_returning_ids([])
        with pytest.raises(HTTPException) as exc:
            await _assert_log_visible_to(db, sub, log)
        assert exc.value.status_code == 403
