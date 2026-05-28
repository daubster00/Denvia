"""관리자 등급 CRUD 서비스 (0057 도입).

엔드포인트:
- GET    /api/v1/admin/grades              — 전체 등급 목록(내장 + 커스텀)
- POST   /api/v1/admin/grades              — 커스텀 등급 추가 (label 만 입력)
- DELETE /api/v1/admin/grades/{code}       — 커스텀 등급 삭제 (해당 등급 사용자 0명일 때만)

규칙:
- 내장 4종(master/operator/sub_operator/pending) 은 추가·삭제·라벨 변경 불가.
- label 중복 차단(공백·대소문자 정규화 비교).
- 'operator' 등 내장 라벨/유사 라벨 차단.
- 커스텀 등급 추가 시 admin_grade_page_permissions 에 모든 라우트 allowed=false 시드.
- 삭제 시 해당 코드 사용자가 있으면 409 (DB FK ON DELETE RESTRICT 도 동일 가드).
"""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.admin_grade import AdminGrade
from api.src.models.admin_grade_page_permission import AdminGradePagePermission
from api.src.models.user import User
from api.src.services.admin_grade_permission_service import ADMIN_PAGE_ROUTES


logger = structlog.get_logger(__name__)


# 신규 코드/라벨이 이 값과 충돌하면 거부.
# sub_operator 는 커스텀 등급으로 취급(2026-05-28 정책) — 예약 목록에서 제외.
RESERVED_CODES: set[str] = {"master", "operator", "pending"}

# 예약 라벨(정규화된 비교용) — 신규 라벨 입력이 이와 충돌하면 거부.
# 정규화는 _normalize_label 참조(공백 제거 + 소문자).
_RESERVED_LABEL_NORMS: set[str] = {
    "마스터",
    "운영관리자",
    "승인대기",
    "master",
    "operator",
    "pending",
    "admin",
}

# 등급 관리 페이지·등급 변경 모달에서 항상 숨기는 코드.
# master 는 개발자 단일 백본 — 운영자에게 노출하지 않는다.
_HIDDEN_FROM_LIST: set[str] = {"master"}

_LABEL_MAX_LEN = 32
_LABEL_MIN_LEN = 1


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _normalize_label(label: str) -> str:
    """중복 비교용 정규화 — 모든 공백 제거 + 소문자."""
    return re.sub(r"\s+", "", label or "").lower()


def _generate_code(db_codes: set[str]) -> str:
    """커스텀 등급 코드 생성 — g_<8 hex>. 충돌 시 재생성(최대 5회)."""
    for _ in range(5):
        candidate = f"g_{secrets.token_hex(4)}"
        if candidate not in db_codes:
            return candidate
    raise HTTPException(
        500,
        detail={
            "code": "ADMIN_GRADE_CODE_GEN_FAILED",
            "message": "등급 코드 생성에 실패했습니다. 다시 시도해주세요.",
        },
    )


async def list_grades(db: AsyncSession) -> list[dict[str, Any]]:
    """전체 등급 — 내장(고정 순서) → 커스텀(생성 순) + 각 등급의 사용자 수.

    master 는 응답에서 제외(_HIDDEN_FROM_LIST).
    pending 은 표시되지만 운영자가 직접 부여하는 등급은 아님 — 프론트 모달에서 별도 처리.
    """
    grade_rows = [
        r
        for r in (await db.execute(select(AdminGrade))).scalars().all()
        if r.code not in _HIDDEN_FROM_LIST
    ]

    counts_stmt = (
        select(User.admin_grade, func.count())
        .where(User.role == "admin", User.withdrawn_at.is_(None))
        .group_by(User.admin_grade)
    )
    counts: dict[str, int] = {
        (g or ""): int(n) for g, n in (await db.execute(counts_stmt)).all()
    }

    def _rank(code: str) -> int:
        order = {"master": 1, "operator": 2, "sub_operator": 3, "pending": 4}
        return order.get(code, 5)

    sorted_rows = sorted(
        grade_rows,
        key=lambda r: (_rank(r.code), r.created_at or _now_utc()),
    )
    return [
        {
            "code": r.code,
            "label": r.label,
            "is_builtin": bool(r.is_builtin),
            "user_count": counts.get(r.code, 0),
            "created_at": r.created_at,
        }
        for r in sorted_rows
    ]


async def create_grade(
    db: AsyncSession,
    *,
    actor: User,
    label: str,
) -> dict[str, Any]:
    """커스텀 등급 추가.

    Raises:
        422 ADMIN_GRADE_LABEL_INVALID    — 빈 문자열·과길이
        422 ADMIN_GRADE_LABEL_RESERVED   — 내장 등급 라벨과 충돌
        409 ADMIN_GRADE_LABEL_DUPLICATE  — DB 에 동일(정규화) 라벨 존재
    """
    label_clean = (label or "").strip()
    if not label_clean or len(label_clean) > _LABEL_MAX_LEN:
        raise HTTPException(
            422,
            detail={
                "code": "ADMIN_GRADE_LABEL_INVALID",
                "message": f"등급 이름은 {_LABEL_MIN_LEN}~{_LABEL_MAX_LEN}자 이내로 입력해주세요.",
            },
        )

    norm = _normalize_label(label_clean)
    if norm in _RESERVED_LABEL_NORMS:
        raise HTTPException(
            422,
            detail={
                "code": "ADMIN_GRADE_LABEL_RESERVED",
                "message": "이 이름은 예약되어 있어 사용할 수 없습니다.",
            },
        )

    existing_rows = (await db.execute(select(AdminGrade))).scalars().all()
    existing_codes = {r.code for r in existing_rows}
    for r in existing_rows:
        if _normalize_label(r.label) == norm:
            raise HTTPException(
                409,
                detail={
                    "code": "ADMIN_GRADE_LABEL_DUPLICATE",
                    "message": "이미 같은 이름의 등급이 존재합니다.",
                },
            )

    code = _generate_code(existing_codes)
    now = _now_utc()
    grade = AdminGrade(
        code=code,
        label=label_clean,
        is_builtin=False,
        created_by_admin_id=actor.id,
        created_at=now,
        updated_at=now,
    )
    db.add(grade)
    await db.flush()

    # 매트릭스 시드 — 9개 라우트 × allowed=false (sub_operator 기본값과 동일).
    for route, _ in ADMIN_PAGE_ROUTES:
        db.add(
            AdminGradePagePermission(
                admin_grade=code,
                page_route=route,
                allowed=False,
                updated_by_admin_id=actor.id,
                created_at=now,
                updated_at=now,
            )
        )
    await db.flush()

    logger.info(
        "admin.grade.created",
        actor_user_id=actor.id,
        grade_code=code,
        grade_label=label_clean,
    )
    return {
        "row": {
            "code": code,
            "label": label_clean,
            "is_builtin": False,
            "user_count": 0,
            "created_at": now,
        },
        "diff": {
            "before": None,
            "after": {"code": code, "label": label_clean},
        },
    }


async def delete_grade(
    db: AsyncSession,
    *,
    actor: User,
    code: str,
) -> dict[str, Any]:
    """커스텀 등급 삭제.

    Raises:
        404 ADMIN_GRADE_NOT_FOUND
        403 ADMIN_GRADE_BUILTIN_PROTECTED — 내장 등급 삭제 시도
        409 ADMIN_GRADE_IN_USE            — 해당 등급 사용자 1명 이상
    """
    grade = (
        await db.execute(select(AdminGrade).where(AdminGrade.code == code))
    ).scalar_one_or_none()
    if grade is None:
        raise HTTPException(
            404,
            detail={
                "code": "ADMIN_GRADE_NOT_FOUND",
                "message": "등급을 찾을 수 없습니다.",
            },
        )
    if grade.is_builtin:
        raise HTTPException(
            403,
            detail={
                "code": "ADMIN_GRADE_BUILTIN_PROTECTED",
                "message": "내장 등급은 삭제할 수 없습니다.",
            },
        )

    active_count = (
        await db.execute(
            select(func.count()).where(
                User.role == "admin",
                User.withdrawn_at.is_(None),
                User.admin_grade == code,
            )
        )
    ).scalar() or 0
    if int(active_count) > 0:
        raise HTTPException(
            409,
            detail={
                "code": "ADMIN_GRADE_IN_USE",
                "message": (
                    f"이 등급을 사용 중인 관리자가 {int(active_count)}명 있습니다. "
                    "먼저 등급을 변경한 뒤 삭제해주세요."
                ),
            },
        )

    # 탈퇴(소프트 삭제) 관리자가 본 등급을 들고 있으면 FK 가 막힌다.
    # withdrawn_at 가 셋된 관리자는 로그인 불가 상태이므로 admin_grade 를 NULL 로
    # 풀어 FK 참조를 해제한 뒤 등급을 삭제한다.
    await db.execute(
        update(User)
        .where(
            User.role == "admin",
            User.withdrawn_at.is_not(None),
            User.admin_grade == code,
        )
        .values(admin_grade=None)
    )

    before = {"code": grade.code, "label": grade.label}
    await db.delete(grade)
    # admin_grade_page_permissions 의 매트릭스 행은 FK ON DELETE CASCADE 로 자동 정리.
    await db.flush()

    logger.info(
        "admin.grade.deleted",
        actor_user_id=actor.id,
        grade_code=code,
    )
    return {
        "diff": {"before": before, "after": None},
    }


__all__ = [
    "RESERVED_CODES",
    "create_grade",
    "delete_grade",
    "list_grades",
]
