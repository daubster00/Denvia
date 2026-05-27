"""Story 10.5 — 등급 × 페이지 접근 권한 매트릭스 서비스.

매트릭스 정의:
- 행: ADMIN_PAGE_ROUTES (9개 1차 라우트)
- 열: configurable 등급 = ('operator', 'sub_operator')  — master 는 항상 전체 ON 으로 매트릭스 제외

권한 가드 (라우터 측 require_admin_grade('master') 와 중복 방어):
- 조회: master / operator 가능 (operator 는 자기 등급이 무엇을 가졌는지 확인 가능)
- 수정: master 만 가능
- master 등급 row 자체는 본 테이블에 존재하지 않음 — INSERT/UPDATE 시 422.

업데이트는 단일 셀(UPSERT) 단위. 일괄 변경이 필요하면 프론트가 여러 번 호출.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

import structlog
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.admin_grade_page_permission import AdminGradePagePermission
from api.src.models.user import User


logger = structlog.get_logger(__name__)


# 매트릭스에 노출되는 1차 라우트와 라벨.
# - /admin/admins/* 는 본 매트릭스에서 제외 — require_admin_grade('master','operator') 단독 가드.
# - 새 페이지 추가 시 본 상수 + 0055 마이그레이션의 _DEFAULT_ROUTES 동시 갱신.
ADMIN_PAGE_ROUTES: list[tuple[str, str]] = [
    ("/admin", "대시보드"),
    ("/admin/users", "고객관리"),
    ("/admin/anomaly", "이상탐지"),
    ("/admin/content", "콘텐츠"),
    ("/admin/rag", "RAG 데이터 관리"),
    ("/admin/finance", "재무"),
    ("/admin/cs", "CS"),
    ("/admin/board", "수정요청"),
    ("/admin/settings", "설정"),
]

ADMIN_PAGE_ROUTE_SET: set[str] = {r for r, _ in ADMIN_PAGE_ROUTES}

CONFIGURABLE_GRADES: list[str] = ["operator", "sub_operator"]


GradeConfigurable = Literal["operator", "sub_operator"]


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _validate_route(page_route: str) -> None:
    if page_route not in ADMIN_PAGE_ROUTE_SET:
        raise HTTPException(
            422,
            detail={
                "code": "ADMIN_PAGE_ROUTE_UNKNOWN",
                "message": "알 수 없는 페이지 경로입니다.",
            },
        )


def _validate_grade(admin_grade: str) -> None:
    if admin_grade not in CONFIGURABLE_GRADES:
        # master 는 본 테이블의 대상이 아니다(항상 전체 접근).
        raise HTTPException(
            422,
            detail={
                "code": "ADMIN_GRADE_NOT_CONFIGURABLE",
                "message": "이 등급은 권한 설정 대상이 아닙니다.",
            },
        )


async def get_matrix(db: AsyncSession) -> dict[str, Any]:
    """현재 매트릭스 전체를 반환. 누락된 셀은 기본값(operator=true, sub_operator=false)."""
    stmt = select(AdminGradePagePermission)
    rows = (await db.execute(stmt)).scalars().all()
    by_key: dict[tuple[str, str], bool] = {
        (r.admin_grade, r.page_route): bool(r.allowed) for r in rows
    }

    result_rows: list[dict[str, Any]] = []
    for route, _label in ADMIN_PAGE_ROUTES:
        for grade in CONFIGURABLE_GRADES:
            allowed = by_key.get(
                (grade, route),
                grade == "operator",  # operator default ON, sub_operator default OFF
            )
            result_rows.append(
                {
                    "admin_grade": grade,
                    "page_route": route,
                    "allowed": allowed,
                }
            )

    return {
        "pages": [{"page_route": r, "label": label} for r, label in ADMIN_PAGE_ROUTES],
        "grades": list(CONFIGURABLE_GRADES),
        "rows": result_rows,
    }


async def upsert_permission(
    db: AsyncSession,
    *,
    actor: User,
    admin_grade: str,
    page_route: str,
    allowed: bool,
) -> dict[str, Any]:
    """단일 (등급, 페이지) 셀 UPSERT.

    Raises:
        422 ADMIN_PAGE_ROUTE_UNKNOWN / ADMIN_GRADE_NOT_CONFIGURABLE
    """
    _validate_route(page_route)
    _validate_grade(admin_grade)

    # before 값 — 없으면 default
    existing = (
        await db.execute(
            select(AdminGradePagePermission).where(
                AdminGradePagePermission.admin_grade == admin_grade,
                AdminGradePagePermission.page_route == page_route,
            )
        )
    ).scalar_one_or_none()
    before_allowed = (
        bool(existing.allowed)
        if existing is not None
        else (admin_grade == "operator")
    )

    now = _now_utc()
    stmt = pg_insert(AdminGradePagePermission).values(
        admin_grade=admin_grade,
        page_route=page_route,
        allowed=allowed,
        updated_by_admin_id=actor.id,
        created_at=now,
        updated_at=now,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["admin_grade", "page_route"],
        set_={
            "allowed": stmt.excluded.allowed,
            "updated_by_admin_id": stmt.excluded.updated_by_admin_id,
            "updated_at": now,
        },
    )
    await db.execute(stmt)
    await db.flush()

    logger.info(
        "admin.grade_permission.updated",
        actor_user_id=actor.id,
        admin_grade=admin_grade,
        page_route=page_route,
        before=before_allowed,
        after=allowed,
    )
    return {
        "row": {
            "admin_grade": admin_grade,
            "page_route": page_route,
            "allowed": allowed,
        },
        "diff": {
            "before": {"allowed": before_allowed},
            "after": {"allowed": allowed},
            "admin_grade": admin_grade,
            "page_route": page_route,
        },
    }


async def get_allowed_pages_for_admin(
    db: AsyncSession, *, admin_grade: str | None
) -> list[str]:
    """주어진 등급에 대해 허용된 ADMIN_PAGE_ROUTES 목록.

    프론트 사이드바·라우트 가드용 — /admin/auth/me 응답에 동봉된다.
    - master / NULL(레거시) → 매트릭스 전체 ON
    - operator             → 누락 셀 True(default)
    - sub_operator         → 누락 셀 False(default)
    - pending 등 그 외      → 빈 리스트
    """
    if admin_grade is None or admin_grade == "master":
        return [route for route, _ in ADMIN_PAGE_ROUTES]
    if admin_grade not in CONFIGURABLE_GRADES:
        return []

    rows = (
        await db.execute(
            select(
                AdminGradePagePermission.page_route,
                AdminGradePagePermission.allowed,
            ).where(AdminGradePagePermission.admin_grade == admin_grade)
        )
    ).all()
    by_route: dict[str, bool] = {r.page_route: bool(r.allowed) for r in rows}

    default_allowed = admin_grade == "operator"
    return [
        route
        for route, _ in ADMIN_PAGE_ROUTES
        if by_route.get(route, default_allowed)
    ]


async def is_page_allowed(
    db: AsyncSession, *, admin_grade: str, page_route: str
) -> bool:
    """deps.auth.require_admin_page 가 호출하는 단건 조회.

    - master           → True (본 함수는 호출되지 않지만 방어)
    - operator         → admin_grade_page_permissions 조회. 누락 셀은 True(default).
    - sub_operator     → 조회. 누락 셀은 False(default).
    - 그 외(pending 등) → False
    """
    if admin_grade == "master":
        return True
    if admin_grade not in CONFIGURABLE_GRADES:
        return False
    if page_route not in ADMIN_PAGE_ROUTE_SET:
        # 매트릭스 대상이 아닌 경로는 별도 grade 가드(require_admin_grade)에 위임 — 통과.
        return True
    row = (
        await db.execute(
            select(AdminGradePagePermission.allowed).where(
                AdminGradePagePermission.admin_grade == admin_grade,
                AdminGradePagePermission.page_route == page_route,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return admin_grade == "operator"
    return bool(row)


__all__ = [
    "ADMIN_PAGE_ROUTES",
    "ADMIN_PAGE_ROUTE_SET",
    "CONFIGURABLE_GRADES",
    "GradeConfigurable",
    "get_allowed_pages_for_admin",
    "get_matrix",
    "is_page_allowed",
    "upsert_permission",
]
