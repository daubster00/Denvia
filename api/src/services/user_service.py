"""유저 서비스 — DB 조회 래퍼 + Story 6.2 권한 편집 도메인 로직.

Story 6.2 추가 함수:
- update_permission: PATCH /admin/users/{id} 통합 진입점.
  - subscription_status, daily_quota_override, block_action, unblock, pro_granted_by_admin
    5종을 한 번에 처리 (모두 optional, 하나 이상 필수).
  - before/after diff를 계산해 request.state.audit_diff/target_*로 미들웨어 INSERT 트리거.
- _validate_payload: 422 분기 6종.
- _apply_block / _apply_unblock: 차단·해제 컬럼 갱신 헬퍼.
- _serialize_with_billing: 응답 직렬화 (admin_user_service._serialize_user 재사용).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.src.middleware.audit_actions import (
    AUDIT_USER_PERMISSION_EDIT,
    AUDIT_USER_SPEED_OVERRIDE,
)
from api.src.models.user import User
from api.src.schemas.admin.users import (
    BlockActionRequest,
    UserPermissionUpdateRequest,
    UserSearchItem,
)
from api.src.services import admin_user_service, anomaly_service


async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    """user_id로 활성 유저를 조회한다. 없으면 None."""
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


# ── Story 6.2 ─────────────────────────────────────────────────────────────────


def _http_422(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=422, detail={"code": code, "message": message})


def _http_404(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=404, detail={"code": code, "message": message})


def _extract_admin_actor_id(request: Request) -> int | None:
    """관리자 세션 쿠키에서 actor user_id를 복원. 실패 시 None."""
    from api.src.utils.jwt import (
        JWTDecodeError,
        SessionExpired,
        decode_admin_session_jwt,
    )

    cookie = request.cookies.get("denvia_admin_session")
    if not cookie:
        return None
    try:
        payload = decode_admin_session_jwt(cookie)
        return int(payload["sub"])
    except (JWTDecodeError, SessionExpired, KeyError, ValueError):
        return None


def _validate_payload(
    user: User, payload: UserPermissionUpdateRequest
) -> None:
    """422 분기 8종 — 도메인 무결성 검증.

    1) BLOCK_ACTION_CONFLICT: block_action + unblock=true 동시
    2) PRO_GRANT_CONFIRMATION_REQUIRED: subscription_status='pro' 강제 + pro_granted_by_admin 누락
    3) USER_ALREADY_WITHDRAWN: 탈퇴 사용자
    4) BLOCK_ACTION_REASON_REQUIRED: subscription_status='blocked' 만 지정 + block_action 미동봉
    5) UNBLOCK_TARGET_NOT_BLOCKED: unblock=true 인데 user.subscription_status != 'blocked'
    6) BLOCK_ACTION_INVALID_FOR_STATUS: block_action 지정인데 subscription_status='blocked' 미지정
    7) SPEED_OVERRIDE_CONFLICT: free_delay_override + free_delay_override_clear=true 동시 (Story 6.3)
    8) SPEED_DELAY_OUT_OF_RANGE: quantize 후 0~30초 경계 이탈 (Story 6.3, 방어적 검증)
    """
    if payload.block_action is not None and payload.unblock is True:
        raise _http_422(
            "BLOCK_ACTION_CONFLICT",
            "차단과 차단 해제는 동시에 수행할 수 없습니다.",
        )

    if (
        payload.free_delay_override is not None
        and payload.free_delay_override_clear is True
    ):
        raise _http_422(
            "SPEED_OVERRIDE_CONFLICT",
            "응답 속도 설정과 초기화는 동시에 수행할 수 없습니다.",
        )

    if payload.free_delay_override is not None:
        quantized = Decimal(str(payload.free_delay_override)).quantize(Decimal("0.1"))
        if quantized < Decimal("0.0") or quantized > Decimal("30.0"):
            raise _http_422(
                "SPEED_DELAY_OUT_OF_RANGE",
                "0 이상 30 이하로 설정해주세요.",
            )

    if (
        payload.subscription_status == "pro"
        and user.subscription_status != "pro"
        and payload.pro_granted_by_admin is not True
    ):
        raise _http_422(
            "PRO_GRANT_CONFIRMATION_REQUIRED",
            "결제 없이 Pro 권한을 부여하려면 확인이 필요합니다.",
        )

    if user.withdrawn_at is not None:
        raise _http_422(
            "USER_ALREADY_WITHDRAWN",
            "탈퇴한 사용자는 수정할 수 없습니다.",
        )

    if (
        payload.subscription_status == "blocked"
        and payload.block_action is None
    ):
        raise _http_422(
            "BLOCK_ACTION_REASON_REQUIRED",
            "차단 시 차단 사유를 입력해야 합니다.",
        )

    if (
        payload.unblock is True
        and user.subscription_status != "blocked"
    ):
        raise _http_422(
            "UNBLOCK_TARGET_NOT_BLOCKED",
            "차단 상태가 아닌 사용자는 차단 해제할 수 없습니다.",
        )

    if (
        payload.block_action is not None
        and payload.subscription_status not in ("blocked", None)
    ):
        raise _http_422(
            "BLOCK_ACTION_INVALID_FOR_STATUS",
            "차단 옵션은 차단 상태에서만 지정할 수 있습니다.",
        )


def _apply_block(user: User, block_action: BlockActionRequest, now: datetime) -> None:
    """user를 차단 상태로 갱신.

    이미 blocked가 아닐 때만 pre_block_status에 이전 상태를 보존한다.
    re-block(기간/사유 수정)이라면 기존 pre_block_status를 유지한다.
    """
    if user.subscription_status != "blocked":
        user.pre_block_status = user.subscription_status
    user.subscription_status = "blocked"
    if block_action.duration_hours is None:
        user.blocked_until = None  # 영구 차단
    else:
        user.blocked_until = now + timedelta(hours=block_action.duration_hours)
    user.block_reason = block_action.reason


def _apply_unblock(user: User) -> None:
    """user 차단 해제 — pre_block_status에서 이전 상태를 복원 (없으면 free)."""
    user.subscription_status = user.pre_block_status if user.pre_block_status is not None else "free"
    user.pre_block_status = None
    user.blocked_until = None
    user.block_reason = None


def _diff_value(before: Any, after: Any) -> bool:
    """ISO 호환 비교 — datetime/Decimal 등도 단순 != 비교."""
    return before != after


def _serialize_dt(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


async def _serialize_response(
    db: AsyncSession, user: User
) -> UserSearchItem:
    """6.1 admin_user_service._serialize_user + 활성 빌링키 1쿼리.

    last_login_at / block_until / pro_since는 진짜 DB 값으로 채운다 (6.1은 placeholder).
    """
    billing_map = await admin_user_service._resolve_active_billing_keys(db, [user.id])
    billing = billing_map.get(user.id)
    item = admin_user_service._serialize_user(user, billing)
    # 6.1 placeholder 자리를 진짜 값으로 덮어씀
    item.block_until = user.blocked_until
    item.last_login_at = user.last_login_at
    return item


async def update_permission(
    request: Request,
    user_id: int,
    payload: UserPermissionUpdateRequest,
    db: AsyncSession,
) -> UserSearchItem:
    """PATCH /admin/users/{user_id} 통합 진입점.

    1. user 조회 + 422 분기 6종
    2. before snapshot 캡처 (변경 가능 컬럼만)
    3. 변경 적용 (subscription_status / quota / block / unblock / pro flag)
    4. after snapshot 캡처 + diff_json 계산 + audit_target/diff 설정
    5. commit + 응답 직렬화

    audit_logs INSERT는 AuditMiddleware가 응답 직후 자동 처리.
    """
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise _http_404("ADMIN_USER_NOT_FOUND", "사용자를 찾을 수 없습니다.")

    _validate_payload(user, payload)

    now = datetime.now(tz=timezone.utc)

    # before snapshot — 변경 가능 컬럼만
    before_status = user.subscription_status
    before_segment = user.segment
    before_quota = user.daily_quota_override
    before_speed = user.free_delay_override
    before_blocked_until = user.blocked_until
    before_pro_granted = user.pro_granted_by_admin
    before_is_blocked = before_status == "blocked"

    # 1) 차단 해제 (unblock=true 단독 분기)
    if payload.unblock is True:
        _apply_unblock(user)
        # 사용자의 모든 'actioned' anomaly 이벤트를 'unblocked' 로 종결.
        # 사용자관리 페이지에서 해제하든 이상탐지 페이지에서 해제하든 동일하게 동기화.
        await anomaly_service.mark_user_anomalies_unblocked(db, user_id=user.id)

    # 2) 차단 적용 (block_action — subscription_status='blocked' 자동 설정)
    if payload.block_action is not None:
        _apply_block(user, payload.block_action, now)
        # 이상탐지 UI에서 호출된 경우, 해당 anomaly_event를 'actioned' 로 전이.
        if payload.block_action.anomaly_id is not None:
            await anomaly_service.mark_anomaly_actioned(
                db,
                anomaly_id=payload.block_action.anomaly_id,
                actor_admin_id=_extract_admin_actor_id(request),
            )

    # 3) 일반 subscription_status 변경 (block_action/unblock 분기와 충돌 안 하도록 마지막)
    if payload.subscription_status is not None and payload.block_action is None and payload.unblock is not True:
        user.subscription_status = payload.subscription_status
        if payload.subscription_status == "pro":
            if payload.pro_granted_by_admin is True:
                user.pro_granted_by_admin = True
        elif payload.subscription_status == "free":
            # 명시적 free 전환 시 차단 컬럼도 초기화 (운영 일관성)
            user.blocked_until = None
            user.block_reason = None

    # 4) daily_quota_override (clear vs set 분리)
    if payload.daily_quota_override_clear is True:
        user.daily_quota_override = None
    elif payload.daily_quota_override is not None:
        user.daily_quota_override = payload.daily_quota_override

    # 4-b) segment (가입유형) — 관리자만 변경 가능 (SSOT 편차 #1)
    if payload.segment is not None:
        user.segment = payload.segment

    # 5) pro_granted_by_admin 단독 변경 (subscription_status='pro' 분기에서 이미 설정한 경우 idempotent)
    if (
        payload.pro_granted_by_admin is not None
        and user.subscription_status == "pro"
    ):
        user.pro_granted_by_admin = payload.pro_granted_by_admin

    # 6) free_delay_override (clear vs set 분리) — Story 6.3
    if payload.free_delay_override_clear is True:
        user.free_delay_override = None
    elif payload.free_delay_override is not None:
        # 클라이언트가 0.05 같은 비-step 값을 보낼 수 있으므로 quantize로 정규화
        user.free_delay_override = Decimal(str(payload.free_delay_override)).quantize(
            Decimal("0.1")
        )

    user.updated_at = now

    # after snapshot
    after_status = user.subscription_status
    after_segment = user.segment
    after_quota = user.daily_quota_override
    after_speed = user.free_delay_override
    after_blocked_until = user.blocked_until
    after_pro_granted = user.pro_granted_by_admin
    after_is_blocked = after_status == "blocked"

    # diff_json 구성 — 변경된 필드만 before/after 양쪽에 포함
    before_diff: dict[str, Any] = {}
    after_diff: dict[str, Any] = {}

    if _diff_value(before_status, after_status):
        before_diff["subscription_status"] = before_status
        after_diff["subscription_status"] = after_status

    if _diff_value(before_segment, after_segment):
        before_diff["segment"] = before_segment
        after_diff["segment"] = after_segment

    if _diff_value(before_quota, after_quota):
        before_diff["daily_quota_override"] = before_quota
        after_diff["daily_quota_override"] = after_quota

    if _diff_value(before_speed, after_speed):
        before_diff["free_delay_override"] = (
            float(before_speed) if before_speed is not None else None
        )
        after_diff["free_delay_override"] = (
            float(after_speed) if after_speed is not None else None
        )

    if _diff_value(before_is_blocked, after_is_blocked):
        before_diff["is_blocked"] = before_is_blocked
        after_diff["is_blocked"] = after_is_blocked

    if _diff_value(before_blocked_until, after_blocked_until):
        before_diff["blocked_until"] = _serialize_dt(before_blocked_until)
        after_diff["blocked_until"] = _serialize_dt(after_blocked_until)

    metadata: dict[str, Any] = {}
    if payload.block_action is not None:
        metadata["block_reason"] = payload.block_action.reason
    if (
        before_pro_granted != after_pro_granted
        and after_pro_granted is True
    ):
        metadata["pro_granted_by_admin"] = True

    diff_json: dict[str, Any] = {"before": before_diff, "after": after_diff}
    if metadata:
        diff_json["metadata"] = metadata

    # audit action 분리 (Story 6.3 편차 4): free_delay_override 단독 변경 시 별도 액션
    changed_keys = set(before_diff.keys())
    is_speed_only = changed_keys == {"free_delay_override"}

    # audit middleware hooks
    request.state.audit_action = (
        AUDIT_USER_SPEED_OVERRIDE if is_speed_only else AUDIT_USER_PERMISSION_EDIT
    )
    request.state.audit_target_type = "user"
    request.state.audit_target_id = user.id
    request.state.audit_diff = diff_json

    await db.commit()
    await db.refresh(user)

    return await _serialize_response(db, user)
