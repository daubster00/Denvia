"""Story 6.5 — anomaly_service 자동 탐지 hook 단위 테스트.

Coverage:
- check_concurrent_ip_login: 1~2 user_id skip / 3 user_id INSERT / 멱등 flag / IP None skip
- check_rapid_followup_questions: streak 임계 도달 시 status='actioned' + auto 검토 마킹
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

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


# ── check_rapid_followup_questions ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_rapid_followup_threshold_inserts_actioned_event(fake_quota, db):
    """답변 직후 3초 윈도우에서 streak 임계(3) 도달 시 actioned + 자동검토."""
    user_id = 7
    # streak=2 까지 사전 누적 → 본 호출에서 3 도달.
    await fake_quota.set(
        f"qa:last_done:user:{user_id}", str(time.time() - 1.0)
    )
    await fake_quota.set(f"qa:rapid_followup_streak:user:{user_id}", "2")

    # User row 모킹 — anomaly_throttled_at = None (신규 throttle 적용).
    user_row = MagicMock()
    user_row.anomaly_throttled_at = None
    select_result = MagicMock()
    select_result.scalar_one_or_none = MagicMock(return_value=user_row)
    db.execute = AsyncMock(return_value=select_result)

    result = await anomaly_service.check_rapid_followup_questions(
        user_id=user_id,
        subscription_status="free",
        redis_quota=fake_quota,
        db=db,
    )

    assert result is True
    assert len(db.added) == 1
    event = db.added[0]
    assert event.type == "rapid_followup_questions"
    assert event.target_user_id == user_id
    # 핵심 — 시스템 자동조치이므로 등록 시점부터 actioned + 자동검토.
    assert event.status == "actioned"
    assert event.reviewed_by_admin_id is None
    assert event.reviewed_at is not None
    assert event.details.get("auto_actioned") is True


@pytest.mark.asyncio
async def test_rapid_followup_below_threshold_no_event(fake_quota, db):
    """streak 임계 미달 — INSERT 없음."""
    user_id = 7
    await fake_quota.set(
        f"qa:last_done:user:{user_id}", str(time.time() - 1.0)
    )
    # streak=0 (없는 키 INCR → 1) → 임계 3 미달.

    result = await anomaly_service.check_rapid_followup_questions(
        user_id=user_id,
        subscription_status="free",
        redis_quota=fake_quota,
        db=db,
    )

    assert result is False
    assert db.added == []


@pytest.mark.asyncio
async def test_rapid_followup_admin_skipped(fake_quota, db):
    """admin 은 throttle 대상이 아님 — Redis 조회 자체 skip."""
    result = await anomaly_service.check_rapid_followup_questions(
        user_id=1,
        subscription_status="admin",
        redis_quota=fake_quota,
        db=db,
    )
    assert result is False
    assert db.added == []


@pytest.mark.asyncio
async def test_rapid_followup_outside_window_resets_streak(fake_quota, db):
    """답변 완료 후 3초 초과 — streak 리셋, INSERT 없음."""
    user_id = 7
    await fake_quota.set(
        f"qa:last_done:user:{user_id}", str(time.time() - 10.0)
    )
    await fake_quota.set(f"qa:rapid_followup_streak:user:{user_id}", "2")

    result = await anomaly_service.check_rapid_followup_questions(
        user_id=user_id,
        subscription_status="free",
        redis_quota=fake_quota,
        db=db,
    )

    assert result is False
    assert db.added == []
    # streak 키 삭제 확인.
    assert await fake_quota.get(f"qa:rapid_followup_streak:user:{user_id}") is None
