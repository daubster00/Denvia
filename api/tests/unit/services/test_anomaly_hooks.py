"""Story 6.5 — anomaly_service 자동 탐지 hook 단위 테스트.

Coverage:
- check_concurrent_ip_login: 1~2 user_id skip / 3 user_id INSERT / 멱등 flag / IP None skip
- check_rapid_questions: <3건 skip / 3건 INSERT / 5분 멱등 flag / admin skip
"""

from __future__ import annotations

from unittest.mock import MagicMock

import fakeredis.aioredis as fakeredis
import pytest

from api.src.services import anomaly_service


@pytest.fixture
def fake_rl():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def fake_quota():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def db():
    """flush() 호출 추적용 mock — 실제 INSERT는 검증하지 않고 db.add 호출만 검증."""
    s = MagicMock()
    s.added = []
    s.add = lambda obj: s.added.append(obj)

    async def _flush():
        return None

    async def _rollback():
        return None

    s.flush = _flush
    s.rollback = _rollback
    return s


# ── check_concurrent_ip_login ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_concurrent_ip_login_ip_none_skip(fake_rl, db):
    await anomaly_service.check_concurrent_ip_login(
        ip=None, user_id=1, ua="ua", redis_rl=fake_rl, db=db,
    )
    assert db.added == []


@pytest.mark.asyncio
async def test_concurrent_ip_login_below_threshold_skip(fake_rl, db):
    # 2개 user_id만 — 임계 미달
    await anomaly_service.check_concurrent_ip_login(
        ip="1.2.3.4", user_id=1, ua="ua", redis_rl=fake_rl, db=db,
    )
    await anomaly_service.check_concurrent_ip_login(
        ip="1.2.3.4", user_id=2, ua="ua", redis_rl=fake_rl, db=db,
    )
    assert db.added == []


@pytest.mark.asyncio
async def test_concurrent_ip_login_threshold_inserts_event(fake_rl, db):
    # 3개 distinct user_id → INSERT
    await anomaly_service.check_concurrent_ip_login(
        ip="1.2.3.4", user_id=1, ua="ua", redis_rl=fake_rl, db=db,
    )
    await anomaly_service.check_concurrent_ip_login(
        ip="1.2.3.4", user_id=2, ua="ua", redis_rl=fake_rl, db=db,
    )
    await anomaly_service.check_concurrent_ip_login(
        ip="1.2.3.4", user_id=3, ua="ua", redis_rl=fake_rl, db=db,
    )
    assert len(db.added) == 1
    event = db.added[0]
    assert event.type == "concurrent_ip_login"
    assert event.target_user_id is None
    assert event.ip == "1.2.3.4"
    assert event.details["distinct_user_count"] == 3
    assert sorted(event.details["user_ids"]) == [1, 2, 3]


@pytest.mark.asyncio
async def test_concurrent_ip_login_idempotent_within_window(fake_rl, db):
    # 3 user → INSERT, 4번째 user → flag 막아 INSERT 0
    for uid in [1, 2, 3]:
        await anomaly_service.check_concurrent_ip_login(
            ip="1.2.3.4", user_id=uid, ua="ua", redis_rl=fake_rl, db=db,
        )
    assert len(db.added) == 1

    await anomaly_service.check_concurrent_ip_login(
        ip="1.2.3.4", user_id=4, ua="ua", redis_rl=fake_rl, db=db,
    )
    assert len(db.added) == 1  # 멱등 flag로 1회만


@pytest.mark.asyncio
async def test_concurrent_ip_login_different_ips_independent(fake_rl, db):
    # IP A 3건 + IP B 3건 → 각각 INSERT
    for uid in [1, 2, 3]:
        await anomaly_service.check_concurrent_ip_login(
            ip="1.2.3.4", user_id=uid, ua="ua", redis_rl=fake_rl, db=db,
        )
    for uid in [10, 11, 12]:
        await anomaly_service.check_concurrent_ip_login(
            ip="5.6.7.8", user_id=uid, ua="ua", redis_rl=fake_rl, db=db,
        )
    assert len(db.added) == 2
    assert {e.ip for e in db.added} == {"1.2.3.4", "5.6.7.8"}


# ── check_rapid_questions ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rapid_questions_admin_skip(fake_quota, db):
    await anomaly_service.check_rapid_questions(
        user_id=1,
        subscription_status="admin",
        redis_quota=fake_quota,
        db=db,
    )
    assert db.added == []


@pytest.mark.asyncio
async def test_rapid_questions_below_threshold_skip(fake_quota, db):
    # 2건만 — 임계 미달
    for _ in range(2):
        await anomaly_service.check_rapid_questions(
            user_id=7,
            subscription_status="free",
            redis_quota=fake_quota,
            db=db,
        )
    assert db.added == []


@pytest.mark.asyncio
async def test_rapid_questions_threshold_inserts_event(fake_quota, db):
    # 3건 — 임계 도달 후 INSERT
    for _ in range(3):
        await anomaly_service.check_rapid_questions(
            user_id=7,
            subscription_status="free",
            redis_quota=fake_quota,
            db=db,
        )
    assert len(db.added) == 1
    event = db.added[0]
    assert event.type == "rapid_questions"
    assert event.target_user_id == 7
    assert event.details["count_in_window"] == 3


@pytest.mark.asyncio
async def test_rapid_questions_idempotent_5min_flag(fake_quota, db):
    # 3건 → INSERT, 4·5번째 → flag로 INSERT 막힘
    for _ in range(5):
        await anomaly_service.check_rapid_questions(
            user_id=7,
            subscription_status="free",
            redis_quota=fake_quota,
            db=db,
        )
    assert len(db.added) == 1


@pytest.mark.asyncio
async def test_rapid_questions_pro_user_also_applies(fake_quota, db):
    # Pro도 어뷰징 대상 — admin만 skip
    for _ in range(3):
        await anomaly_service.check_rapid_questions(
            user_id=42,
            subscription_status="pro",
            redis_quota=fake_quota,
            db=db,
        )
    assert len(db.added) == 1
    assert db.added[0].target_user_id == 42
