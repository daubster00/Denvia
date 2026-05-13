"""Admin 운영 환불 v1.1 — Pydantic 스키마 (ADR-0001 편차 #5, Story 9.3 v1.1).

v1.0 자가 환불 폼(`manual_refund_queue` 승인 큐 기반)은 Story 3.6 v1.1 Phase 4에서 삭제됨.
본 모듈은 v1.1 운영 환불 — 관리자가 결제 건당 환불 금액을 직접 입력하는 부분/전액 환불 —
스키마를 담는다.

본 모듈 스키마:
- T6: `RefundQuoteResponse` — 환불 입력 화면 진입 시 참고 계산값 묶음.
- T9: `RefundCreateRequest` / `RefundCreateResponse` — 실제 환불 실행 요청/응답.
- T10: `RefundListResponse` / `RefundListItem` — 결제별 환불 이력 목록(시계열).

DTO 설계 노트:
- 모든 금액은 원(KRW) 정수. 토스 페이먼츠 API와 1:1.
- `refundable_balance = payment_amount - refunded_total`. 프론트는 본 값을 입력 가드 상한으로
  사용한다. 0 이하면 환불 버튼 비활성. ADR 편차 #5 (c) 가드레일 1·2 대응.
- `prorated_amount` 공식: `payment_amount × (남은 일수 ÷ 총 구독 일수)`, 원 단위 내림
  (소비자에게 불리하지 않게). 단순 권장값이며 강제하지 않는다 — 관리자가 자유 입력.
- `is_within_cooling_off`는 (결제 후 7일 이내 AND 해당 구독 기간 동안 질문 0건) 모두 충족 시 True.
  True여도 사용자가 셀프 청약철회를 안 한 케이스(예: 알림톡 미수신·해지 미요청)에서 관리자가
  대행 처리할 수 있도록 표기만 한다 — 자동 적용 아님.
- `next_refund_sequence`는 동일 결제 건 내 다음 환불의 1-based 시퀀스. 동시 환불 충돌은 DB의
  `uq_refunds_payment_sequence`로 차단되며, 본 필드는 단순 표기/멱등 키 조립 참고용.
- `RefundCreateRequest.reason_category`는 5종 enum과 1:1 매칭 (DB enum 값 그대로).
- `RefundCreateRequest.memo` 최대 500자 — 토스 페이먼츠 cancelReason은 200자 상한이지만
  본 시스템 내부 보존 한도는 500자로 두고 PG 호출 시점에만 200자로 잘라 전달한다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


RefundReasonCategory = Literal[
    "customer_complaint",
    "duplicate_payment",
    "system_error",
    "special_mid_cancel",
    "other",
]


class RefundQuoteResponse(BaseModel):
    """GET /api/v1/admin/payments/{payment_id}/refund-quote 응답.

    관리자가 환불 입력 화면에 진입할 때 1회 호출. 모든 참고 계산값을 묶어 반환한다.
    프론트는 본 응답으로 입력 가드(상한·하한)·권장값 표시·청약철회 표기·다음 sequence를
    모두 구성한다.
    """

    payment_id: int = Field(description="대상 결제 ID.")
    user_id: int = Field(description="결제 소유 사용자 ID (마스킹은 별도 엔드포인트 책임).")

    payment_amount: int = Field(
        ge=0,
        description="결제 시점 원금(KRW). `payments.amount_krw` 스냅샷.",
    )
    refunded_total: int = Field(
        ge=0,
        description="기존 부분환불 누적 합계(KRW). `refunds.cancel_amount` SUM.",
    )
    refundable_balance: int = Field(
        ge=0,
        description=(
            "환불 가능 잔액(KRW) = payment_amount - refunded_total. "
            "프론트는 본 값을 입력 가드 상한으로 사용한다. 0이면 환불 버튼 비활성."
        ),
    )

    full_refund_amount: int = Field(
        ge=0,
        description="전액 환불 권장값(KRW) — refundable_balance와 동일. 표기 일관성용 별칭.",
    )
    prorated_amount: int = Field(
        ge=0,
        description=(
            "일할 환불 권장값(KRW). 공식: payment_amount × (days_remaining ÷ total_days), "
            "원 단위 내림. 단순 권장값이며 강제 아님."
        ),
    )
    prorated_days_remaining: int = Field(
        ge=0,
        description="구독 기간 중 남은 일수(일할 계산 분자).",
    )
    prorated_total_days: int = Field(
        ge=1,
        description="해당 결제의 총 구독 일수(일할 계산 분모). 1 이상 보장.",
    )

    is_within_cooling_off: bool = Field(
        description=(
            "청약철회 적용 가능 여부. (결제 후 7일 이내) AND (해당 구독 기간 동안 질문 0건) "
            "모두 충족 시 True. True면 프론트가 '청약철회 적용 가능' 배지를 표기한다 — 자동 적용 아님."
        ),
    )
    cooling_off_days_since_charge: int = Field(
        ge=0,
        description="결제 후 경과 일수 (청약철회 7일 판정 근거 표시).",
    )
    cooling_off_qa_count: int = Field(
        ge=0,
        description="해당 구독 기간 동안 사용자 질문 누적 건수 (청약철회 0건 판정 근거 표시).",
    )

    next_refund_sequence: int = Field(
        ge=1,
        description=(
            "동일 결제 건 내 다음 환불의 1-based 시퀀스. "
            "idempotency_key 조립 참고용 (refund:{payment_id}:manual:{sequence})."
        ),
    )
    existing_refunds_count: int = Field(
        ge=0,
        description="이미 처리된 부분환불 row 수. UI 표기용(예: '이 결제는 N회 환불됨').",
    )

    subscription_period_start: datetime | None = Field(
        default=None,
        description="해당 결제로 시작된 구독 기간 시작 시각(KST aware). 일할 계산 기준일.",
    )
    subscription_period_end: datetime | None = Field(
        default=None,
        description="해당 결제로 끝나는 구독 기간 종료 시각(KST aware). 일할 계산 만료일.",
    )


class RefundCreateRequest(BaseModel):
    """POST /api/v1/admin/payments/{payment_id}/refunds 요청.

    관리자가 환불 입력 화면에서 금액·사유·메모를 자유 입력해 제출한다.
    `cancel_amount` 상한 검증은 서비스 레이어에서 `payments.amount_krw - SUM(refunds.cancel_amount)`로
    재계산되므로 본 스키마는 0 초과만 보장한다 (DB의 `ck_refunds_cancel_amount_positive`와 일치).
    """

    cancel_amount: int = Field(
        gt=0,
        description=(
            "이번 환불 금액(KRW). 0 초과. 잔액 초과 여부는 서비스 레이어에서 재검증한다."
        ),
    )
    reason_category: RefundReasonCategory = Field(
        description=(
            "환불 사유 분류(5종 enum). DB의 `refund_reason_category_enum`과 동일 값. "
            "프론트 라디오/드롭다운 매핑."
        ),
    )
    memo: str | None = Field(
        default=None,
        max_length=500,
        description=(
            "관리자 자유 메모. 최대 500자. PG cancelReason으로는 앞 200자만 전달된다 "
            "(토스 페이먼츠 API 한도). 본 메모는 `refunds.memo`에 원문 보존."
        ),
    )


class RefundCreateResponse(BaseModel):
    """POST /api/v1/admin/payments/{payment_id}/refunds 응답.

    환불 INSERT 성공 시 프론트가 영수증·이력 화면을 즉시 갱신할 수 있도록 핵심 식별자만
    반환한다. 잔액·후속 sequence 등 파생값은 환불 직후 quote를 재호출해 가져온다.
    """

    refund_id: int = Field(description="`refunds.id` — 새로 생성된 환불 row.")
    refund_sequence: int = Field(
        ge=1,
        description="동일 결제 건 내 1-based 시퀀스. 멱등 키 조립과 일치.",
    )
    cancel_amount: int = Field(
        gt=0,
        description="이번 환불 금액(KRW). 요청 값과 동일하지만 응답 일관성용으로 echo.",
    )
    refunded_at: datetime = Field(
        description="환불 처리 시각(UTC). 알림톡 effective_at은 본 값을 KST로 변환해 표기한다.",
    )


class RefundListItem(BaseModel):
    """결제별 환불 이력 1건. `RefundListResponse.items[]` 원소.

    `admin_email_masked`는 환불을 처리한 관리자 이메일을 부분 마스킹한 값
    (analytics_service._mask_email 동일 규칙). 본 응답은 관리자 전용이지만
    이력 화면이 사용자에게 노출 가능한 영수증 도메인과 시각적으로 인접해
    일관된 마스킹 정책을 유지하기 위해 마스킹된 값을 반환한다 — 일관성·운영 사고 시 캡쳐 공유 안전성 모두 고려.
    """

    id: int = Field(description="`refunds.id`.")
    refund_sequence: int = Field(
        ge=1,
        description="동일 결제 건 내 1-based 시퀀스. 시계열 정렬과 일치(asc).",
    )
    cancel_amount: int = Field(
        gt=0,
        description="해당 환불 row의 환불 금액(KRW).",
    )
    reason_category: RefundReasonCategory = Field(
        description="환불 사유 분류(5종 enum). 한국어 라벨 매핑은 프론트 책임.",
    )
    memo: str | None = Field(
        default=None,
        description=(
            "관리자 자유 메모 원문. None이면 메모 미입력. 관리자 화면에서만 노출."
        ),
    )
    admin_email_masked: str = Field(
        description=(
            "환불을 처리한 관리자 이메일 마스킹값. 예: `a****@denvia.local`. "
            "마스킹 규칙은 `utils.mask.mask_email`와 동일."
        ),
    )
    created_at: datetime = Field(
        description="환불 row 생성 시각(UTC). 프론트는 KST로 변환해 표기한다.",
    )


class RefundListResponse(BaseModel):
    """GET /api/v1/admin/payments/{payment_id}/refunds 응답.

    단일 결제에 묶인 모든 환불 row를 시계열(created_at ASC) 순으로 반환한다.
    부분환불 다회 누적 시 1→2→3 순으로 표시되어 관리자가 화면에서 누적 흐름을
    자연스럽게 따라갈 수 있다. 페이지네이션은 도입하지 않는다 — 단일 결제에 묶이는
    환불 row 수는 본 정책상 매우 적다(통상 1~2건, 최대 N건도 두 자릿수 미만 예상).

    `total`은 items 길이와 동일하며 클라이언트가 별도 카운트 쿼리 없이 사용할 수
    있도록 echo한다.
    """

    items: list[RefundListItem] = Field(
        description="환불 이력 (created_at ASC 정렬).",
    )
    total: int = Field(
        ge=0,
        description="환불 row 총 개수. items 길이와 동일.",
    )


__all__ = [
    "RefundCreateRequest",
    "RefundCreateResponse",
    "RefundListItem",
    "RefundListResponse",
    "RefundQuoteResponse",
    "RefundReasonCategory",
]
