"""재사용 가능한 slowapi 레이트 리밋 Depends 데코레이터.

Story 1.3/1.4에서 각 라우터에 부착 예정. 여기서는 정의만.
"""

from fastapi import Request

from api.src.middleware.rate_limit import limiter


def _phone_key(request: Request) -> str:
    """휴대폰 번호 기반 키 생성 — SMS 발송 레이트 리밋용."""
    body = getattr(request.state, "parsed_body", {}) or {}
    return f"sms:{body.get('phone', 'unknown')}"


# Story 1.4 로그인에서 @limit_login Depends 사용
limit_login = limiter.limit("5/minute")

# Story 1.3 SMS 발송에서 phone 기반 key
limit_sms_send_per_minute = limiter.limit("1/minute", key_func=_phone_key)
limit_sms_send_per_hour = limiter.limit("5/hour", key_func=_phone_key)

# Story 1.3 회원가입
limit_signup = limiter.limit("3/minute")
