"""argon2 유틸 단위 테스트."""

import pytest
from api.src.utils.argon2 import hash_password, verify_password


def test_hash_password_returns_string():
    hashed = hash_password("password123")
    assert isinstance(hashed, str)
    assert hashed.startswith("$argon2")


def test_verify_password_correct():
    hashed = hash_password("mypassword")
    assert verify_password("mypassword", hashed) is True


def test_verify_password_wrong():
    hashed = hash_password("mypassword")
    assert verify_password("wrongpassword", hashed) is False


def test_verify_password_invalid_hash():
    assert verify_password("anything", "not_a_hash") is False


def test_hash_is_unique():
    h1 = hash_password("same")
    h2 = hash_password("same")
    assert h1 != h2  # argon2 salt 자동 부여
