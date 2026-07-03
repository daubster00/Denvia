"""#113 질의응답 검토 Pydantic 스키마 — api/src/routers/admin/qa_review.py 와 1:1 매핑.

기존 qa_feedback(고객 피드백)과 완전히 분리된 별도 기능.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# =============================================================================
# 목록
# =============================================================================


class ReviewState(BaseModel):
    """qa_reviews 검토 상태(굿/베드 + 코멘트 + 검토완료)."""

    rating: Literal["good", "bad"] | None = None
    comment: str | None = None
    change_count: int = 0
    reviewed_at: str | None = None
    reviewed_by_name: str | None = None
    # 평가 메모(굿/베드 코멘트)를 작성한 관리자 계정. rated_by_admin_id → email.
    rated_by_name: str | None = None
    # 평가/메모를 마지막으로 저장한 시각(KST ISO). 모달에서 작성자 계정 옆에 표기.
    rated_at: str | None = None


class ReviewUserInfo(BaseModel):
    """질문 작성자 정보. viewer_grade 가 sub_operator 이면 응답에서 제외."""

    user_id: int | None = None
    email: str | None = None
    segment: str | None = None


class ReviewItem(BaseModel):
    qa_log_id: int
    question: str
    answer: str | None = None
    created_at: str | None = None
    review: ReviewState
    # sub_operator 응답에는 포함되지 않음(비노출).
    user: ReviewUserInfo | None = None


class EffectivePeriod(BaseModel):
    date_from: str
    date_to: str
    clamped: bool
    max_lookback_days: int


class ReviewListResponse(BaseModel):
    items: list[ReviewItem]
    total: int
    page: int
    page_size: int
    viewer_grade: str | None = None
    effective_period: EffectivePeriod


# =============================================================================
# 통계
# =============================================================================


class ReviewSummary(BaseModel):
    good_count: int
    bad_count: int
    reviewed_count: int
    good_ratio: float | None = None


class ReviewSeriesItem(BaseModel):
    bucket: str
    good: int
    bad: int
    good_ratio: float | None = None


class ReviewSummaryResponse(BaseModel):
    summary: ReviewSummary
    series: list[ReviewSeriesItem]


# =============================================================================
# 요청 / 액션 응답
# =============================================================================


class RateRequest(BaseModel):
    # None = 평가 해제(#113 모달 SET 시맨틱). comment = 평가 메모(굿/베드 공통).
    rating: Literal["good", "bad"] | None = None
    comment: str | None = Field(default=None, max_length=2000)


class CommentRequest(BaseModel):
    comment: str = Field(min_length=1, max_length=2000)


class CompleteRequest(BaseModel):
    reviewed: bool


class BulkDeleteRequest(BaseModel):
    qa_log_ids: list[int] = Field(min_length=1)


class ReviewActionResponse(BaseModel):
    """rate/comment/complete 공통 응답 — 갱신된 review 상태."""

    qa_log_id: int
    rating: Literal["good", "bad"] | None = None
    comment: str | None = None
    change_count: int = 0
    reviewed_at: str | None = None
    reviewed: bool | None = None
    # 평가/메모를 마지막으로 저장한 시각(KST ISO). 모달 저장 후 작성일자 표기용.
    rated_at: str | None = None


class BulkDeleteResponse(BaseModel):
    deleted: int


# =============================================================================
# 설정
# =============================================================================


class SettingsResponse(BaseModel):
    sub_operator_max_lookback_days: int


class SettingsUpdateRequest(BaseModel):
    sub_operator_max_lookback_days: int = Field(ge=1, le=365)
