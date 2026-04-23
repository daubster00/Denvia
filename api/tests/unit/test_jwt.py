"""decode_session_jwt 유닛 테스트."""

import time
import pytest
import jwt as pyjwt

from api.src.utils.jwt import decode_session_jwt, JWTDecodeError, SessionExpired
from api.src.settings import settings


def _make_token(payload: dict, secret: str | None = None, algorithm: str = "HS256") -> str:
    """테스트용 JWT 토큰 생성기. PyJWT 표준: sub는 문자열."""
    return pyjwt.encode(payload, secret or settings.denvia_jwt_secret, algorithm=algorithm)


class TestDecodeSessionJwt:
    def test_유효한_토큰_성공(self):
        payload = {
            "sub": "1",  # JWT 표준: sub는 문자열
            "role": "user",
            "sub_status": "free",
            "exp": int(time.time()) + 3600,
        }
        token = _make_token(payload)
        result = decode_session_jwt(token)
        assert result["sub"] == 1  # decode 시 int 변환됨
        assert result["role"] == "user"

    def test_만료_토큰_SessionExpired(self):
        payload = {
            "sub": "2",
            "role": "user",
            "sub_status": "free",
            "exp": int(time.time()) - 10,  # 과거 시각
        }
        token = _make_token(payload)
        with pytest.raises(SessionExpired):
            decode_session_jwt(token)

    def test_서명_오류_JWTDecodeError(self):
        payload = {
            "sub": "3",
            "role": "user",
            "sub_status": "free",
            "exp": int(time.time()) + 3600,
        }
        # wrong_secret은 32자 이상이어야 InsecureKeyLengthWarning 없음
        token = _make_token(payload, secret="wrong_secret_long_enough_32chars_abc")
        with pytest.raises(JWTDecodeError):
            decode_session_jwt(token)

    def test_필수_필드_누락_JWTDecodeError(self):
        """sub, role, sub_status, exp 중 하나 누락 시 JWTDecodeError."""
        payload = {
            "sub": "4",
            "role": "user",
            # sub_status 누락
            "exp": int(time.time()) + 3600,
        }
        token = _make_token(payload)
        with pytest.raises(JWTDecodeError):
            decode_session_jwt(token)
