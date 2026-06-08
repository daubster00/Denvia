"""Story 10.5 — admin_grade_permission_service 단위 테스트.

검증 항목:
1) get_matrix 가 ADMIN_PAGE_ROUTES × 설정 가능 등급 만큼의 셀을 반환
2) upsert_permission 이 매트릭스 비대상 등급(master/pending) 부여 시 422
3) upsert_permission 이 알 수 없는 page_route 에 422
4) is_page_allowed 의 etoe 매트릭스 분기 (master 통과, operator default true, sub_operator default false)

0057 이후 매트릭스 등급은 admin_grades 테이블에서 동적 조회되므로 mock 패치로 테스트.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api.src.services.admin_grade_permission_service import (
    ADMIN_PAGE_ROUTES,
    get_matrix,
    is_page_allowed,
    upsert_permission,
)


def _make_admin(user_id: int = 1, grade: str = "master") -> MagicMock:
    u = MagicMock()
    u.id = user_id
    u.admin_grade = grade
    u.current_session_id = None
    return u


def _make_grade_row(code: str, label: str, is_builtin: bool = True) -> MagicMock:
    g = MagicMock()
    g.code = code
    g.label = label
    g.is_builtin = is_builtin
    g.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return g


class TestGetMatrix:
    async def test_빈_매트릭스도_기본값으로_18행_반환(self):
        """admin_grades 에는 내장 4종(operator, sub_operator) 만 매트릭스 대상."""
        db = MagicMock()

        # 첫 번째 execute: select(AdminGrade) → 4 builtins
        grade_scalars = MagicMock()
        grade_scalars.all = MagicMock(
            return_value=[
                _make_grade_row("master", "마스터"),
                _make_grade_row("operator", "운영 관리자"),
                _make_grade_row("sub_operator", "부운영자"),
                _make_grade_row("pending", "승인 대기"),
            ]
        )
        grade_result = MagicMock()
        grade_result.scalars = MagicMock(return_value=grade_scalars)

        # 두 번째 execute: select(AdminGradePagePermission) → 빈
        perm_scalars = MagicMock()
        perm_scalars.all = MagicMock(return_value=[])
        perm_result = MagicMock()
        perm_result.scalars = MagicMock(return_value=perm_scalars)

        db.execute = AsyncMock(side_effect=[grade_result, perm_result])

        result = await get_matrix(db)
        # master/pending 제외 → operator + sub_operator 2개 컬럼
        expected_count = len(ADMIN_PAGE_ROUTES) * 2
        assert len(result["rows"]) == expected_count
        for row in result["rows"]:
            if row["admin_grade"] == "operator":
                assert row["allowed"] is True
            else:
                assert row["allowed"] is False
        assert result["grades"] == ["operator", "sub_operator"]
        assert len(result["grade_meta"]) == 2
        assert len(result["pages"]) == len(ADMIN_PAGE_ROUTES)


class TestUpsertPermission:
    def _mock_db_known_grade(self, grade_code: str = "operator") -> MagicMock:
        """upsert_permission 은 _validate_grade_configurable 안에서 select(AdminGrade.code) 한 번,
        이후 기존 셀 lookup select 한 번, 총 2번 execute."""
        db = MagicMock()

        # 첫 호출: 등급 존재 확인
        exists_result = MagicMock()
        exists_result.scalar_one_or_none = MagicMock(return_value=grade_code)

        # 두 번째 호출: 기존 셀 (없음)
        cell_result = MagicMock()
        cell_result.scalar_one_or_none = MagicMock(return_value=None)

        db.execute = AsyncMock(side_effect=[exists_result, cell_result])
        db.flush = AsyncMock()
        return db

    async def test_알수없는_route_422(self):
        actor = _make_admin()
        db = MagicMock()
        db.execute = AsyncMock()
        db.flush = AsyncMock()
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
        db = MagicMock()
        db.execute = AsyncMock()
        db.flush = AsyncMock()
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
        db = self._mock_db_known_grade("sub_operator")
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
