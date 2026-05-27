"""Story 10.5 — admin_grade_permission_service 단위 테스트.

검증 항목:
1) get_matrix 가 ADMIN_PAGE_ROUTES × CONFIGURABLE_GRADES 만큼의 셀을 반환
2) upsert_permission 이 master 아닌 등급 → master 부여 시 422
3) upsert_permission 이 알 수 없는 page_route 에 422
4) is_page_allowed 의 etoe 매트릭스 분기 (master 통과, operator default true, sub_operator default false)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api.src.services.admin_grade_permission_service import (
    ADMIN_PAGE_ROUTES,
    CONFIGURABLE_GRADES,
    get_matrix,
    is_page_allowed,
    upsert_permission,
)


def _make_admin(user_id: int = 1, grade: str = "master") -> MagicMock:
    u = MagicMock()
    u.id = user_id
    u.admin_grade = grade
    return u


class TestGetMatrix:
    async def test_빈_DB_도_기본값으로_18행_반환(self):
        db = MagicMock()
        scalars = MagicMock()
        scalars.all = MagicMock(return_value=[])
        execute_result = MagicMock()
        execute_result.scalars = MagicMock(return_value=scalars)
        db.execute = AsyncMock(return_value=execute_result)

        result = await get_matrix(db)
        expected_count = len(ADMIN_PAGE_ROUTES) * len(CONFIGURABLE_GRADES)
        assert len(result["rows"]) == expected_count
        # operator 기본 ON / sub_operator 기본 OFF
        for row in result["rows"]:
            if row["admin_grade"] == "operator":
                assert row["allowed"] is True
            else:
                assert row["allowed"] is False
        assert result["grades"] == ["operator", "sub_operator"]
        assert len(result["pages"]) == len(ADMIN_PAGE_ROUTES)


class TestUpsertPermission:
    def _mock_db_no_existing(self) -> MagicMock:
        db = MagicMock()
        select_result = MagicMock()
        select_result.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=select_result)
        db.flush = AsyncMock()
        return db

    async def test_알수없는_route_422(self):
        actor = _make_admin()
        db = self._mock_db_no_existing()
        with pytest.raises(HTTPException) as exc:
            await upsert_permission(
                db,
                actor=actor,
                admin_grade="operator",
                page_route="/admin/__unknown__",
                allowed=True,
            )
        assert exc.value.status_code == 422
        assert exc.value.detail["code"] == "ADMIN_PAGE_ROUTE_UNKNOWN"

    async def test_설정대상_아닌_등급_422(self):
        actor = _make_admin()
        db = self._mock_db_no_existing()
        with pytest.raises(HTTPException) as exc:
            await upsert_permission(
                db,
                actor=actor,
                admin_grade="master",  # master 는 매트릭스 대상 아님
                page_route="/admin",
                allowed=True,
            )
        assert exc.value.status_code == 422
        assert exc.value.detail["code"] == "ADMIN_GRADE_NOT_CONFIGURABLE"

    async def test_정상_케이스_diff_반환(self):
        actor = _make_admin()
        db = self._mock_db_no_existing()
        result = await upsert_permission(
            db,
            actor=actor,
            admin_grade="sub_operator",
            page_route="/admin/users",
            allowed=True,
        )
        assert result["row"]["allowed"] is True
        assert result["row"]["admin_grade"] == "sub_operator"
        # sub_operator default = False, 변경 후 True
        assert result["diff"]["before"]["allowed"] is False
        assert result["diff"]["after"]["allowed"] is True


class TestIsPageAllowed:
    async def test_master_는_항상_True(self):
        db = MagicMock()
        result = await is_page_allowed(
            db, admin_grade="master", page_route="/admin/finance"
        )
        assert result is True

    async def test_매트릭스_외_route_는_통과(self):
        db = MagicMock()
        # /admin/admins 는 require_admin_grade 가 처리하므로 매트릭스 외부.
        result = await is_page_allowed(
            db, admin_grade="sub_operator", page_route="/admin/admins"
        )
        assert result is True

    async def test_operator_누락셀_True_default(self):
        db = MagicMock()
        select_result = MagicMock()
        select_result.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=select_result)
        result = await is_page_allowed(
            db, admin_grade="operator", page_route="/admin/finance"
        )
        assert result is True

    async def test_sub_operator_누락셀_False_default(self):
        db = MagicMock()
        select_result = MagicMock()
        select_result.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=select_result)
        result = await is_page_allowed(
            db, admin_grade="sub_operator", page_route="/admin/finance"
        )
        assert result is False

    async def test_sub_operator_명시적_True_허용(self):
        db = MagicMock()
        select_result = MagicMock()
        select_result.scalar_one_or_none = MagicMock(return_value=True)
        db.execute = AsyncMock(return_value=select_result)
        result = await is_page_allowed(
            db, admin_grade="sub_operator", page_route="/admin/finance"
        )
        assert result is True

    async def test_pending_은_False(self):
        db = MagicMock()
        result = await is_page_allowed(
            db, admin_grade="pending", page_route="/admin"
        )
        assert result is False
