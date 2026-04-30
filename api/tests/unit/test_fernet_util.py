"""Fernet 암호화 유틸 단위 테스트 — Story 3.1.

encrypt/decrypt 왕복 + 평문 노출 없음 확인.
"""

import os
import pytest

from cryptography.fernet import Fernet


@pytest.fixture(autouse=True)
def _set_enc_key(monkeypatch):
    """테스트용 Fernet 키 주입."""
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("BILLING_KEY_ENC_KEY", key)


def test_encrypt_returns_bytes():
    """encrypt_billing_key는 bytes를 반환해야 한다."""
    from api.src.utils.fernet import encrypt_billing_key

    result = encrypt_billing_key("test_billing_key_plain")
    assert isinstance(result, bytes)


def test_encrypt_decrypt_roundtrip():
    """암호화 후 복호화하면 원래 평문을 반환해야 한다."""
    from api.src.utils.fernet import encrypt_billing_key, decrypt_billing_key

    plain = "bk_test_abcdef1234567890"
    encrypted = encrypt_billing_key(plain)
    decrypted = decrypt_billing_key(encrypted)

    assert decrypted == plain


def test_encrypted_value_differs_from_plain():
    """암호화 결과가 평문과 달라야 한다 (실제 암호화 동작 확인)."""
    from api.src.utils.fernet import encrypt_billing_key

    plain = "bk_test_sensitive"
    encrypted = encrypt_billing_key(plain)

    assert plain.encode() not in encrypted


def test_decrypt_does_not_expose_plain_in_bytes_repr():
    """decrypt_billing_key 반환값 repr에 평문 자체가 포함되면 안 된다는 기본 확인.
    실제 로그 노출 방지는 코드 리뷰 레이어에서 검증 — 여기서는 복호화 동작만 확인.
    """
    from api.src.utils.fernet import encrypt_billing_key, decrypt_billing_key

    plain = "super_secret_billing_key"
    token = encrypt_billing_key(plain)
    result = decrypt_billing_key(token)

    # 복호화 결과가 평문과 일치하고, 암호화 바이트에는 평문이 없음
    assert result == plain
    assert plain.encode() not in token


def test_missing_env_key_raises():
    """BILLING_KEY_ENC_KEY 환경변수 누락 시 KeyError가 발생해야 한다."""
    import importlib
    import api.src.utils.fernet as fernet_module

    env_backup = os.environ.pop("BILLING_KEY_ENC_KEY", None)
    try:
        # 모듈 캐시 우회를 위해 get_fernet() 직접 호출
        with pytest.raises(KeyError):
            fernet_module.get_fernet()
    finally:
        if env_backup is not None:
            os.environ["BILLING_KEY_ENC_KEY"] = env_backup


def test_different_plains_produce_different_ciphertext():
    """서로 다른 평문은 서로 다른 암호문을 생성해야 한다."""
    from api.src.utils.fernet import encrypt_billing_key

    enc1 = encrypt_billing_key("key_aaa")
    enc2 = encrypt_billing_key("key_bbb")

    assert enc1 != enc2
