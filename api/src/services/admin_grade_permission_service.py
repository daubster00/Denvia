"""Story 10.5 — 등급 × 페이지 접근 권한 매트릭스 서비스.

매트릭스 정의:
- 행: ADMIN_PAGE_ROUTES (9개 1차 라우트)
- 열: configurable 등급 = master/pending 을 제외한 모든 admin_grades 행
       (내장: operator/sub_operator + 0057 이후 커스텀 등급)
- master 는 항상 전체 ON, pending 은 매트릭스 외부에서 401 차단이라 모두 매트릭스 미포함.

권한 가드 (라우터 측 require_admin_grade('master','operator') 와 중복 방어):
- 조회 / 수정: master / operator 둘 다 가능 (2026-05-28 SSOT — 운영자가 본인 등급 매트릭스도 직접 조정).

업데이트는 단일 셀(UPSERT) 단위. 일괄 변경이 필요하면 프론트가 여러 번 호출.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.admin_grade import AdminGrade
from api.src.models.admin_grade_page_permission import AdminGradePagePermission
from api.src.models.user import User


logger = structlog.get_logger(__name__)


# 매트릭스에 노출되는 1차 라우트와 라벨.
# - /admin/admins/* 는 본 매트릭스에서 제외 — require_admin_grade('master','operator') 단독 가드.
# - 새 페이지 추가 시 본 상수 + 0055 마이그레이션의 _DEFAULT_ROUTES 동시 갱신.
# - "/admin/feature/*" 는 실제 페이지가 아니라 상단바·기타 UI 기능의 노출 토글 자리.
#   매트릭스 한 행을 차지해 등급별 ON/OFF 만 컨트롤하고, 라우팅 가드는 사용하지 않는다.
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
    ("/admin/feature/openai-warmup", "AI 워밍업 (상단바 토글)"),
]

ADMIN_PAGE_ROUTE_SET: set[str] = {r for r, _ in ADMIN_PAGE_ROUTES}

# 매트릭스에서 항상 제외되는 등급 — master 는 전체 ON, pending 은 차단.
_GRADES_NOT_CONFIGURABLE: set[str] = {"master", "pending"}


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


async def _fetch_configurable_grades(db: AsyncSession) -> list[dict[str, Any]]:
    """매트릭스 노출 등급(master/pending 제외) — admin_grades 메타에서 동적 조회."""
    rows = (await db.execute(select(AdminGrade))).scalars().all()

    def _rank(r: AdminGrade) -> tuple[int, datetime]:
        # operator → sub_operator → 커스텀(생성순)
        order = {"operator": 1, "sub_operator": 2}
        return (order.get(r.code, 3), r.created_at or _now_utc())

    return [
        {"code": r.code, "label": r.label, "is_builtin": bool(r.is_builtin)}
        for r in sorted(rows, key=_rank)
        if r.code not in _GRADES_NOT_CONFIGURABLE
    ]


async def _validate_grade_configurable(db: AsyncSession, admin_grade: str) -> None:
    if admin_grade in _GRADES_NOT_CONFIGURABLE:
        raise HTTPException(
            422,
            detail={
                "code": "ADMIN_GRADE_NOT_CONFIGURABLE",
                "message": "이 등급은 권한 설정 대상이 아닙니다.",
            },
        )
    exists = (
        await db.execute(select(AdminGrade.code).where(AdminGrade.code == admin_grade))
    ).scalar_one_or_none()
    if exists is None:
        raise HTTPException(
            422,
            detail={
                "code": "ADMIN_GRADE_UNKNOWN",
                "message": "알 수 없는 등급입니다.",
            },
        )


async def get_matrix(db: AsyncSession) -> dict[str, Any]:
    """현재 매트릭스 전체를 반환. 누락 셀은 기본값(operator=true, 그 외=false)."""
    configurable = await _fetch_configurable_grades(db)
    stmt = select(AdminGradePagePermission)
    rows = (await db.execute(stmt)).scalars().all()
    by_key: dict[tuple[str, str], bool] = {
        (r.admin_grade, r.page_route): bool(r.allowed) for r in rows
    }

    result_rows: list[dict[str, Any]] = []
    for route, _label in ADMIN_PAGE_ROUTES:
        for grade_meta in configurable:
            code = grade_meta["code"]
            allowed = by_key.get(
                (code, route),
                code == "operator",  # operator default ON, 그 외 default OFF
            )
            result_rows.append(
                {
                    "admin_grade": code,
                    "page_route": route,
                    "allowed": allowed,
                }
            )

    return {
        "pages": [{"page_route": r, "label": label} for r, label in ADMIN_PAGE_ROUTES],
        "grades": [g["code"] for g in configurable],
        "grade_meta": configurable,
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
        422 ADMIN_PAGE_ROUTE_UNKNOWN / ADMIN_GRADE_NOT_CONFIGURABLE / ADMIN_GRADE_UNKNOWN
    """
    _validate_route(page_route)
    await _validate_grade_configurable(db, admin_grade)

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
    - pending              → 빈 리스트 (등급 가드에서 401)
    - operator             → 매트릭스 조회, 누락 셀 True(default)
    - sub_operator/커스텀  → 매트릭스 조회, 누락 셀 False(default)
    """
    if admin_grade is None or admin_grade == "master":
        return [route for route, _ in ADMIN_PAGE_ROUTES]
    if admin_grade in _GRADES_NOT_CONFIGURABLE:
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

    - master                  → True (본 함수는 호출되지 않지만 방어)
    - pending                 → False
    - operator                → 매트릭스 조회. 누락 셀 True(default).
    - sub_operator/커스텀     → 매트릭스 조회. 누락 셀 False(default).
    - 매트릭스 외 등급(미상)  → False
    """
    if admin_grade == "master":
        return True
    if admin_grade in _GRADES_NOT_CONFIGURABLE:
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
    "get_allowed_pages_for_admin",
    "get_matrix",
    "is_page_allowed",
    "upsert_permission",
]
