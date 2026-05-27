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
        "sms_abuse",
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
    # 같은 (target_user_id, type) — target_user_id 가 NULL 이면 (ip, type) — 조합의
    # 누적 탐지 횟수. list 응답은 그룹별 최신 1건만 노출하므로 이 값으로 횟수를 표시한다.
    occurrence_count: int = 1
    last_occurred_at: datetime | None = None
    # 대상 사용자의 현재 차단/자동제한 활성 여부. 리스트 상태 배지가 사건 발생 시점이 아닌
    # "지금 이 사용자에게 어떤 제재가 걸려 있는가" 를 표시하기 위함.
    # - user_blocked_now: blocked_until > NOW() OR subscription_status == 'blocked'.
    # - user_auto_throttled_now: anomaly_throttled_at IS NOT NULL.
    #   login_brute_force 타입이면 Redis 자동 락아웃 활성 여부도 OR 로 포함.
    # target_user_id 가 NULL 이거나 탈퇴 사용자면 둘 다 False.
    user_blocked_now: bool = False
    user_auto_throttled_now: bool = False
    # 주의 계정(watch list) 등록 여부. target_user_id가 있는 행만 의미가 있고,
    # NULL이면 항상 False (IP only 이벤트는 별 토글 불가).
    is_watched: bool = False


class AnomalyListResponse(BaseModel):
    """GET /api/v1/admin/anomaly — flat 페이지네이션 (AR27).

    같은 (target_user_id, type) 조합은 가장 최근 1건만 노출 — 그룹 누적 횟수는
    각 row 의 occurrence_count 로 동봉. 상세 드로어가 history 를 펼친다.
    """

    items: list[AnomalyEventItem]
    page: int
    per_page: int
    total: int


class AnomalyHistoryItem(BaseModel):
    """상세 드로어 history 한 줄 — 같은 그룹의 과거 탐지 기록."""

    id: int
    status: Literal["new", "reviewed", "actioned", "unblocked"]
    ip: str | None = None
    ua: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    reviewed_by_admin_id: int | None = None
    reviewed_at: datetime | None = None
    created_at: datetime


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
    # rapid_followup_questions / repeated_question 은 항상 True, 그 외는 False.
    auto_actioned: bool = False
    # 같은 (target_user_id, type) — target_user_id 가 NULL 이면 (ip, type) — 조합의
    # 모든 탐지 기록(가장 최근 순). 본 이벤트 자체도 포함된다.
    history: list[AnomalyHistoryItem] = Field(default_factory=list)
    # 차단 현황 — 대상 사용자가 있는 경우만 채워짐.
    user_subscription_status: Literal["free", "pro", "blocked"] | None = None
    user_blocked_until: datetime | None = None
    user_block_reason: str | None = None
    user_anomaly_throttled_at: datetime | None = None
    # login_brute_force 의 Redis 자동 락아웃 상태(이메일 기반). 대상 사용자가 있고
    # type 이 login_brute_force 인 경우에만 채워진다.
    # - login_auto_lockout_until: 1차 10분 잠금이 활성이면 만료 시각, 아니면 None.
    # - login_hard_locked: 2차(비번찾기 전까지 영구) 잠금 활성 여부.
    login_auto_lockout_until: datetime | None = None
    login_hard_locked: bool = False


class AnomalyMemoUpdateRequest(BaseModel):
    """PATCH /api/v1/admin/anomaly/{id}/memo 요청 — 메모만 갱신.

    빈 문자열은 NULL 로 정규화 (저장 시 ``""`` → None).
    """

    memo: str = Field(default="", max_length=2000, description="관리자 자유 메모 (0~2000자).")


__all__ = [
    "AnomalyEventItem",
    "AnomalyHistoryItem",
    "AnomalyListResponse",
    "AnomalyMarkReviewedRequest",
    "AnomalyMarkReviewedResponse",
    "AnomalyDetailResponse",
    "AnomalyMemoUpdateRequest",
]
