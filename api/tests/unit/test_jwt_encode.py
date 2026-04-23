"""JWT encode 유틸 단위 테스트."""

import pytest
from api.src.utils.jwt import encode_session_jwt, decode_session_jwt


def test_encode_decode_roundtrip():
    token = encode_session_jwt(user_id=42, role="user", subscription_status="free")
    payload = decode_session_jwt(token)
    assert payload["sub"] == 42
    assert payload["role"] == "user"
    assert payload["sub_status"] == "free"


def test_persist_false_produces_shorter_exp():
    import jwt as pyjwt
    from api.src.settings import settings

    token_short = encode_session_jwt(1, "user", "free", persist=False)
    token_long = encode_session_jwt(1, "user", "free", persist=True)

    p_short = pyjwt.decode(token_short, settings.denvia_jwt_secret, algorithms=[settings.denvia_jwt_algorithm])
    p_long = pyjwt.decode(token_long, settings.denvia_jwt_secret, algorithms=[settings.denvia_jwt_algorithm])

    assert p_long["exp"] > p_short["exp"]


def test_encode_with_admin_role():
    token = encode_session_jwt(user_id=1, role="admin", subscription_status="free")
    payload = decode_session_jwt(token)
    assert payload["role"] == "admin"
