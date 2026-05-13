"""Admin kill-switch — Pydantic 스키마 (Story 9.2 A-502).

GET   /api/v1/admin/killswitch/status              auto/manual 모드 통합 상태 조회
POST  /api/v1/admin/killswitch/manual/activate     수동 비상 정지 발동 (사유 4~500자)
POST  /api/v1/admin/killswitch/manual/deactivate   수동 비상 정지 해제 + 구독 자동 연장 enqueue

설계 원칙:
- snake_case 필드명 일관 (Story 9.1 패턴).
- 비활성 모드의 시각·사유 필드는 모두 None.
- 사유는 plain text + 4~500자 zod 검증 일치.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class AutoFreeOnlyStatus(BaseModel):
    """자동 무료 차단 모드 상태."""

    active: bool
    activated_at: datetime | None = None
    year_month: str | None = None
    current_percent: float
    monthly_limit_usd: Decimal
    spent_usd: Decimal

    model_config = ConfigDict()

    @field_serializer("monthly_limit_usd", "spent_usd")
    def _ser_decimal(self, v: Decimal) -> str:
        return f"{v:.2f}"


class ManualTotalStatus(BaseModel):
    """수동 전체 정지 모드 상태."""

    active: bool
    activated_at: datetime | None = None
    deactivated_at: datetime | None = None
    reason: str | None = None
    activated_by_admin_email: str | None = None
    activated_by_admin_id: int | None = None


class KillswitchStatusResponse(BaseModel):
    """GET /api/v1/admin/killswitch/status 응답."""

    auto_free_only: AutoFreeOnlyStatus
    manual_total: ManualTotalStatus


class ManualActivateRequest(BaseModel):
    """수동 비상 정지 발동 요청 — 사유 4~500자."""

    reason: str = Field(
        min_length=4,
        max_length=500,
        description="비상 정지 발동 사유 (audit_logs.diff_json에 본문 그대로 저장).",
    )


class ManualActivateResponse(BaseModel):
    """수동 비상 정지 발동 응답."""

    id: int
    activated_at: datetime
    mode: str
    active: bool


class ManualDeactivateResponse(BaseModel):
    """수동 비상 정지 해제 응답."""

    id: int
    deactivated_at: datetime
    duration_seconds: int
    extension_task_id: str | None = None


class ManualRequeueExtensionResponse(BaseModel):
    """수동 구독 연장 재enqueue 응답 — enqueue 실패 시 복구용."""

    id: int
    extension_task_id: str


__all__ = [
    "AutoFreeOnlyStatus",
    "ManualTotalStatus",
    "KillswitchStatusResponse",
    "ManualActivateRequest",
    "ManualActivateResponse",
    "ManualDeactivateResponse",
    "ManualRequeueExtensionResponse",
]
