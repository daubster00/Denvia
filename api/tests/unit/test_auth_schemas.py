"""인증 스키마 유효성 검증 단위 테스트."""

import pytest
from pydantic import ValidationError

from api.src.schemas.auth import (
    FindPasswordRequest,
    FindIdRequest,
    FindIdResponse,
    PasswordChangeRequest,
    SignupRequest,
    SmsSendRequest,
    SmsVerifyRequest,
    SegmentRequest,
)


# ── SmsSendRequest ────────────────────────────────────────────────────────────

def test_sms_send_valid_phone():
    r = SmsSendRequest(phone="010-1234-5678", purpose="signup")
    assert r.phone == "01012345678"


def test_sms_send_phone_raw_digits():
    r = SmsSendRequest(phone="01012345678", purpose="signup")
    assert r.phone == "01012345678"


def test_sms_send_invalid_phone():
    with pytest.raises(ValidationError):
        SmsSendRequest(phone="0201234567", purpose="signup")


# ── SmsVerifyRequest ──────────────────────────────────────────────────────────

def test_sms_verify_valid():
    r = SmsVerifyRequest(phone="01012345678", code="123456", purpose="signup")
    assert r.code == "123456"


def test_sms_verify_invalid_code():
    with pytest.raises(ValidationError):
        SmsVerifyRequest(phone="01012345678", code="12345", purpose="signup")

    with pytest.raises(ValidationError):
        SmsVerifyRequest(phone="01012345678", code="abc123", purpose="signup")


# ── SignupRequest ─────────────────────────────────────────────────────────────

def test_signup_valid():
    r = SignupRequest(
        email="User@Example.com",
        password="password123",
        phone="01012345678",
        phone_verification_token="abc",
    )
    assert r.email == "user@example.com"


def test_signup_short_password():
    with pytest.raises(ValidationError):
        SignupRequest(
            email="user@example.com",
            password="short",
            phone="01012345678",
            phone_verification_token="tok",
        )


def test_signup_invalid_email():
    with pytest.raises(ValidationError):
        SignupRequest(
            email="not_an_email",
            password="password123",
            phone="01012345678",
            phone_verification_token="tok",
        )


# ── SegmentRequest ────────────────────────────────────────────────────────────

def test_segment_doctor_with_years():
    r = SegmentRequest(segment="doctor", years_of_experience=5)
    assert r.years_of_experience == 5


def test_segment_student_without_years():
    r = SegmentRequest(segment="student_other")
    assert r.years_of_experience is None


def test_segment_invalid_years():
    with pytest.raises(ValidationError):
        SegmentRequest(segment="doctor", years_of_experience=0)

    with pytest.raises(ValidationError):
        SegmentRequest(segment="doctor", years_of_experience=51)


def test_segment_invalid_value():
    with pytest.raises(ValidationError):
        SegmentRequest(segment="unknown")


# ── FindPasswordRequest ───────────────────────────────────────────────────────

def test_find_password_valid():
    r = FindPasswordRequest(email="User@Example.com", phone="010-1234-5678")
    assert r.email == "user@example.com"
    assert r.phone == "01012345678"


def test_find_password_invalid_phone():
    with pytest.raises(ValidationError):
        FindPasswordRequest(email="a@b.com", phone="0201234567")


def test_find_password_invalid_email():
    with pytest.raises(ValidationError):
        FindPasswordRequest(email="not_email", phone="01012345678")


# ── FindIdRequest ─────────────────────────────────────────────────────────────

def test_find_id_valid():
    r = FindIdRequest(phone_verification_token="some_token_abc")
    assert r.phone_verification_token == "some_token_abc"


# ── PasswordChangeRequest ─────────────────────────────────────────────────────

def test_password_change_valid():
    r = PasswordChangeRequest(new_password="newpass99")
    assert r.new_password == "newpass99"


def test_password_change_too_short():
    with pytest.raises(ValidationError) as exc_info:
        PasswordChangeRequest(new_password="short")
    assert "PASSWORD_TOO_SHORT" in str(exc_info.value)
