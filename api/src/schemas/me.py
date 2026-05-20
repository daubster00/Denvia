"""Me 관련 Pydantic 스키마 — Story 2.3 / 4.3 / 4.4."""

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, field_validator


class QuotaResponse(BaseModel):
    subscription_status: str
    daily_limit: int
    used_today: int
    remaining: int
    reset_at: str
    show_upgrade_prompt: bool
    show_subscribe_button: bool
    delay_seconds: float


class UsageSummaryResponse(BaseModel):
    """GET /api/v1/me/usage-summary 응답 — Story 4.3 마이페이지."""

    month_question_count: int
    daily_used: int
    daily_limit: int
    daily_remaining: int
    daily_reset_at: str  # ISO-8601 KST (+09:00)
    subscription_status: str  # free | pro | admin
    segment: str | None
    years_of_experience: int | None
    show_subscribe_button: bool


PaymentStatusLiteral = Literal[
    "pending", "success", "failed", "refunded", "refund_pending"
]


class PaymentHistoryItem(BaseModel):
    """GET /api/v1/me/payments items[i] — Story 4.4 (FR27 / F-402)."""

    payment_id: int
    charged_at: str | None  # ISO 8601 (NULL은 status='pending')
    subscription_period_start: str | None
    subscription_period_end: str | None
    buyer_email: str
    card_last4: str | None
    card_company: str | None
    amount_krw: int
    provider_order_id: str
    status: PaymentStatusLiteral


class PaymentHistoryResponse(BaseModel):
    """GET /api/v1/me/payments 응답 (AR27 flat 페이지네이션) — Story 4.4."""

    items: list[PaymentHistoryItem]
    page: int
    per_page: int
    total: int


# ── Story 1.7: 회원 탈퇴 ─────────────────────────────────────────────────────


class WithdrawOtpSendResponse(BaseModel):
    """POST /api/v1/me/withdraw/send-otp 응답 — 마스킹된 휴대폰만 노출."""

    masked_phone: str


class WithdrawOtpVerifyRequest(BaseModel):
    code: str


class WithdrawOtpVerifyResponse(BaseModel):
    phone_verification_token: str


class WithdrawRequest(BaseModel):
    """DELETE /api/v1/me 요청 — 자체 가입자는 password, 소셜 가입자는 token."""

    password: str | None = None
    phone_verification_token: str | None = None


# ── 회원정보 수정 (마이페이지 /my/profile) ──────────────────────────────────


def _empty_to_none(v: str | None) -> str | None:
    """빈 문자열·공백만 입력은 NULL로 정규화 (IS NULL 쿼리 일관성)."""
    if v is None:
        return None
    stripped = v.strip()
    return stripped if stripped else None


class ProfileResponse(BaseModel):
    """GET /api/v1/me/profile 응답.

    `/me` 응답은 SessionBootstrap이 빈번히 호출하므로 PII를 섞지 않고
    분리한다. is_social은 password_hash IS NULL로 파생.

    `segment`/`years_of_experience`는 마이페이지에서 **읽기 전용**으로 표시한다
    (변경은 관리자만 — AR34). PATCH 요청에는 포함되지 않는다.
    """

    email: str
    name: str | None
    phone: str | None
    phone_verified: bool
    is_social: bool
    postcode: str | None
    address_road: str | None
    address_detail: str | None
    # 인구통계 (선택 입력)
    gender: Literal["male", "female"] | None
    birthdate: date | None
    # 마케팅 활용 동의 — 알림톡·SMS·이메일 통합 단일 토글.
    # `marketing_consent`는 `marketing_consent_at IS NOT NULL`로 파생한 편의 필드.
    marketing_consent: bool
    marketing_consent_at: str | None  # ISO 8601 (UTC)
    # 가입유형/연차 — 읽기 전용 표시. 변경은 관리자만.
    segment: Literal["doctor", "hygienist", "student_other"] | None
    years_of_experience: int | None


class ProfileUpdateRequest(BaseModel):
    """PATCH /api/v1/me/profile 요청 — 모든 필드 optional, 변경분만 전송 권장.

    phone이 현재 값과 다르면 phone_verification_token이 필수다(서비스 레이어에서 검증).

    `segment`/`years_of_experience`는 본 엔드포인트에서 수정할 수 없다(AR34).
    """

    name: str | None = None
    phone: str | None = None
    phone_verification_token: str | None = None
    postcode: str | None = None
    address_road: str | None = None
    address_detail: str | None = None
    gender: Literal["male", "female"] | None = None
    birthdate: date | None = None
    marketing_consent: bool | None = None

    @field_validator("name", "address_road", "address_detail")
    @classmethod
    def _trim_or_none(cls, v: str | None) -> str | None:
        return _empty_to_none(v)

    @field_validator("postcode")
    @classmethod
    def _postcode_digits(cls, v: str | None) -> str | None:
        v = _empty_to_none(v)
        if v is None:
            return None
        if not re.match(r"^\d{5,10}$", v):
            raise ValueError("우편번호 형식이 올바르지 않습니다.")
        return v

    @field_validator("phone")
    @classmethod
    def _phone_or_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = re.sub(r"[^0-9]", "", v)
        if not cleaned:
            return None
        if not re.match(r"^010\d{8}$", cleaned):
            raise ValueError("올바른 휴대폰 번호를 입력하세요.")
        return cleaned

    @field_validator("birthdate")
    @classmethod
    def _birthdate_sane_range(cls, v: date | None) -> date | None:
        if v is None:
            return None
        # 1900-01-01 이전, 또는 미래 일자는 입력 오류로 거부.
        from datetime import date as _date
        today = _date.today()
        if v.year < 1900 or v > today:
            raise ValueError("생년월일이 올바르지 않습니다.")
        return v


class PasswordChangeWithCurrentRequest(BaseModel):
    """POST /api/v1/me/password/change — 기존 비밀번호 확인 필수.

    `PasswordChangeRequest`(임시PW용)와 별개. 평범한 이메일 가입자는 이 엔드포인트로,
    소셜·임시PW 사용자는 기존 `/me/password`로 분리해 보안 경로를 명확히 한다.
    """

    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("PASSWORD_TOO_SHORT")
        return v
