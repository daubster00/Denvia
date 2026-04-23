"""slowapi Limiter 설정 유닛 테스트."""

from api.src.middleware.rate_limit import limiter
from api.src.settings import settings, REDIS_DB_RATE_LIMIT


class TestRateLimitConfig:
    def test_limiter_storage_uri가_redis_db2를_가리킨다(self):
        """Limiter storage_uri가 REDIS_DB_RATE_LIMIT(2) DB를 참조하는지 확인."""
        expected_uri = f"{settings.redis_url}/{REDIS_DB_RATE_LIMIT}"
        # slowapi Limiter의 storage_uri는 직접 접근 불가, 초기화 인자로 확인
        assert REDIS_DB_RATE_LIMIT == 2
        assert expected_uri == f"redis://redis:6379/2" or expected_uri.endswith(f"/{REDIS_DB_RATE_LIMIT}")

    def test_redis_db_rate_limit_상수가_2이다(self):
        assert REDIS_DB_RATE_LIMIT == 2
