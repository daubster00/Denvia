"""Story 10.1 / 10.5 — RBAC 의존성 단위 테스트.

검증 대상:
1) get_current_admin 이 admin_grade=='pending' 사용자를 401 ADMIN_PENDING_APPROVAL 로 차단
2) require_admin_grade('master') 가 operator 등급에게 403 ADMIN_FORBIDDEN_GRADE 반환
3) require_admin_page('/admin/finance') 가
   - master           → 통과
   - operator + 허용  → 통과 / 미허용 → 403
   - sub_operator     → 등급 매트릭스 조회 결과대로
4) require_admin_grade — admin_grade NULL(레거시 백필 누락)은 통과
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest
from fastapi import HTTPException

from api.src.deps.auth import (
    get_current_admin,
    require_admin_grade,
    require_admin_page,
)
from api.src.settings import settings


def _make_admin_jwt(user_id: int = 99) -> str:
    payload = {
        "sub": str(user_id),
        "aud": "denvia-admin",
        "exp": int(time.time()) + 3600,
    }
    return pyjwt.encode(
        payload, settings.denvia_jwt_secret, algorithm=settings.denvia_jwt_algorithm
    )


def _make_admin_user(grade: str | None = "operator") -> MagicMock:
    user = MagicMock()
    user.id = 99
    user.email = "admin@denvia.local"
    user.role = "admin"
    user.subscription_status = "free"
    user.withdrawn_at = None
    user.admin_grade = grade
    return user


class TestGetCurrentAdminPending:
    async def test_pending_등급_관리자는_401_ADMIN_PENDING_APPROVAL(self):
        token = _make_admin_jwt(user_id=99)
        user = _make_admin_user(grade="pending")
        db = MagicMock()

        with patch(
            "api.src.deps.auth.get_user_by_id",
            new=AsyncMock(return_value=user),
        ):
            with pytest.raises(HTTPException) as exc:
                await get_current_admin(denvia_admin_session=token, db=db)

        assert exc.value.status_code == 401
        assert exc.value.detail["code"] == "ADMIN_PENDING_APPROVAL"

    async def test_operator_등급은_통과(self):
        token = _make_admin_jwt(user_id=99)
        user = _make_admin_user(grade="operator")
        db = MagicMock()

        with patch(
            "api.src.deps.auth.get_user_by_id",
            new=AsyncMock(return_value=user),
        ):
            result = await get_current_admin(denvia_admin_session=token, db=db)

        assert result is user

    async def test_admin_grade_NULL_레거시는_통과(self):
        """백필 누락된 레거시 admin(admin_grade=NULL)은 정상 통과 — Story 10.3에서 정리."""
        token = _make_admin_jwt(user_id=99)
        user = _make_admin_user(grade=None)
        db = MagicMock()

        with patch(
            "api.src.deps.auth.get_user_by_id",
            new=AsyncMock(return_value=user),
        ):
            result = await get_current_admin(denvia_admin_session=token, db=db)

        assert result is user


class TestRequireAdminGrade:
    async def test_operator_가_master_전용_의존성_접근시_403(self):
        user = _make_admin_user(grade="operator")
        checker = require_admin_grade("master")

        with pytest.raises(HTTPException) as exc:
            await checker(admin=user)

        assert exc.value.status_code == 403
        assert exc.value.detail["code"] == "ADMIN_FORBIDDEN_GRADE"

    async def test_master_는_master_전용_의존성_통과(self):
        user = _make_admin_user(grade="master")
        checker = require_admin_grade("master")

        result = await checker(admin=user)
        assert result is user

    async def test_master_operator_혼합_허용_의존성_operator_통과(self):
        user = _make_admin_user(grade="operator")
        checker = require_admin_grade("master", "operator")

        result = await checker(admin=user)
        assert result is user

    async def test_sub_operator_가_master_operator_전용_접근시_403(self):
        user = _make_admin_user(grade="sub_operator")
        checker = require_admin_grade("master", "operator")

        with pytest.raises(HTTPException) as exc:
            await checker(admin=user)

        assert exc.value.status_code == 403
        assert exc.value.detail["code"] == "ADMIN_FORBIDDEN_GRADE"

    async def test_admin_grade_NULL_은_백필_누락으로_보고_통과(self):
        """Story 10.3에서 정리되기 전까지 NULL 은 통과."""
        user = _make_admin_user(grade=None)
        checker = require_admin_grade("master")

        result = await checker(admin=user)
        assert result is user


class TestRequireAdminPage:
    """Story 10.5 — 등급 × 페이지 매트릭스. is_page_allowed 서비스 함수를 mock."""

    def _patch_is_allowed(self, allowed: bool):
        return patch(
            "api.src.services.admin_grade_permission_service.is_page_allowed",
            new=AsyncMock(return_value=allowed),
        )

    async def test_master_는_매트릭스_미적용_통과(self):
        user = _make_admin_user(grade="master")
        checker = require_admin_page("/admin/finance")
        db = MagicMock()

        with self._patch_is_allowed(allowed=False):  # master 는 service 호출 자체 안 함
            result = await checker(admin=user, db=db)
        assert result is user

    async def test_operator_허용시_통과(self):
        user = _make_admin_user(grade="operator")
        checker = require_admin_page("/admin/finance")
        db = MagicMock()

        with self._patch_is_allowed(allowed=True):
            result = await checker(admin=user, db=db)
        assert result is user

    async def test_operator_미허용시_403(self):
        user = _make_admin_user(grade="operator")
        checker = require_admin_page("/admin/finance")
        db = MagicMock()

        with self._patch_is_allowed(allowed=False):
            with pytest.raises(HTTPException) as exc:
                await checker(admin=user, db=db)

        assert exc.value.status_code == 403
        assert exc.value.detail["code"] == "ADMIN_FORBIDDEN_PAGE"

    async def test_sub_operator_허용된_페이지_통과(self):
        user = _make_admin_user(grade="sub_operator")
        checker = require_admin_page("/admin/finance")
        db = MagicMock()

        with self._patch_is_allowed(allowed=True):
            result = await checker(admin=user, db=db)
        assert result is user

    async def test_sub_operator_미허용_페이지_403(self):
        user = _make_admin_user(grade="sub_operator")
        checker = require_admin_page("/admin/finance")
        db = MagicMock()

        with self._patch_is_allowed(allowed=False):
            with pytest.raises(HTTPException) as exc:
                await checker(admin=user, db=db)

        assert exc.value.status_code == 403
        assert exc.value.detail["code"] == "ADMIN_FORBIDDEN_PAGE"
