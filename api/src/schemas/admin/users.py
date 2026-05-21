"""Admin 사용자 통합 검색·상세 — Story 6.1 Pydantic schema.

본 모듈은 GET /api/v1/admin/users (목록 + 검색·필터·페이지네이션)와
GET /api/v1/admin/users/{user_id} (상세 Drawer 단건 조회) 두 endpoint의
요청·응답 schema를 정의한다.

주요 결정:
- AR27 flat 페이지네이션(items/page/per_page/total) 그대로 차용.
- is_blocked 는 subscription_status='blocked' 매핑 (편차 1, Story 6.2가 컬럼 추가).
- card_last4/card_company 는 활성 빌링키 단일 LEFT JOIN 결과 (없으면 둘 다 null).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class UserSearchItem(BaseModel):
    """검색 결과 1행 — 목록·상세 응답 양쪽에서 동일하게 사용한다."""

    user_id: int
    email: str
    phone: str | None = None
    segment: str | None = None
    years_of_experience: int | None = None
    subscription_status: Literal["free", "pro", "blocked"]
    is_blocked: bool = Field(description="subscription_status=='blocked' 매핑 (Story 6.2가 컬럼 추가 예정)")
    block_until: datetime | None = Field(default=None, description="Story 6.2 컬럼 추가 후 채움")
    daily_quota_override: int | None = None
    free_delay_override: float | None = Field(
        default=None,
        description="개별 응답 지연(초). NULL=전역 설정 따름. 0.0~30.0, 0.1 단위 (Story 6.3).",
    )
    anomaly_throttled_at: datetime | None = Field(
        default=None,
        description="이상 질문 패턴 탐지로 자동 throttle 이 적용된 시각. NULL=throttle 미적용.",
    )
    created_at: datetime
    last_login_at: datetime | None = Field(default=None, description="Story 6.2 컬럼 추가 후 채움")
    withdrawn_at: datetime | None = None
    pro_since: datetime | None = Field(default=None, description="Epic 3 결제 흐름이 채울 수 있는 시점에 보강")
    card_last4: str | None = None
    card_company: str | None = None


class UserSearchListResponse(BaseModel):
    """GET /api/v1/admin/users 응답 — AR27 flat 페이지네이션."""

    items: list[UserSearchItem]
    page: int
    per_page: int
    total: int


class SubscriptionSummary(BaseModel):
    """상세 Drawer 결제 정보 섹션."""

    current_status: Literal["free", "pro", "blocked"]
    billing_key_active: bool
    card_last4: str | None = None
    card_company: str | None = None
    subscription_started_at: datetime | None = None
    next_charge_at: datetime | None = None


class RecentQALog(BaseModel):
    """최근 질의 1건 (질문/답변 전문 + 토큰 + 비용)."""

    qa_log_id: int
    question_excerpt: str
    answer_excerpt: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: Decimal | None = None
    status: str | None = None
    created_at: datetime


class RecentAnomalyEvent(BaseModel):
    """최근 이상 이벤트 1건 (5종 enum 그대로 노출)."""

    id: int
    type: str
    ip: str | None = None
    status: str
    created_at: datetime


class UserDetailResponse(BaseModel):
    """GET /api/v1/admin/users/{user_id} 응답 — Drawer 4 섹션."""

    user: UserSearchItem
    subscription_summary: SubscriptionSummary
    recent_qa: list[RecentQALog]
    recent_anomaly_events: list[RecentAnomalyEvent]


# Story 6.2 — PATCH /api/v1/admin/users/{user_id} 요청 스키마
class BlockActionRequest(BaseModel):
    """차단 적용 요청 — block_action 필드의 중첩 모델."""

    duration_hours: int | None = Field(
        default=None,
        ge=1,
        le=8760,
        description="1~8760시간(최대 1년). null=영구 차단.",
    )
    reason: str = Field(min_length=1, max_length=200, description="차단 사유 (1~200자, 필수)")
    anomaly_id: int | None = Field(
        default=None,
        ge=1,
        description="이상탐지 UI에서 차단을 적용한 경우, 해당 anomaly_event.id. "
        "전달 시 해당 이벤트를 'actioned' 상태로 전이한다. 일반 권한 수정 시 생략.",
    )


class UserPermissionUpdateRequest(BaseModel):
    """PATCH /api/v1/admin/users/{user_id} 요청 본문.

    모든 필드 선택. 한 번의 요청으로 권한·한도·차단/해제 동시 적용 가능.
    """

    subscription_status: Literal["free", "pro", "blocked"] | None = None
    segment: Literal["doctor", "hygienist", "student_other"] | None = Field(
        default=None,
        description="가입유형 — 관리자가 사용자 분류를 교정할 때 사용 (SSOT 편차 #1: 관리자만 변경 가능).",
    )
    daily_quota_override: int | None = Field(default=None, ge=1, le=10000)
    daily_quota_override_clear: bool | None = Field(
        default=None,
        description="True 시 daily_quota_override 컬럼을 NULL로 리셋한다 "
        "(JSON null과 unset 미지정의 모호함을 명시 플래그로 해소).",
    )
    free_delay_override: float | None = Field(
        default=None,
        ge=0.0,
        le=30.0,
        description="개별 응답 지연(초). 0.0~30.0, 0.1 단위. None=unset(변경 안 함). "
        "전역 기본값으로 되돌리려면 free_delay_override_clear=true 사용 (Story 6.3).",
    )
    free_delay_override_clear: bool | None = Field(
        default=None,
        description="True 시 free_delay_override 컬럼을 NULL로 리셋한다 "
        "(JSON null과 unset 미지정의 모호함을 명시 플래그로 해소).",
    )
    block_action: BlockActionRequest | None = None
    unblock: bool | None = None
    pro_granted_by_admin: bool | None = None

    @model_validator(mode="after")
    def _check_no_op(self) -> "UserPermissionUpdateRequest":
        """모든 필드가 None이면 422 — 무의미한 PATCH 거부."""
        if (
            self.subscription_status is None
            and self.segment is None
            and self.daily_quota_override is None
            and self.daily_quota_override_clear is not True
            and self.free_delay_override is None
            and self.free_delay_override_clear is not True
            and self.block_action is None
            and self.unblock is None
            and self.pro_granted_by_admin is None
        ):
            raise ValueError("적어도 한 개 필드를 지정해야 합니다.")
        return self


__all__ = [
    "UserSearchItem",
    "UserSearchListResponse",
    "SubscriptionSummary",
    "RecentQALog",
    "RecentAnomalyEvent",
    "UserDetailResponse",
    "BlockActionRequest",
    "UserPermissionUpdateRequest",
]
