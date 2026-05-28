"""Story 10.3 — 관리자 계정 관리 서비스 (CRUD + 등급 제약).

엔드포인트와 1:1 매핑:
- list_admins         → GET    /api/v1/admin/accounts
- approve_pending     → POST   /api/v1/admin/accounts/{id}/approve
- block_admin         → POST   /api/v1/admin/accounts/{id}/block
- unblock_admin       → POST   /api/v1/admin/accounts/{id}/unblock
- delete_admin        → DELETE /api/v1/admin/accounts/{id}
- update_admin_grade  → PATCH  /api/v1/admin/accounts/{id}

핵심 가드 (2026-05-28 SSOT 갱신 — master 는 개발자 전용이라 운영 가드에서 분리):
1) 자기 자신 액션 금지         → 403 ADMIN_SELF_ACTION_FORBIDDEN
2) master 행 변경 금지(누구든) → 403 ADMIN_MASTER_PROTECTED
3) 'master' 등급은 누구도 신규 부여 불가 → 422 ADMIN_MASTER_UNIQUE_VIOLATION
   (operator 끼리는 서로 등급 변경/차단/삭제 가능 — master 가 운영에 개입 안 함)

알림톡 발송 없음 (2026-05-27 폐기) — 대상자에게는 운영자가 직접 통보.
audit_logs INSERT 는 라우터의 request.state.audit_* 를 AuditMiddleware 가 응답 직후 처리.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

import structlog
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.user import User

logger = structlog.get_logger(__name__)


# 등급 라벨 — 응답 + 알림톡 본문에 노출.
GRADE_LABELS: dict[str, str] = {
    "master": "마스터",
    "operator": "운영 관리자",
    "sub_operator": "부운영자",
    "pending": "승인대기",
}

# 정렬 우선순위 — master → operator → sub_operator → pending.
_GRADE_SORT_RANK: dict[str, int] = {
    "master": 1,
    "operator": 2,
    "sub_operator": 3,
    "pending": 4,
}

ListFilter = Literal["all", "pending", "active", "blocked"]


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _mask_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) < 8:
        return phone
    if len(digits) == 11:  # 010XXXXYYYY
        return f"{digits[:3]}-****-{digits[-4:]}"
    if len(digits) == 10:  # 02XXXXYYYY 등 (관리자에는 거의 없음)
        return f"{digits[:2]}-****-{digits[-4:]}"
    return f"{digits[:3]}-****-{digits[-4:]}"


# ── 권한 가드 ────────────────────────────────────────────────────────────────


def _is_active_admin(actor: User) -> None:
    """라우터 진입 deps 가 이미 검증하지만 방어용 — pending/withdrawn 등 통과 금지."""
    if actor.role != "admin":
        raise HTTPException(403, detail={"code": "ADMIN_FORBIDDEN_GRADE", "message": "권한이 부족합니다."})
    if getattr(actor, "admin_grade", None) == "pending":
        raise HTTPException(401, detail={"code": "ADMIN_PENDING_APPROVAL", "message": "관리자 승인 대기 중입니다."})


def _guard_self_action(actor: User, target: User) -> None:
    if actor.id == target.id:
        raise HTTPException(
            403,
            detail={
                "code": "ADMIN_SELF_ACTION_FORBIDDEN",
                "message": "본인 계정은 본 페이지에서 관리할 수 없습니다.",
            },
        )


def _guard_master_target(target: User) -> None:
    """대상이 master 등급이면 어떤 액션도 거부 — FR63 단일성 보호."""
    if getattr(target, "admin_grade", None) == "master":
        raise HTTPException(
            403,
            detail={
                "code": "ADMIN_MASTER_PROTECTED",
                "message": "마스터 계정은 보호되어 있습니다.",
            },
        )


def _guard_operator_hierarchy(actor: User, target: User) -> None:
    """master 행 보호는 _guard_master_target 가 담당. operator 끼리는 서로 관리 가능.

    2026-05-28 SSOT 갱신 — master 는 개발자 전용 계정으로 운영 관여 안 함.
    실제 운영 주체는 operator. operator 가 다른 operator 의 등급/차단/삭제를
    수행할 수 있어야 휴가·이양·업무 분담이 가능 (master 가 안 끼게).
    """
    # 본 가드는 master 행 보호와 자기 자신 보호만 남기고, operator hierarchy 는 없음.
    # (호출 측에서 _guard_self_action / _guard_master_target 가 별도로 처리)
    return


def _guard_grade_assignment(actor: User, target_grade: str) -> None:
    """등급 변경/승인 시 부여 가능한 등급인지 검증.

    - master 부여는 누구도 불가 (FR63 — partial UNIQUE 가 DB 차원에서도 막지만 메시지 친화적으로 먼저 거부).
    - operator / sub_operator / pending 부여는 master / operator 모두 가능 (2026-05-28 SSOT 갱신).
    """
    if target_grade == "master":
        raise HTTPException(
            422,
            detail={
                "code": "ADMIN_MASTER_UNIQUE_VIOLATION",
                "message": "마스터 등급은 새로 부여할 수 없습니다.",
            },
        )
    if target_grade not in ("operator", "sub_operator", "pending"):
        # pending 으로 회귀시키는 변경은 운영상 필요할 수 있어 허용.
        raise HTTPException(
            422,
            detail={
                "code": "ADMIN_GRADE_NOT_ALLOWED",
                "message": "이 등급은 부여 권한이 없습니다.",
            },
        )


async def _get_target_or_404(db: AsyncSession, user_id: int) -> User:
    target = (
        await db.execute(
            select(User).where(User.id == user_id, User.role == "admin")
        )
    ).scalar_one_or_none()
    if target is None or target.withdrawn_at is not None:
        raise HTTPException(
            404,
            detail={
                "code": "ADMIN_ACCOUNT_NOT_FOUND",
                "message": "관리자 계정을 찾을 수 없습니다.",
            },
        )
    return target


# ── 조회 ──────────────────────────────────────────────────────────────────────


def _serialize(row: User) -> dict[str, Any]:
    grade = getattr(row, "admin_grade", None) or "pending"
    return {
        "id": row.id,
        "email": row.email,
        "admin_grade": grade,
        "grade_label": GRADE_LABELS.get(grade, grade),
        "phone_masked": _mask_phone(row.phone),
        "admin_blocked_until": row.admin_blocked_until,
        "admin_block_reason": row.admin_block_reason,
        "admin_signup_at": row.admin_signup_at,
        "last_login_at": row.last_login_at,
        "created_at": row.created_at,
    }


async def list_admins(
    db: AsyncSession,
    *,
    actor: User,
    list_filter: ListFilter = "all",
) -> list[dict[str, Any]]:
    """전체 관리자 목록.

    - master 등급은 응답에서 항상 제외(요청: 관리자 항목에 마스터 비노출).
      본인이 master 인 경우 자기 계정 관리는 /admin/account 에서 수행.
    - 정렬: admin_grade ASC(_GRADE_SORT_RANK) → created_at DESC.
    """
    _is_active_admin(actor)
    stmt = select(User).where(
        User.role == "admin",
        User.withdrawn_at.is_(None),
        User.admin_grade != "master",
    )
    now = _now_utc()
    if list_filter == "pending":
        stmt = stmt.where(User.admin_grade == "pending")
    elif list_filter == "blocked":
        stmt = stmt.where(
            User.admin_blocked_until.is_not(None),
            User.admin_blocked_until > now,
        )
    elif list_filter == "active":
        stmt = stmt.where(
            User.admin_grade != "pending",
            (User.admin_blocked_until.is_(None)) | (User.admin_blocked_until <= now),
        )
    rows = (await db.execute(stmt)).scalars().all()

    def _rank(u: User) -> tuple[int, datetime]:
        rank = _GRADE_SORT_RANK.get(getattr(u, "admin_grade", None) or "pending", 99)
        return (rank, -(u.created_at.timestamp() if u.created_at else 0))

    rows_sorted = sorted(rows, key=_rank)
    return [_serialize(r) for r in rows_sorted]


# ── 액션 함수 ────────────────────────────────────────────────────────────────


async def approve_pending(
    db: AsyncSession,
    *,
    actor: User,
    target_user_id: int,
    target_grade: str,
) -> dict[str, Any]:
    """pending → sub_operator 또는 operator 로 승격.

    Raises:
        404 ADMIN_ACCOUNT_NOT_FOUND
        403 ADMIN_SELF_ACTION_FORBIDDEN
        422 ADMIN_GRADE_NOT_ALLOWED  / ADMIN_MASTER_UNIQUE_VIOLATION
        409 ADMIN_ACCOUNT_NOT_PENDING
    """
    _is_active_admin(actor)
    target = await _get_target_or_404(db, target_user_id)
    _guard_self_action(actor, target)
    _guard_grade_assignment(actor, target_grade)

    if getattr(target, "admin_grade", None) != "pending":
        raise HTTPException(
            409,
            detail={
                "code": "ADMIN_ACCOUNT_NOT_PENDING",
                "message": "이미 승인 처리된 계정입니다.",
            },
        )

    before_grade = target.admin_grade
    target.admin_grade = target_grade
    target.updated_at = _now_utc()
    await db.flush()

    logger.info(
        "admin.account.approved",
        actor_user_id=actor.id,
        target_user_id=target.id,
        target_grade=target_grade,
    )
    return {
        "diff": {"before": {"admin_grade": before_grade}, "after": {"admin_grade": target_grade}},
        "row": _serialize(target),
    }


async def block_admin(
    db: AsyncSession,
    *,
    actor: User,
    target_user_id: int,
    blocked_until: datetime,
    reason: str,
) -> dict[str, Any]:
    _is_active_admin(actor)
    target = await _get_target_or_404(db, target_user_id)
    _guard_self_action(actor, target)
    _guard_master_target(target)
    _guard_operator_hierarchy(actor, target)

    if blocked_until.tzinfo is None:
        blocked_until = blocked_until.replace(tzinfo=timezone.utc)
    if blocked_until <= _now_utc():
        raise HTTPException(
            422,
            detail={
                "code": "ADMIN_BLOCK_UNTIL_INVALID",
                "message": "차단 만료 시각이 현재보다 이후여야 합니다.",
            },
        )
    reason_clean = (reason or "").strip()
    if not reason_clean:
        raise HTTPException(
            422,
            detail={"code": "ADMIN_BLOCK_REASON_REQUIRED", "message": "차단 사유를 입력해주세요."},
        )

    before = {
        "admin_blocked_until": target.admin_blocked_until.isoformat() if target.admin_blocked_until else None,
        "admin_block_reason": target.admin_block_reason,
    }
    target.admin_blocked_until = blocked_until
    target.admin_block_reason = reason_clean
    target.updated_at = _now_utc()
    await db.flush()

    logger.info(
        "admin.account.blocked",
        actor_user_id=actor.id,
        target_user_id=target.id,
        blocked_until=blocked_until.isoformat(),
    )
    return {
        "diff": {
            "before": before,
            "after": {
                "admin_blocked_until": blocked_until.isoformat(),
                "admin_block_reason": reason_clean,
            },
        },
        "row": _serialize(target),
    }


async def unblock_admin(
    db: AsyncSession,
    *,
    actor: User,
    target_user_id: int,
) -> dict[str, Any]:
    _is_active_admin(actor)
    target = await _get_target_or_404(db, target_user_id)
    _guard_self_action(actor, target)
    _guard_master_target(target)
    _guard_operator_hierarchy(actor, target)

    if target.admin_blocked_until is None:
        raise HTTPException(
            409,
            detail={
                "code": "ADMIN_ACCOUNT_NOT_BLOCKED",
                "message": "차단 상태가 아닙니다.",
            },
        )

    before = {
        "admin_blocked_until": target.admin_blocked_until.isoformat() if target.admin_blocked_until else None,
        "admin_block_reason": target.admin_block_reason,
    }
    target.admin_blocked_until = None
    target.admin_block_reason = None
    target.updated_at = _now_utc()
    await db.flush()

    logger.info(
        "admin.account.unblocked",
        actor_user_id=actor.id,
        target_user_id=target.id,
    )
    return {
        "diff": {"before": before, "after": {"admin_blocked_until": None, "admin_block_reason": None}},
        "row": _serialize(target),
    }


async def delete_admin(
    db: AsyncSession,
    *,
    actor: User,
    target_user_id: int,
) -> dict[str, Any]:
    """소프트 삭제 — withdrawn_at=NOW(). 등급별 권한 매트릭스(admin_grade_page_permissions)는 등급 단위라 별도 정리 불필요."""
    _is_active_admin(actor)
    target = await _get_target_or_404(db, target_user_id)
    _guard_self_action(actor, target)
    _guard_master_target(target)
    _guard_operator_hierarchy(actor, target)

    now = _now_utc()
    before = {
        "withdrawn_at": None,
        "admin_grade": target.admin_grade,
    }
    target.withdrawn_at = now
    target.updated_at = now
    # 단일 세션 nonce 도 갈아엎어 기존 admin 쿠키 즉시 무효화.
    target.current_session_id = None
    await db.flush()

    logger.info(
        "admin.account.deleted",
        actor_user_id=actor.id,
        target_user_id=target.id,
    )
    return {
        "diff": {"before": before, "after": {"withdrawn_at": now.isoformat()}},
        "row": _serialize(target),
    }


async def update_admin_grade(
    db: AsyncSession,
    *,
    actor: User,
    target_user_id: int,
    new_grade: str,
) -> dict[str, Any]:
    """등급 변경 — pending 회귀·sub_operator↔operator 승강."""
    _is_active_admin(actor)
    target = await _get_target_or_404(db, target_user_id)
    _guard_self_action(actor, target)
    _guard_master_target(target)
    _guard_operator_hierarchy(actor, target)
    _guard_grade_assignment(actor, new_grade)

    before_grade = target.admin_grade
    if before_grade == new_grade:
        raise HTTPException(
            409,
            detail={"code": "ADMIN_GRADE_UNCHANGED", "message": "동일한 등급입니다."},
        )

    target.admin_grade = new_grade
    target.updated_at = _now_utc()
    await db.flush()

    logger.info(
        "admin.account.grade_updated",
        actor_user_id=actor.id,
        target_user_id=target.id,
        before=before_grade,
        after=new_grade,
    )
    return {
        "diff": {"before": {"admin_grade": before_grade}, "after": {"admin_grade": new_grade}},
        "row": _serialize(target),
    }


# ── Celery Beat: admin_blocked_until 자동 만료 해제 (Story 10.3 AC 차단 만료) ─────


async def expire_admin_blocks(
    db: AsyncSession,
    *,
    system_actor_id: int,
) -> dict[str, Any]:
    """admin_blocked_until <= NOW() 인 관리자 일괄 해제.

    audit_logs 는 호출 측(workers/anomaly_tasks)에서 actor_user_id=system_actor_id 로 기록.
    알림톡 발송 없음(2026-05-27 폐기) — 운영자가 사후 인지.
    `system_actor_id` 인자는 호출 측 시그니처 호환을 위해 유지(현재 본 함수에서는 미사용).
    """
    del system_actor_id  # 호출 측 시그니처 호환 — 본 함수 내에서는 사용 안 함
    now = _now_utc()
    rows = (
        await db.execute(
            select(User).where(
                User.role == "admin",
                User.withdrawn_at.is_(None),
                User.admin_blocked_until.is_not(None),
                User.admin_blocked_until <= now,
            )
        )
    ).scalars().all()
    if not rows:
        return {"expired_count": 0, "expired_ids": []}

    expired_ids: list[int] = []
    for row in rows:
        row.admin_blocked_until = None
        row.admin_block_reason = None
        row.updated_at = now
        expired_ids.append(row.id)
    return {"expired_count": len(expired_ids), "expired_ids": expired_ids}


# ── 캐논 라벨 함수 (BTMDESIGN_EMAIL 하드코딩 대체) ───────────────────────────


def grade_label_for_user(user: User) -> tuple[bool, str]:
    """admin_grade 기반 마스터 여부 + 표시 라벨.

    role='admin' 이 아닌 사용자는 (False, '관리자')를 반환(방어).
    admin_grade NULL(레거시 백필 미적용) 도 (False, '관리자') 처리.
    """
    grade = getattr(user, "admin_grade", None)
    is_master = grade == "master"
    label = GRADE_LABELS.get(grade or "operator", "관리자")
    return is_master, label


async def count_admins_by_grade(db: AsyncSession) -> dict[str, int]:
    """대시보드 위젯 등에서 활용 가능한 카운터."""
    rows = (
        await db.execute(
            select(User.admin_grade, func.count())
            .where(User.role == "admin", User.withdrawn_at.is_(None))
            .group_by(User.admin_grade)
        )
    ).all()
    return {(grade or "unknown"): int(n) for grade, n in rows}


__all__ = [
    "GRADE_LABELS",
    "ListFilter",
    "approve_pending",
    "block_admin",
    "count_admins_by_grade",
    "delete_admin",
    "expire_admin_blocks",
    "grade_label_for_user",
    "list_admins",
    "unblock_admin",
    "update_admin_grade",
]
