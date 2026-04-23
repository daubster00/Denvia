"""인증 관련 Pydantic 스키마 — snake_case, 래퍼 금지 (architecture.md §703)."""

from typing import Literal
from pydantic import BaseModel, field_validator
import re


class SessionUserResponse(BaseModel):
    """GET /api/v1/me 응답 스키마 — 7 필드 flat 구조."""

    user_id: int
    email: str
    role: str
    subscription_status: str
    segment: str | None
    years_of_experience: int | None
    must_reset_password: bool


# ── SMS ──────────────────────────────────────────────────────────────────────

class SmsSendRequest(BaseModel):
    phone: str
    purpose: Literal["signup", "find_id", "find_password"]

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


class SmsVerifyRequest(BaseModel):
    phone: str
    code: str
    purpose: Literal["signup", "find_id", "find_password"]

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
    email: str
    password: str
    phone: str
    phone_verification_token: str

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


class FindIdRequest(BaseModel):
    phone_verification_token: str


class FindIdResponse(BaseModel):
    email_masked: str | None
    signup_method: Literal["email", "social"] | None


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
