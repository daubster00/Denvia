"""Story 6.2 — user_service.update_permission 단위 테스트.

본 테스트는 422 분기 6종 + diff_json 구성 + audit_target 설정을 mock DB로 검증한다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api.src.middleware.audit_actions import (
    AUDIT_USER_PERMISSION_EDIT,
    AUDIT_USER_SPEED_OVERRIDE,
)
from api.src.schemas.admin.users import (
    BlockActionRequest,
    UserPermissionUpdateRequest,
    UserSearchItem,
)
from api.src.services import user_service
from api.src.services.user_service import (
    _apply_block,
    _apply_unblock,
    _validate_payload,
)


def _make_user(
    *,
    user_id: int = 1,
    email: str = "user@example.com",
    subscription_status: str = "free",
    daily_quota_override: int | None = None,
    free_delay_override: Decimal | None = None,
    blocked_until: datetime | None = None,
    block_reason: str | None = None,
    pre_block_status: str | None = None,
    pro_granted_by_admin: bool = False,
    last_login_at: datetime | None = None,
    withdrawn_at: datetime | None = None,
) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.email = email
    user.phone = "01012345678"
    user.segment = "dentist"
    user.years_of_experience = 5
    user.subscription_status = subscription_status
    user.daily_quota_override = daily_quota_override
    user.free_delay_override = free_delay_override
    user.blocked_until = blocked_until
    user.block_reason = block_reason
    user.pre_block_status = pre_block_status
    user.pro_granted_by_admin = pro_granted_by_admin
    user.last_login_at = last_login_at
    user.withdrawn_at = withdrawn_at
    user.created_at = datetime(2026, 4, 1, tzinfo=timezone.utc)
    user.updated_at = datetime(2026, 4, 1, tzinfo=timezone.utc)
    return user


def _make_request_state() -> MagicMock:
    request = MagicMock()
    request.state = MagicMock()
    return request


def _make_db() -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


# ── 422 분기 6종 ───────────────────────────────────────────────────────────────


class TestValidatePayload:
    def test_block_action_and_unblock_simultaneously_raises_conflict(self):
        user = _make_user()
        payload = UserPermissionUpdateRequest(
            block_action=BlockActionRequest(duration_hours=24, reason="r"),
            unblock=True,
        )
        with pytest.raises(HTTPException) as exc:
            _validate_payload(user, payload)
        assert exc.value.status_code == 422
        assert exc.value.detail["code"] == "BLOCK_ACTION_CONFLICT"

    def test_pro_force_without_confirmation_raises(self):
        user = _make_user(subscription_status="free")
        payload = UserPermissionUpdateRequest(subscription_status="pro")
        with pytest.raises(HTTPException) as exc:
            _validate_payload(user, payload)
        assert exc.value.detail["code"] == "PRO_GRANT_CONFIRMATION_REQUIRED"

    def test_pro_force_with_confirmation_passes(self):
        user = _make_user(subscription_status="free")
        payload = UserPermissionUpdateRequest(
            subscription_status="pro", pro_granted_by_admin=True
        )
        _validate_payload(user, payload)  # raises 없으면 통과

    def test_already_pro_to_pro_no_confirmation_required(self):
        user = _make_user(subscription_status="pro")
        payload = UserPermissionUpdateRequest(subscription_status="pro")
        _validate_payload(user, payload)  # 이미 pro 인 경우 confirm 불필요

    def test_withdrawn_user_raises(self):
        user = _make_user(withdrawn_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
        payload = UserPermissionUpdateRequest(daily_quota_override=50)
        with pytest.raises(HTTPException) as exc:
            _validate_payload(user, payload)
        assert exc.value.detail["code"] == "USER_ALREADY_WITHDRAWN"

    def test_status_blocked_without_block_action_raises(self):
        user = _make_user()
        payload = UserPermissionUpdateRequest(subscription_status="blocked")
        with pytest.raises(HTTPException) as exc:
            _validate_payload(user, payload)
        assert exc.value.detail["code"] == "BLOCK_ACTION_REASON_REQUIRED"

    def test_unblock_when_not_blocked_raises(self):
        user = _make_user(subscription_status="free")
        payload = UserPermissionUpdateRequest(unblock=True)
        with pytest.raises(HTTPException) as exc:
            _validate_payload(user, payload)
        assert exc.value.detail["code"] == "UNBLOCK_TARGET_NOT_BLOCKED"

    def test_block_action_without_blocked_status_raises(self):
        user = _make_user()
        # subscription_status 미지정 OK (None=blocked 함의), 'pro' 지정 시 422
        payload = UserPermissionUpdateRequest(
            subscription_status="pro",
            pro_granted_by_admin=True,
            block_action=BlockActionRequest(duration_hours=24, reason="r"),
        )
        with pytest.raises(HTTPException) as exc:
            _validate_payload(user, payload)
        assert exc.value.detail["code"] == "BLOCK_ACTION_INVALID_FOR_STATUS"


# ── 헬퍼 함수 ──────────────────────────────────────────────────────────────────


class TestApplyBlock:
    def test_apply_24h_block(self):
        user = _make_user(subscription_status="free")
        now = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)
        _apply_block(
            user,
            BlockActionRequest(duration_hours=24, reason="광고 봇 의심"),
            now,
        )
        assert user.subscription_status == "blocked"
        assert user.blocked_until == now + timedelta(hours=24)
        assert user.block_reason == "광고 봇 의심"
        assert user.pre_block_status == "free"  # 이전 상태 보존

    def test_apply_permanent_block(self):
        user = _make_user(subscription_status="free")
        now = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)
        _apply_block(
            user,
            BlockActionRequest(duration_hours=None, reason="영구"),
            now,
        )
        assert user.subscription_status == "blocked"
        assert user.blocked_until is None
        assert user.block_reason == "영구"
        assert user.pre_block_status == "free"

    def test_apply_block_preserves_pro_status(self):
        user = _make_user(subscription_status="pro")
        now = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)
        _apply_block(user, BlockActionRequest(duration_hours=24, reason="테스트"), now)
        assert user.subscription_status == "blocked"
        assert user.pre_block_status == "pro"  # pro 상태 보존

    def test_reblock_does_not_overwrite_pre_block_status(self):
        # 이미 blocked인 사용자를 re-block할 때 pre_block_status를 덮어쓰지 않아야 함
        user = _make_user(
            subscription_status="blocked",
            pre_block_status="pro",  # 원래 pro였음
        )
        now = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)
        _apply_block(user, BlockActionRequest(duration_hours=48, reason="기간 연장"), now)
        assert user.pre_block_status == "pro"  # 덮어쓰지 않음


class TestApplyUnblock:
    def test_unblock_resets_to_free_when_pre_block_status_is_none(self):
        user = _make_user(
            subscription_status="blocked",
            blocked_until=datetime(2026, 5, 5, tzinfo=timezone.utc),
            block_reason="reason",
            pre_block_status=None,
        )
        _apply_unblock(user)
        assert user.subscription_status == "free"
        assert user.blocked_until is None
        assert user.block_reason is None
        assert user.pre_block_status is None

    def test_unblock_restores_pro_from_pre_block_status(self):
        user = _make_user(
            subscription_status="blocked",
            blocked_until=datetime(2026, 5, 5, tzinfo=timezone.utc),
            block_reason="reason",
            pre_block_status="pro",
        )
        _apply_unblock(user)
        assert user.subscription_status == "pro"  # pro 복원
        assert user.blocked_until is None
        assert user.block_reason is None
        assert user.pre_block_status is None  # 복원 후 초기화


# ── update_permission 통합 ─────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestUpdatePermission:
    async def _stub_serialize(self) -> UserSearchItem:
        return UserSearchItem(
            user_id=1,
            email="user@example.com",
            phone=None,
            segment="dentist",
            years_of_experience=5,
            subscription_status="free",
            is_blocked=False,
            block_until=None,
            daily_quota_override=None,
            created_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
            last_login_at=None,
            withdrawn_at=None,
            pro_since=None,
            card_last4=None,
            card_company=None,
        )

    async def test_user_not_found_raises_404(self):
        db = _make_db()
        request = _make_request_state()
        payload = UserPermissionUpdateRequest(daily_quota_override=50)
        with patch.object(
            user_service, "get_user_by_id", new=AsyncMock(return_value=None)
        ):
            with pytest.raises(HTTPException) as exc:
                await user_service.update_permission(request, 999, payload, db)
        assert exc.value.status_code == 404
        assert exc.value.detail["code"] == "ADMIN_USER_NOT_FOUND"

    async def test_quota_only_change_diff(self):
        user = _make_user(daily_quota_override=None)
        db = _make_db()
        request = _make_request_state()
        payload = UserPermissionUpdateRequest(daily_quota_override=50)

        with patch.object(
            user_service, "get_user_by_id", new=AsyncMock(return_value=user)
        ):
            with patch.object(
                user_service,
                "_serialize_response",
                new=AsyncMock(return_value=await self._stub_serialize()),
            ):
                result = await user_service.update_permission(
                    request, 1, payload, db
                )

        assert result.user_id == 1
        assert user.daily_quota_override == 50
        assert request.state.audit_action == AUDIT_USER_PERMISSION_EDIT
        assert request.state.audit_target_type == "user"
        assert request.state.audit_target_id == 1
        diff = request.state.audit_diff
        assert diff["before"]["daily_quota_override"] is None
        assert diff["after"]["daily_quota_override"] == 50
        # subscription_status는 변경되지 않았으므로 diff에서 제외
        assert "subscription_status" not in diff["before"]
        db.commit.assert_awaited_once()

    async def test_quota_clear_via_explicit_flag(self):
        user = _make_user(daily_quota_override=100)
        db = _make_db()
        request = _make_request_state()
        payload = UserPermissionUpdateRequest(daily_quota_override_clear=True)

        with patch.object(
            user_service, "get_user_by_id", new=AsyncMock(return_value=user)
        ):
            with patch.object(
                user_service,
                "_serialize_response",
                new=AsyncMock(return_value=await self._stub_serialize()),
            ):
                await user_service.update_permission(request, 1, payload, db)

        assert user.daily_quota_override is None
        diff = request.state.audit_diff
        assert diff["before"]["daily_quota_override"] == 100
        assert diff["after"]["daily_quota_override"] is None

    async def test_block_24h_includes_metadata_reason(self):
        user = _make_user(subscription_status="free")
        db = _make_db()
        request = _make_request_state()
        payload = UserPermissionUpdateRequest(
            block_action=BlockActionRequest(duration_hours=24, reason="광고 봇")
        )

        with patch.object(
            user_service, "get_user_by_id", new=AsyncMock(return_value=user)
        ):
            with patch.object(
                user_service,
                "_serialize_response",
                new=AsyncMock(return_value=await self._stub_serialize()),
            ):
                await user_service.update_permission(request, 1, payload, db)

        assert user.subscription_status == "blocked"
        assert user.blocked_until is not None
        assert user.block_reason == "광고 봇"
        diff = request.state.audit_diff
        assert diff["metadata"]["block_reason"] == "광고 봇"
        assert diff["after"]["is_blocked"] is True
        assert diff["before"]["is_blocked"] is False

    async def test_unblock_resets_to_free(self):
        user = _make_user(
            subscription_status="blocked",
            blocked_until=datetime(2026, 5, 10, tzinfo=timezone.utc),
            block_reason="테스트",
            pre_block_status=None,
        )
        db = _make_db()
        request = _make_request_state()
        payload = UserPermissionUpdateRequest(unblock=True)

        with patch.object(
            user_service, "get_user_by_id", new=AsyncMock(return_value=user)
        ):
            with patch.object(
                user_service,
                "_serialize_response",
                new=AsyncMock(return_value=await self._stub_serialize()),
            ):
                await user_service.update_permission(request, 1, payload, db)

        assert user.subscription_status == "free"
        assert user.blocked_until is None
        assert user.block_reason is None
        diff = request.state.audit_diff
        assert diff["before"]["subscription_status"] == "blocked"
        assert diff["after"]["subscription_status"] == "free"

    async def test_unblock_restores_pro_from_pre_block_status(self):
        user = _make_user(
            subscription_status="blocked",
            blocked_until=datetime(2026, 5, 10, tzinfo=timezone.utc),
            block_reason="테스트",
            pre_block_status="pro",
        )
        db = _make_db()
        request = _make_request_state()
        payload = UserPermissionUpdateRequest(unblock=True)

        with patch.object(
            user_service, "get_user_by_id", new=AsyncMock(return_value=user)
        ):
            with patch.object(
                user_service,
                "_serialize_response",
                new=AsyncMock(return_value=await self._stub_serialize()),
            ):
                await user_service.update_permission(request, 1, payload, db)

        assert user.subscription_status == "pro"
        assert user.blocked_until is None
        assert user.pre_block_status is None
        diff = request.state.audit_diff
        assert diff["before"]["subscription_status"] == "blocked"
        assert diff["after"]["subscription_status"] == "pro"

    async def test_pro_grant_marks_metadata_flag(self):
        user = _make_user(subscription_status="free")
        db = _make_db()
        request = _make_request_state()
        payload = UserPermissionUpdateRequest(
            subscription_status="pro", pro_granted_by_admin=True
        )

        with patch.object(
            user_service, "get_user_by_id", new=AsyncMock(return_value=user)
        ):
            with patch.object(
                user_service,
                "_serialize_response",
                new=AsyncMock(return_value=await self._stub_serialize()),
            ):
                await user_service.update_permission(request, 1, payload, db)

        assert user.subscription_status == "pro"
        assert user.pro_granted_by_admin is True
        diff = request.state.audit_diff
        assert diff["metadata"]["pro_granted_by_admin"] is True

    async def test_no_op_payload_rejected_at_schema(self):
        # 모든 필드 None — Pydantic validator가 ValueError 던짐
        with pytest.raises(Exception):
            UserPermissionUpdateRequest()


# ── Story 6.3 — free_delay_override 분기 ────────────────────────────────────


class TestSpeedValidate:
    """Story 6.3 — _validate_payload 추가 분기 검증."""

    def test_speed_set_and_clear_simultaneously_raises_conflict(self):
        user = _make_user()
        payload = UserPermissionUpdateRequest(
            free_delay_override=1.5, free_delay_override_clear=True
        )
        with pytest.raises(HTTPException) as exc:
            _validate_payload(user, payload)
        assert exc.value.status_code == 422
        assert exc.value.detail["code"] == "SPEED_OVERRIDE_CONFLICT"

    def test_speed_quantize_absorbs_sub_step_value(self):
        # Pydantic ge=0/le=30을 통과하면 service quantize는 0.0으로 흡수, 422 안 남
        user = _make_user()
        payload = UserPermissionUpdateRequest(free_delay_override=0.05)
        _validate_payload(user, payload)  # raises 없으면 통과

    def test_speed_pydantic_rejects_above_30(self):
        # Pydantic ge=0.0/le=30.0 검증으로 422 자동 발생
        with pytest.raises(Exception):
            UserPermissionUpdateRequest(free_delay_override=31.0)

    def test_speed_pydantic_rejects_negative(self):
        with pytest.raises(Exception):
            UserPermissionUpdateRequest(free_delay_override=-0.1)


@pytest.mark.asyncio
class TestSpeedUpdatePermission:
    """Story 6.3 — update_permission speed 분기 + audit action 단일/묶음."""

    async def _stub_serialize(self) -> UserSearchItem:
        return UserSearchItem(
            user_id=1,
            email="user@example.com",
            phone=None,
            segment="dentist",
            years_of_experience=5,
            subscription_status="free",
            is_blocked=False,
            block_until=None,
            daily_quota_override=None,
            free_delay_override=None,
            created_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
            last_login_at=None,
            withdrawn_at=None,
            pro_since=None,
            card_last4=None,
            card_company=None,
        )

    async def test_speed_only_change_uses_speed_override_action(self):
        user = _make_user(free_delay_override=None)
        db = _make_db()
        request = _make_request_state()
        payload = UserPermissionUpdateRequest(free_delay_override=1.5)

        with patch.object(
            user_service, "get_user_by_id", new=AsyncMock(return_value=user)
        ):
            with patch.object(
                user_service,
                "_serialize_response",
                new=AsyncMock(return_value=await self._stub_serialize()),
            ):
                await user_service.update_permission(request, 1, payload, db)

        # 단독 변경 — user.speed_override 액션
        assert request.state.audit_action == AUDIT_USER_SPEED_OVERRIDE
        assert user.free_delay_override == Decimal("1.5")
        diff = request.state.audit_diff
        assert diff["before"]["free_delay_override"] is None
        assert diff["after"]["free_delay_override"] == 1.5
        # speed 단독이므로 quota/status 키 없어야 함
        assert "daily_quota_override" not in diff["before"]
        assert "subscription_status" not in diff["before"]

    async def test_speed_plus_quota_uses_permission_edit_action(self):
        user = _make_user(daily_quota_override=None, free_delay_override=None)
        db = _make_db()
        request = _make_request_state()
        payload = UserPermissionUpdateRequest(
            free_delay_override=2.5, daily_quota_override=50
        )

        with patch.object(
            user_service, "get_user_by_id", new=AsyncMock(return_value=user)
        ):
            with patch.object(
                user_service,
                "_serialize_response",
                new=AsyncMock(return_value=await self._stub_serialize()),
            ):
                await user_service.update_permission(request, 1, payload, db)

        # 묶음 변경 — user.permission_edit 액션
        assert request.state.audit_action == AUDIT_USER_PERMISSION_EDIT
        diff = request.state.audit_diff
        assert diff["before"]["free_delay_override"] is None
        assert diff["after"]["free_delay_override"] == 2.5
        assert diff["before"]["daily_quota_override"] is None
        assert diff["after"]["daily_quota_override"] == 50

    async def test_speed_clear_resets_to_null(self):
        user = _make_user(free_delay_override=Decimal("1.5"))
        db = _make_db()
        request = _make_request_state()
        payload = UserPermissionUpdateRequest(free_delay_override_clear=True)

        with patch.object(
            user_service, "get_user_by_id", new=AsyncMock(return_value=user)
        ):
            with patch.object(
                user_service,
                "_serialize_response",
                new=AsyncMock(return_value=await self._stub_serialize()),
            ):
                await user_service.update_permission(request, 1, payload, db)

        assert user.free_delay_override is None
        # speed clear 단독 — 단독 변경으로 audit action speed_override
        assert request.state.audit_action == AUDIT_USER_SPEED_OVERRIDE
        diff = request.state.audit_diff
        assert diff["before"]["free_delay_override"] == 1.5
        assert diff["after"]["free_delay_override"] is None

    async def test_speed_quantize_normalizes_to_one_decimal(self):
        user = _make_user(free_delay_override=None)
        db = _make_db()
        request = _make_request_state()
        # 0.05 입력은 quantize되어 0.0으로 저장
        payload = UserPermissionUpdateRequest(free_delay_override=0.05)

        with patch.object(
            user_service, "get_user_by_id", new=AsyncMock(return_value=user)
        ):
            with patch.object(
                user_service,
                "_serialize_response",
                new=AsyncMock(return_value=await self._stub_serialize()),
            ):
                await user_service.update_permission(request, 1, payload, db)

        assert user.free_delay_override == Decimal("0.0")
        diff = request.state.audit_diff
        assert diff["after"]["free_delay_override"] == 0.0

    async def test_speed_set_and_clear_simultaneously_raises_via_service(self):
        user = _make_user(free_delay_override=Decimal("1.5"))
        db = _make_db()
        request = _make_request_state()
        payload = UserPermissionUpdateRequest(
            free_delay_override=2.0, free_delay_override_clear=True
        )

        with patch.object(
            user_service, "get_user_by_id", new=AsyncMock(return_value=user)
        ):
            with pytest.raises(HTTPException) as exc:
                await user_service.update_permission(request, 1, payload, db)

        assert exc.value.status_code == 422
        assert exc.value.detail["code"] == "SPEED_OVERRIDE_CONFLICT"

    async def test_speed_above_30_rejected_at_schema(self):
        # Pydantic ge=0.0/le=30.0 — service에 들어오기 전에 422
        with pytest.raises(Exception):
            UserPermissionUpdateRequest(free_delay_override=30.5)


# ── 가입유형(segment) 편집 — 관리자 전용 (SSOT 편차 #1) ──────────────────────


@pytest.mark.asyncio
class TestSegmentUpdate:
    """관리자가 가입유형을 수정하는 경로의 diff/audit 동작 검증."""

    async def _stub_serialize(
        self, segment: str | None = "dentist"
    ) -> UserSearchItem:
        return UserSearchItem(
            user_id=1,
            email="user@example.com",
            phone=None,
            segment=segment,
            years_of_experience=5,
            subscription_status="free",
            is_blocked=False,
            block_until=None,
            daily_quota_override=None,
            free_delay_override=None,
            created_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
            last_login_at=None,
            withdrawn_at=None,
            pro_since=None,
            card_last4=None,
            card_company=None,
        )

    async def test_segment_only_change_records_diff_and_permission_edit_action(
        self,
    ):
        user = _make_user()
        user.segment = "dentist"
        db = _make_db()
        request = _make_request_state()
        payload = UserPermissionUpdateRequest(segment="dental_hygienist")

        with patch.object(
            user_service, "get_user_by_id", new=AsyncMock(return_value=user)
        ):
            with patch.object(
                user_service,
                "_serialize_response",
                new=AsyncMock(
                    return_value=await self._stub_serialize(
                        segment="dental_hygienist"
                    )
                ),
            ):
                await user_service.update_permission(request, 1, payload, db)

        assert user.segment == "dental_hygienist"
        assert request.state.audit_action == AUDIT_USER_PERMISSION_EDIT
        diff = request.state.audit_diff
        assert diff["before"]["segment"] == "dentist"
        assert diff["after"]["segment"] == "dental_hygienist"
        # 다른 필드는 변경되지 않았으므로 diff에서 제외
        assert "subscription_status" not in diff["before"]
        assert "daily_quota_override" not in diff["before"]

    async def test_segment_unchanged_value_is_no_op_in_diff(self):
        # 같은 값으로 PATCH 보냈을 때 diff에는 포함되지 않아야 함
        user = _make_user()
        user.segment = "dentist"
        user.daily_quota_override = None
        db = _make_db()
        request = _make_request_state()
        payload = UserPermissionUpdateRequest(
            segment="dentist", daily_quota_override=50
        )

        with patch.object(
            user_service, "get_user_by_id", new=AsyncMock(return_value=user)
        ):
            with patch.object(
                user_service,
                "_serialize_response",
                new=AsyncMock(return_value=await self._stub_serialize()),
            ):
                await user_service.update_permission(request, 1, payload, db)

        diff = request.state.audit_diff
        assert "segment" not in diff["before"]
        assert "segment" not in diff["after"]
        assert diff["before"]["daily_quota_override"] is None
        assert diff["after"]["daily_quota_override"] == 50

    async def test_segment_from_null_records_diff(self):
        user = _make_user()
        user.segment = None
        db = _make_db()
        request = _make_request_state()
        payload = UserPermissionUpdateRequest(segment="student_other")

        with patch.object(
            user_service, "get_user_by_id", new=AsyncMock(return_value=user)
        ):
            with patch.object(
                user_service,
                "_serialize_response",
                new=AsyncMock(
                    return_value=await self._stub_serialize(segment="student_other")
                ),
            ):
                await user_service.update_permission(request, 1, payload, db)

        assert user.segment == "student_other"
        diff = request.state.audit_diff
        assert diff["before"]["segment"] is None
        assert diff["after"]["segment"] == "student_other"

    async def test_segment_invalid_value_rejected_at_schema(self):
        # Pydantic Literal — 3종 외 값은 422
        with pytest.raises(Exception):
            UserPermissionUpdateRequest(segment="doctor")  # type: ignore[arg-type]
