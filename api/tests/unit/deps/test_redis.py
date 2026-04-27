"""Redis 의존성 단위 테스트 — Story 2.3 (DB 3/4 별도 풀 분리 검증)."""

import pytest

from api.src.deps.redis import (
    get_redis_client,
    get_redis_quota_client,
    get_redis_runtime_client,
)
from api.src.settings import REDIS_DB_QUOTA, REDIS_DB_RUNTIME_CONFIG


class TestRedisPools:
    def test_quota_and_runtime_clients_are_different_objects(self):
        """DB 3과 DB 4는 서로 다른 클라이언트 풀 인스턴스를 사용한다 (race-condition 방지)."""
        quota = get_redis_quota_client()
        runtime = get_redis_runtime_client()
        assert quota is not runtime

    def test_default_client_is_different_from_quota(self):
        """기본 클라이언트(DB 0)와 quota(DB 4)는 별개 풀이다."""
        default = get_redis_client()
        quota = get_redis_quota_client()
        assert default is not quota

    def test_quota_client_is_singleton(self):
        """quota 클라이언트는 lazy-init 싱글턴 — 같은 객체를 반환한다."""
        a = get_redis_quota_client()
        b = get_redis_quota_client()
        assert a is b

    def test_runtime_client_is_singleton(self):
        """runtime 클라이언트는 lazy-init 싱글턴 — 같은 객체를 반환한다."""
        a = get_redis_runtime_client()
        b = get_redis_runtime_client()
        assert a is b

    def test_quota_db_constant(self):
        assert REDIS_DB_QUOTA == 4

    def test_runtime_db_constant(self):
        assert REDIS_DB_RUNTIME_CONFIG == 3
