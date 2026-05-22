"""Story 6.5 — Admin 이상 이벤트 응답 schema."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class AnomalyEventItem(BaseModel):
    """list/단건 응답 공통 row.

    target_user_email_masked는 list 응답에서만 채워짐 (상세 권한은 6.1 진입점 경유).
    """

    id: int
    type: Literal[
        "login_brute_force",
        "concurrent_ip_login",
        "repeated_question",
        "recovery_abuse",
        "rapid_followup_questions",
    ]
    target_user_id: int | None = None
    target_user_email_masked: str | None = Field(
        default=None,
        description="target_user_id가 있는 경우만 마스킹된 이메일 (예: k**@example.com).",
    )
    ip: str | None = None
    ua: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    status: Literal["new", "reviewed", "actioned", "unblocked"]
    reviewed_by_admin_id: int | None = None
    reviewed_at: datetime | None = None
    created_at: datetime


class AnomalyListResponse(BaseModel):
    """GET /api/v1/admin/anomaly — flat 페이지네이션 (AR27)."""

    items: list[AnomalyEventItem]
    page: int
    per_page: int
    total: int


class AnomalyMarkReviewedRequest(BaseModel):
    """PATCH /api/v1/admin/anomaly/{id} body.

    `status` 필드는 'reviewed' 단일 값만 허용 — 'actioned' 직접 전이는 차단 endpoint 경유 only.
    실제 값 검증은 라우터에서 수행해 spec AC-7의 `ANOMALY_STATUS_INVALID` 코드 보장.
    """

    status: str


class AnomalyMarkReviewedResponse(AnomalyEventItem):
    """PATCH /api/v1/admin/anomaly/{id} 응답 — 단건 row."""


class AnomalyDetailResponse(AnomalyEventItem):
    """GET /api/v1/admin/anomaly/{id} 응답 — 상세 드로어용 보강 필드.

    list 응답에 누적 통계·자동조치 표식·차단 현황·메모를 추가한 superset.
    """

    admin_memo: str | None = None
    # 자동조치(throttle)가 시스템에 의해 즉시 적용된 이벤트인지.
    # rapid_followup_questions 는 항상 True, 그 외는 False.
    auto_actioned: bool = False
    # 같은 (target_user_id, type) 조합의 누적 탐지 횟수 + 가장 최근 탐지 시각.
    # target_user_id 가 NULL(IP 기반) 인 이벤트는 (ip, type) 조합으로 집계.
    occurrence_count: int = 1
    last_occurred_at: datetime | None = None
    # 차단 현황 — 대상 사용자가 있는 경우만 채워짐.
    user_subscription_status: Literal["free", "pro", "blocked"] | None = None
    user_blocked_until: datetime | None = None
    user_block_reason: str | None = None
    user_question_blocked_until: datetime | None = None
    user_question_block_reason: str | None = None
    user_anomaly_throttled_at: datetime | None = None


class AnomalyMemoUpdateRequest(BaseModel):
    """PATCH /api/v1/admin/anomaly/{id}/memo 요청 — 메모만 갱신.

    빈 문자열은 NULL 로 정규화 (저장 시 ``""`` → None).
    """

    memo: str = Field(default="", max_length=2000, description="관리자 자유 메모 (0~2000자).")


__all__ = [
    "AnomalyEventItem",
    "AnomalyListResponse",
    "AnomalyMarkReviewedRequest",
    "AnomalyMarkReviewedResponse",
    "AnomalyDetailResponse",
    "AnomalyMemoUpdateRequest",
]
