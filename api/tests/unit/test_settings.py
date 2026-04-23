"""Redis DB 번호 상수 검증 — 용도별 DB 번호가 0~4에 정확히 매핑되는지 확인."""


from api.src.settings import (
    REDIS_DB_CELERY,
    REDIS_DB_OTP,
    REDIS_DB_QUOTA,
    REDIS_DB_RATE_LIMIT,
    REDIS_DB_RUNTIME_CONFIG,
)


def test_redis_db_numbers_are_correct():
    """Redis DB 번호 상수가 아키텍처 문서와 일치하는지 검증한다."""
    assert REDIS_DB_CELERY == 0, "DB 0: Celery broker/result"
    assert REDIS_DB_OTP == 1, "DB 1: OTP (5분 TTL)"
    assert REDIS_DB_RATE_LIMIT == 2, "DB 2: Rate Limit"
    assert REDIS_DB_RUNTIME_CONFIG == 3, "DB 3: RuntimeConfig"
    assert REDIS_DB_QUOTA == 4, "DB 4: Quota"


def test_redis_db_numbers_are_unique():
    """모든 Redis DB 번호가 서로 다른지 검증한다."""
    all_dbs = [
        REDIS_DB_CELERY,
        REDIS_DB_OTP,
        REDIS_DB_RATE_LIMIT,
        REDIS_DB_RUNTIME_CONFIG,
        REDIS_DB_QUOTA,
    ]
    assert len(set(all_dbs)) == len(all_dbs), "Redis DB 번호 중복 없어야 함"
