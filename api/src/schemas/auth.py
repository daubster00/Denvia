"""인증 관련 Pydantic 스키마 — snake_case, 래퍼 금지 (architecture.md §703)."""

from datetime import date
from typing import Literal
from pydantic import BaseModel, Field, field_validator
import re


def _empty_to_none(v: str | None) -> str | None:
    """빈 문자열·공백만 입력은 NULL로 정규화 — me.py와 동일 규칙."""
    if v is None:
        return None
    stripped = v.strip()
    return stripped if stripped else None


class SessionUserResponse(BaseModel):
    """GET /api/v1/me 응답 스키마 — 8 필드 flat 구조 (Story 1.7 is_social 추가)."""

    user_id: int
    email: str
    role: str
    subscription_status: str
    segment: str | None
    years_of_experience: int | None
    must_reset_password: bool
    # Story 1.7 — 소셜 전용 가입 여부(password_hash IS NULL).
    # ConfirmWithdrawPopup이 비밀번호 입력 vs SMS OTP 분기를 위해 사용한다.
    is_social: bool


# ── SMS ──────────────────────────────────────────────────────────────────────

class SmsSendRequest(BaseModel):
    phone: str
    purpose: Literal["signup", "find_id", "find_password", "phone_change", "admin_signup"]

    @field_validator("phone")
    @classmethod
    def phone_format(cls, v: str) -> str:
        cleaned = re.sub(r"[^0-9]", "", v)
        if not re.match(r"^010\d{8}$", cleaned):
            raise ValueError("올바른 휴대폰 번호를 입력하세요.")
        return cleaned


class SmsSendResponse(BaseModel):
    sent_at: str
    cooldown_seconds: int
    max_retries: int
    debug_code: str | None = None


class SmsVerifyRequest(BaseModel):
    phone: str
    code: str
    purpose: Literal["signup", "find_id", "find_password", "phone_change", "admin_signup"]

    @field_validator("phone")
    @classmethod
    def phone_format(cls, v: str) -> str:
        cleaned = re.sub(r"[^0-9]", "", v)
        if not re.match(r"^010\d{8}$", cleaned):
            raise ValueError("올바른 휴대폰 번호를 입력하세요.")
        return cleaned

    @field_validator("code")
    @classmethod
    def code_format(cls, v: str) -> str:
        if not re.match(r"^\d{6}$", v):
            raise ValueError("6자리 숫자를 입력하세요.")
        return v


class SmsVerifyResponse(BaseModel):
    phone_verification_token: str


# ── Signup ────────────────────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    """이메일 회원가입 요청.

    필수: email, password, phone, phone_verification_token.
    선택: name, birthdate, gender, postcode, address_road, address_detail.
    선택 필드의 검증 규칙은 ProfileUpdateRequest와 동일하게 유지(SSOT).
    """

    email: str
    password: str
    phone: str
    phone_verification_token: str
    # 선택 입력 — 빈 문자열은 NULL로 정규화.
    name: str | None = None
    birthdate: date | None = None
    gender: Literal["male", "female"] | None = None
    postcode: str | None = None
    address_road: str | None = None
    address_detail: str | None = None

    @field_validator("phone")
    @classmethod
    def phone_format(cls, v: str) -> str:
        cleaned = re.sub(r"[^0-9]", "", v)
        if not re.match(r"^010\d{8}$", cleaned):
            raise ValueError("올바른 휴대폰 번호를 입력하세요.")
        return cleaned

    @field_validator("email")
    @classmethod
    def email_format(cls, v: str) -> str:
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("올바른 이메일을 입력하세요.")
        return v.lower().strip()

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("PASSWORD_TOO_SHORT")
        return v

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

    @field_validator("birthdate")
    @classmethod
    def _birthdate_sane_range(cls, v: date | None) -> date | None:
        if v is None:
            return None
        from datetime import date as _date
        today = _date.today()
        if v.year < 1900 or v > today:
            raise ValueError("생년월일이 올바르지 않습니다.")
        return v


# ── Segment ───────────────────────────────────────────────────────────────────

# ── Login ─────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str
    persist_session: bool = False

    @field_validator("email")
    @classmethod
    def email_format(cls, v: str) -> str:
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("올바른 이메일을 입력하세요.")
        return v.lower().strip()


class LoginResponse(BaseModel):
    user_id: int
    email: str
    role: str
    subscription_status: str


# ── Segment ───────────────────────────────────────────────────────────────────

# ── Password Reset / ID Recovery ─────────────────────────────────────────────

def _validate_password_min_length(v: str) -> str:
    if len(v) < 8:
        raise ValueError("PASSWORD_TOO_SHORT")
    return v


class FindPasswordRequest(BaseModel):
    email: str
    phone: str

    @field_validator("email")
    @classmethod
    def email_format(cls, v: str) -> str:
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("올바른 이메일을 입력하세요.")
        return v.lower().strip()

    @field_validator("phone")
    @classmethod
    def phone_format(cls, v: str) -> str:
        cleaned = re.sub(r"[^0-9]", "", v)
        if not re.match(r"^010\d{8}$", cleaned):
            raise ValueError("올바른 휴대폰 번호를 입력하세요.")
        return cleaned


class FindPasswordResponse(BaseModel):
    """비밀번호 찾기 응답.

    일반 가입자·불일치는 linked_providers=[] (계정 열거 방지 유지).
    소셜 전용 계정만 연결된 provider 리스트를 반환해 프론트가 안내 + 소셜 로그인 버튼을 노출.
    """

    ok: bool = True
    linked_providers: list[Literal["kakao", "google", "naver"]] = []


class FindIdRequest(BaseModel):
    phone_verification_token: str


class FindIdResponse(BaseModel):
    email_masked: str | None
    signup_method: Literal["email", "kakao", "google", "naver", "social"] | None


class PasswordChangeRequest(BaseModel):
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        return _validate_password_min_length(v)


# ── Segment ───────────────────────────────────────────────────────────────────

_VALID_SEGMENTS = {"doctor", "hygienist", "student_other"}


class SegmentRequest(BaseModel):
    segment: Literal["doctor", "hygienist", "student_other"]
    years_of_experience: int | None = None

    @field_validator("years_of_experience")
    @classmethod
    def years_range(cls, v: int | None) -> int | None:
        if v is not None and not (1 <= v <= 50):
            raise ValueError("연차는 1~50 사이여야 합니다.")
        return v


# ── OAuth 3종 (Story 1.6) ────────────────────────────────────────────────────

class OAuthCompleteRequest(BaseModel):
    # 빈 문자열 조기 거부(422). 실제 토큰은 secrets.token_urlsafe(32) 결과이나,
    # 테스트 mock은 짧은 상수를 쓰므로 min_length=1로만 강제하고 실 검증은 서비스 레이어에 위임.
    signup_pending_token: str = Field(min_length=1, max_length=128)
    phone: str
    phone_verification_token: str = Field(min_length=1, max_length=128)

    @field_validator("phone")
    @classmethod
    def phone_format(cls, v: str) -> str:
        cleaned = re.sub(r"[^0-9]", "", v)
        if not re.match(r"^010\d{8}$", cleaned):
            raise ValueError("올바른 휴대폰 번호를 입력하세요.")
        return cleaned
