"""argon2id 비밀번호 해싱 유틸리티 (AR20)."""

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

_ph = PasswordHasher()


def hash_password(plaintext: str) -> str:
    """argon2id로 비밀번호를 해싱한다."""
    return _ph.hash(plaintext)


def verify_password(plaintext: str, hashed: str) -> bool:
    """비밀번호를 검증한다. 불일치 또는 오류 시 False 반환."""
    try:
        return _ph.verify(hashed, plaintext)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
