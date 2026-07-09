"""#126 회귀 — 활동로그 operator 가시성은 커스텀 등급(g_*) 부관리자를 포함해야 한다.

버그: `_visible_actor_ids` 의 operator 분기가 `admin_grade == "sub_operator"` 문자열을
하드코딩해, 실서버 부관리자(커스텀 코드 g_1038039a 등)를 하나도 매칭하지 못했다.
결과적으로 operator 가 활동로그에서 부관리자의 질의응답 검토 기록을 볼 수 없었다.

교정: '전체 열람 등급(master/operator)이 아닌 모든 활성 관리자' 로 판정
(`admin_grade NOT IN ('master','operator')` + NOT NULL). qa_review_service 의
FULL_ACCESS_GRADES 판정과 동일 원리.

이 테스트는 operator 분기가 만들어내는 SELECT 의 컴파일된 SQL 을 직접 검증하므로,
누군가 다시 `== 'sub_operator'` 로 되돌리면 실패한다.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from api.src.services import admin_logs_service as svc


def _scalars_result(items: list) -> MagicMock:
    scalars_mock = MagicMock()
    scalars_mock.all = MagicMock(return_value=items)
    result = MagicMock()
    result.scalars = MagicMock(return_value=scalars_mock)
    return result


def _operator(user_id: int = 10) -> MagicMock:
    actor = MagicMock()
    actor.id = user_id
    actor.role = "admin"
    actor.admin_grade = "operator"
    actor.withdrawn_at = None
    return actor


@pytest.mark.asyncio
async def test_operator_visibility_query_uses_not_in_generalization():
    """operator 분기의 WHERE 절이 문자열 하드코딩이 아닌 NOT IN 일반화를 쓴다."""
    captured: dict = {}

    async def _fake_execute(stmt):
        captured["stmt"] = stmt
        # 본인 + 커스텀 등급 부관리자 두 명이 매칭됐다고 가정
        return _scalars_result([10, 80, 128])

    db = MagicMock()
    db.execute = AsyncMock(side_effect=_fake_execute)

    result = await svc._visible_actor_ids(db, _operator(10))

    # 반환값: 실행 결과 그대로
    assert result == [10, 80, 128]

    # 실제로 생성된 SQL 을 리터럴 바인딩으로 컴파일해 검사
    sql = str(
        captured["stmt"].compile(compile_kwargs={"literal_binds": True})
    ).lower()

    # NOT IN ('master','operator') 일반화가 존재해야 한다
    assert "not in" in sql
    assert "master" in sql and "operator" in sql
    # 문자열 하드코딩 방식으로 되돌아가면 실패
    assert "= 'sub_operator'" not in sql
    # 본인 id 조건도 포함
    assert "users.id = 10" in sql


@pytest.mark.asyncio
async def test_master_visibility_returns_none():
    """master 는 전체 가시 → None (쿼리 없이 단축)."""
    actor = MagicMock()
    actor.id = 7
    actor.admin_grade = "master"
    db = MagicMock()
    db.execute = AsyncMock()

    assert await svc._visible_actor_ids(db, actor) is None
    db.execute.assert_not_called()
