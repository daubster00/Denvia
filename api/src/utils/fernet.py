"""빌링키 Fernet 암호화 유틸 (AR21, NFR-S2).

BILLING_KEY_ENC_KEY 환경변수(base64 urlsafe 32B)가 없으면 즉시 오류 발생.
복호화 결과(평문)는 로그·API 응답·Sentry에 절대 출력 금지.
"""

import os

from cryptography.fernet import Fernet


def get_fernet() -> Fernet:
    """환경변수에서 Fernet 키를 로드한다. 키 누락 시 즉시 KeyError 발생."""
    key = os.environ["BILLING_KEY_ENC_KEY"]  # 누락 시 KeyError — 의도된 빠른 실패
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_billing_key(plain: str) -> bytes:
    """평문 빌링키를 Fernet으로 암호화하여 바이트를 반환한다."""
    return get_fernet().encrypt(plain.encode())


def decrypt_billing_key(token: bytes) -> str:
    """암호화된 빌링키 토큰을 복호화한다.
    반환값(평문)을 로그·API 응답에 노출하지 말 것 (NFR-S2).
    """
    return get_fernet().decrypt(token).decode()
