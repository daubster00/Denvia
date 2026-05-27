"""Story 10.4 — 관리자 활동 로그 조회 서비스 (`/admin/admins/logs` 페이지 백엔드).

엔드포인트와 1:1 매핑 (모두 `require_admin_grade('master','operator')`):
- list_logs       → GET /api/v1/admin/accounts/logs
- get_log_diff    → GET /api/v1/admin/accounts/logs/{log_id}/diff
- export_logs_xlsx→ GET /api/v1/admin/accounts/logs/export.xlsx

권한 분기 (FR62 / Story 10.4 AC-3·AC-5):
- master         → 전체 actor 가시 + `actor_id=system` 옵션 허용
- operator       → 본인 + 활성 sub_operator 작성 로그만 가시. 다른 actor_id 입력 시 403.
- sub_operator   → require_admin_grade 단계에서 이미 차단됨 (여기 도달 불가).

민감 필드 마스킹 (NFR-S2 / AC-4):
- `_REDACT_KEYS` 화이트리스트 키는 재귀적으로 `"***REDACTED***"` 로 치환.
- 응답 직전 백엔드에서 일괄 처리 — 프론트는 마스킹 결정 권한 없음.

시스템 자동 액션 식별 (AC-6 — 한계):
- `audit_logs.actor_user_id`는 NOT NULL + FK. 시스템 액션도 첫 admin id로 INSERT됨.
- 본 모듈은 action 코드 패턴 + actor_user_id == _resolve_system_actor_id 조합으로 식별.
- 정확성 한계 — 첫 admin이 수동 unblock 한 로그도 "시스템"으로 분류될 수 있음.
- 장기 개선: `audit_logs.actor_kind ENUM('user','admin','system')` 컬럼 신설 백로그.
"""

from __future__ import annotations

import base64
import io
import json
from datetime import datetime, timezone
from typing import Any, Literal

import structlog
from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.models.audit_log import AuditLog
from api.src.models.user import User

logger = structlog.get_logger(__name__)


# ── 민감 필드 화이트리스트 ────────────────────────────────────────────────────
# 본 SSOT 외 키는 평문 유지. 블랙리스트 채택하지 않음(일반 키도 마스킹되면 페이지 무의미).
_REDACT_KEYS = frozenset({
    "password_hash",
    "password_hash_old",
    "billing_key_encrypted",
    "billing_key",
    "payment_secret",
    "card_number",
    "pg_secret_key",
    "kakao_access_token",
    "kakao_refresh_token",
    "naver_access_token",
    "naver_refresh_token",
    "google_access_token",
    "google_refresh_token",
    "sms_token",
    "session_token",
})
_REDACT_VALUE = "***REDACTED***"

_DEFAULT_LIMIT = 100
_MAX_LIMIT = 200
_MAX_EXPORT_ROWS = 10_000

# 시스템 자동 액션 식별용 — AC-6. anomaly_tasks._expire_blocks 분기에서 발생.
_SYSTEM_ACTION_CODES = ("user.block_auto_expired", "admin.account.unblocked")


def _master_actor_subquery():
    """admin_grade='master' 인 사용자 id 서브쿼리.

    활동 로그에서 마스터 계정 actor 의 행위는 일괄 숨긴다 (사용자 정책).
    예외 — `actor_id="system"` 필터: 시스템 자동 액션이 첫 admin (=대체로 master) actor
    로 INSERT 되는 한계 때문에 시스템 필터 분기에서는 본 제외를 적용하지 않는다.
    """
    return select(User.id).where(User.admin_grade == "master")


# ── 마스킹 ────────────────────────────────────────────────────────────────────


def _redact_diff(node: Any) -> Any:
    """재귀 마스킹 — dict/list/primitive 처리.

    화이트리스트 키에 매칭되면 값을 통째로 `_REDACT_VALUE` 문자열로 치환한다.
    값이 dict/list여도 추가 재귀하지 않고 단순 마스킹(키 자체가 민감 영역의 진입점).
    """
    if isinstance(node, dict):
        return {
            k: (_REDACT_VALUE if k in _REDACT_KEYS else _redact_diff(v))
            for k, v in node.items()
        }
    if isinstance(node, list):
        return [_redact_diff(item) for item in node]
    return node


# ── cursor (created_at, id) 기반 base64 인코딩 ────────────────────────────────


def _encode_cursor(created_at: datetime, log_id: int) -> str:
    raw = f"{created_at.isoformat()}:{log_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, int]:
    try:
        pad = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode((cursor + pad).encode()).decode()
        iso, id_str = raw.rsplit(":", 1)
        return datetime.fromisoformat(iso), int(id_str)
    except (ValueError, UnicodeDecodeError, base64.binascii.Error) as exc:
        raise HTTPException(
            422,
            detail={"code": "INVALID_CURSOR", "message": "잘못된 페이지 커서입니다."},
        ) from exc


# ── 시스템 actor 식별 (AC-6) ──────────────────────────────────────────────────


async def _resolve_system_actor_id(db: AsyncSession) -> int | None:
    """첫 번째 admin user id — workers/anomaly_tasks._resolve_system_actor_id 와 동일."""
    row = (
        await db.execute(
            select(User.id).where(User.role == "admin").order_by(User.id).limit(1)
        )
    ).scalar_one_or_none()
    return row


# ── 가시성 가드 ───────────────────────────────────────────────────────────────


async def _visible_actor_ids(db: AsyncSession, actor: User) -> list[int] | None:
    """actor 등급에 따라 조회 가능한 actor_user_id 목록.

    - master → None (전체 가시)
    - operator → 본인 + 활성 sub_operator id 리스트
    - sub_operator → 빈 리스트 (이론상 도달 불가, 방어용)
    """
    grade = getattr(actor, "admin_grade", None)
    if grade == "master":
        return None
    if grade == "operator":
        rows = (
            await db.execute(
                select(User.id).where(
                    User.role == "admin",
                    User.withdrawn_at.is_(None),
                    or_(User.id == actor.id, User.admin_grade == "sub_operator"),
                )
            )
        ).scalars().all()
        return list(rows)
    # NULL 백필 누락 admin — 보수적으로 본인만
    if grade is None:
        return [actor.id]
    # sub_operator / pending — 방어 (라우터 가드가 먼저 차단)
    return []


async def _assert_log_visible_to(
    db: AsyncSession, actor: User, log: AuditLog
) -> None:
    """단일 로그 가시성 검증 — diff 조회에서 사용.

    마스터 actor 로그는 일괄 숨김. 단, 시스템 자동 액션 코드(`_SYSTEM_ACTION_CODES`)
    는 첫 admin=master 로 INSERT 되는 한계로 인해 list 의 system 분기에서 노출
    되므로, 해당 코드의 diff 조회는 허용한다.
    """
    actor_grade = (
        await db.execute(
            select(User.admin_grade).where(User.id == log.actor_user_id)
        )
    ).scalar_one_or_none()
    if (
        actor_grade == "master"
        and log.action not in _SYSTEM_ACTION_CODES
    ):
        # 목록에서 보이지 않는 로그 — 존재 자체를 숨김(404)
        raise HTTPException(
            404,
            detail={
                "code": "AUDIT_LOG_NOT_FOUND",
                "message": "로그를 찾을 수 없습니다.",
            },
        )

    visible = await _visible_actor_ids(db, actor)
    if visible is None:
        return  # master — 전체 통과
    if log.actor_user_id not in visible:
        raise HTTPException(
            403,
            detail={
                "code": "ADMIN_LOG_FORBIDDEN_ACTOR",
                "message": "조회 권한이 없는 관리자입니다.",
            },
        )


def _forbidden_actor() -> HTTPException:
    return HTTPException(
        403,
        detail={
            "code": "ADMIN_LOG_FORBIDDEN_ACTOR",
            "message": "조회 권한이 없는 관리자입니다.",
        },
    )


# ── WHERE 절 조립 (list_logs / export_logs_xlsx 공통) ─────────────────────────


async def _build_filter_stmt(
    db: AsyncSession,
    *,
    actor: User,
    actor_id: int | Literal["system"] | None,
    action_in: list[str] | None,
    from_at: datetime | None,
    to_at: datetime | None,
    target_id: int | None,
    cursor: str | None,
):
    """list_logs/export 공통 WHERE/ORDER BY 빌더 — limit 만 호출자가 결정."""
    if from_at and to_at and from_at > to_at:
        raise HTTPException(
            422,
            detail={
                "code": "INVALID_RANGE",
                "message": "from_at must be <= to_at",
            },
        )

    visible = await _visible_actor_ids(db, actor)

    stmt = select(AuditLog)

    # actor_id 가드 + WHERE. 시스템 필터 분기에서는 마스터 제외를 건너뛴다
    # (시스템 자동 액션이 첫 admin=master actor 로 INSERT 되는 한계 때문).
    skip_master_exclusion = False
    if actor_id == "system":
        if getattr(actor, "admin_grade", None) != "master":
            raise _forbidden_actor()
        system_actor_id = await _resolve_system_actor_id(db)
        if system_actor_id is None:
            # 시드 누락 — 빈 결과 반환을 위해 불가능한 조건
            stmt = stmt.where(AuditLog.actor_user_id == -1)
        else:
            stmt = stmt.where(
                AuditLog.actor_user_id == system_actor_id,
                AuditLog.action.in_(_SYSTEM_ACTION_CODES),
            )
        skip_master_exclusion = True
    elif isinstance(actor_id, int):
        # 가시성 검증 — 존재 여부보다 가시성 검증이 우선 (enum 누설 방지)
        if visible is not None and actor_id not in visible:
            raise _forbidden_actor()
        stmt = stmt.where(AuditLog.actor_user_id == actor_id)
    else:
        # actor_id 미지정 — 가시 범위 자동 필터
        if visible is not None:
            if not visible:
                # 가시 actor 0명 — 빈 결과
                stmt = stmt.where(AuditLog.actor_user_id == -1)
            else:
                stmt = stmt.where(AuditLog.actor_user_id.in_(visible))

    # 마스터 등급 actor 의 일반 활동 로그는 노출 대상에서 제외 (사용자 정책).
    if not skip_master_exclusion:
        stmt = stmt.where(AuditLog.actor_user_id.not_in(_master_actor_subquery()))

    if action_in:
        stmt = stmt.where(AuditLog.action.in_(action_in))

    if from_at:
        stmt = stmt.where(AuditLog.created_at >= from_at)
    if to_at:
        stmt = stmt.where(AuditLog.created_at <= to_at)

    if target_id is not None:
        stmt = stmt.where(AuditLog.target_id == target_id)

    if cursor:
        cur_at, cur_id = _decode_cursor(cursor)
        # (created_at, id) < cursor — 안정적 페이지네이션
        stmt = stmt.where(
            or_(
                AuditLog.created_at < cur_at,
                (AuditLog.created_at == cur_at) & (AuditLog.id < cur_id),
            )
        )

    stmt = stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    return stmt


# ── 보조: actor_email / target_preview 채움 (N+1 방지) ────────────────────────


async def _load_actor_email_map(
    db: AsyncSession, rows: list[AuditLog]
) -> dict[int, str]:
    actor_ids = {r.actor_user_id for r in rows}
    if not actor_ids:
        return {}
    result = await db.execute(
        select(User.id, User.email).where(User.id.in_(actor_ids))
    )
    return {row.id: row.email for row in result}


async def _load_target_preview_map(
    db: AsyncSession, rows: list[AuditLog]
) -> dict[int, str]:
    target_user_ids = {
        r.target_id
        for r in rows
        if r.target_type == "user" and r.target_id is not None
    }
    if not target_user_ids:
        return {}
    result = await db.execute(
        select(User.id, User.email).where(User.id.in_(target_user_ids))
    )
    return {row.id: row.email for row in result}


def _row_to_item(
    r: AuditLog,
    actor_map: dict[int, str],
    target_map: dict[int, str],
) -> dict[str, Any]:
    created_at = r.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return {
        "id": r.id,
        "created_at": created_at.isoformat(),
        "actor_user_id": r.actor_user_id,
        "actor_email": actor_map.get(r.actor_user_id, ""),
        "action": r.action,
        "target_type": r.target_type,
        "target_id": r.target_id,
        "target_preview": (
            target_map.get(r.target_id)
            if r.target_type == "user" and r.target_id is not None
            else None
        ),
        "ip": str(r.ip) if r.ip else None,
        "has_diff": r.diff_json is not None,
    }


# ── 공개 API ──────────────────────────────────────────────────────────────────


async def list_logs(
    db: AsyncSession,
    *,
    actor: User,
    actor_id: int | Literal["system"] | None,
    action_in: list[str] | None,
    from_at: datetime | None,
    to_at: datetime | None,
    target_id: int | None,
    cursor: str | None,
    limit: int = _DEFAULT_LIMIT,
) -> dict[str, Any]:
    """페이지 1건당 최대 200건 (기본 100). cursor 기반 stable pagination."""
    if limit < 1 or limit > _MAX_LIMIT:
        raise HTTPException(
            422,
            detail={"code": "INVALID_LIMIT", "message": "limit must be 1..200"},
        )

    stmt = await _build_filter_stmt(
        db,
        actor=actor,
        actor_id=actor_id,
        action_in=action_in,
        from_at=from_at,
        to_at=to_at,
        target_id=target_id,
        cursor=cursor,
    )
    stmt = stmt.limit(limit + 1)

    rows = (await db.execute(stmt)).scalars().all()
    next_cursor: str | None = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = _encode_cursor(last.created_at, last.id)
        rows = list(rows[:limit])
    else:
        rows = list(rows)

    actor_map = await _load_actor_email_map(db, rows)
    target_map = await _load_target_preview_map(db, rows)

    items = [_row_to_item(r, actor_map, target_map) for r in rows]
    return {"items": items, "next_cursor": next_cursor}


async def get_log_diff(
    db: AsyncSession, actor: User, log_id: int
) -> dict[str, Any]:
    """단일 로그 diff 조회 — REDACTED 마스킹 적용."""
    log = (
        await db.execute(select(AuditLog).where(AuditLog.id == log_id))
    ).scalar_one_or_none()
    if log is None:
        raise HTTPException(
            404,
            detail={
                "code": "AUDIT_LOG_NOT_FOUND",
                "message": "로그를 찾을 수 없습니다.",
            },
        )
    await _assert_log_visible_to(db, actor, log)
    return {
        "id": log.id,
        "diff_json": _redact_diff(log.diff_json) if log.diff_json else None,
    }


async def export_logs_xlsx(
    db: AsyncSession,
    *,
    actor: User,
    actor_id: int | Literal["system"] | None,
    action_in: list[str] | None,
    from_at: datetime | None,
    to_at: datetime | None,
    target_id: int | None,
) -> tuple[io.BytesIO, str, bool]:
    """openpyxl Workbook 생성 후 (buf, filename, truncated) 반환.

    Story 5.5 패턴 — `routers/admin/analytics.py:478-532` 일관.
    최대 10,000행 + diff_json 컬럼은 마스킹된 JSON 문자열(indent=2).
    """
    import openpyxl  # 함수 내 import — 콜드 스타트 영향 최소화

    stmt = await _build_filter_stmt(
        db,
        actor=actor,
        actor_id=actor_id,
        action_in=action_in,
        from_at=from_at,
        to_at=to_at,
        target_id=target_id,
        cursor=None,
    )
    stmt = stmt.limit(_MAX_EXPORT_ROWS + 1)
    rows = list((await db.execute(stmt)).scalars().all())

    truncated = len(rows) > _MAX_EXPORT_ROWS
    if truncated:
        rows = rows[:_MAX_EXPORT_ROWS]

    actor_map = await _load_actor_email_map(db, rows)
    target_map = await _load_target_preview_map(db, rows)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "관리자 활동 로그"
    ws.append([
        "시각(KST)",
        "Actor 이메일",
        "액션 코드",
        "target_type",
        "target_id",
        "target preview",
        "IP",
        "diff_json",
    ])
    for r in rows:
        created_at = r.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        # UTC → KST 변환은 표시 컬럼만 (서버 측 출력은 UTC 유지가 SSOT이지만 엑셀은 KST 사용자 친화)
        from datetime import timedelta
        kst = created_at + timedelta(hours=9)
        kst_str = kst.strftime("%Y-%m-%d %H:%M:%S")

        diff_str = ""
        if r.diff_json is not None:
            diff_str = json.dumps(
                _redact_diff(r.diff_json), indent=2, ensure_ascii=False
            )

        preview = (
            target_map.get(r.target_id)
            if r.target_type == "user" and r.target_id is not None
            else ""
        )
        ws.append([
            kst_str,
            actor_map.get(r.actor_user_id, ""),
            r.action,
            r.target_type or "",
            r.target_id if r.target_id is not None else "",
            preview or "",
            str(r.ip) if r.ip else "",
            diff_str,
        ])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    # 파일명 — Story 5.5 패턴: 기간이 없으면 "all"
    from_date = from_at.date().isoformat() if from_at else "all"
    to_date = to_at.date().isoformat() if to_at else "all"
    filename = f"admin_logs_{from_date}_{to_date}.xlsx"
    return buf, filename, truncated
