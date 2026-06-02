"""Story 6.5 — anomaly_service 자동 탐지 hook 단위 테스트.

Coverage:
- check_concurrent_ip_login: 1~2 user_id skip / 3 user_id 사용자별 INSERT / 사용자별 멱등
  flag / 추가 합류 사용자 INSERT / IP None skip
- check_rapid_followup_questions: streak 임계 도달 시 status='new' (관리자 미검토 표식)
  + auto_actioned details 표식 + 신규 throttle 적용 시 사용자 쪽지함 안내(InboxMessage)
  동반 INSERT
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import fakeredis.aioredis as fakeredis
import pytest

from api.src.models.anomaly_event import AnomalyEvent
from api.src.models.inbox_message import InboxMessage
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
    # 3개 distinct user_id → 사용자별로 1건씩 총 3건 INSERT
    await anomaly_service.check_concurrent_ip_login(
        ip="1.2.3.4", user_id=1, ua="ua1", redis_rl=fake_rl, db=db,
    )
    await anomaly_service.check_concurrent_ip_login(
        ip="1.2.3.4", user_id=2, ua="ua2", redis_rl=fake_rl, db=db,
    )
    await anomaly_service.check_concurrent_ip_login(
        ip="1.2.3.4", user_id=3, ua="ua3", redis_rl=fake_rl, db=db,
    )
    events = [o for o in db.added if isinstance(o, AnomalyEvent)]
    assert len(events) == 3
    for event in events:
        assert event.type == "concurrent_ip_login"
        assert event.ip == "1.2.3.4"
        assert event.details["distinct_user_count"] == 3
    target_ids = sorted(e.target_user_id for e in events)
    assert target_ids == [1, 2, 3]
    # 임계 도달을 일으킨 호출의 user_id(=3)의 row 에만 그 호출의 UA 가 기록되고,
    # 이전 두 호출의 UA 는 이번 호출 컨텍스트에 없으므로 None.
    by_uid = {e.target_user_id: e for e in events}
    assert by_uid[3].ua == "ua3"
    assert by_uid[1].ua is None
    assert by_uid[2].ua is None
    # co_user_ids 는 자기 자신 제외.
    assert sorted(by_uid[1].details["co_user_ids"]) == [2, 3]
    assert sorted(by_uid[2].details["co_user_ids"]) == [1, 3]
    assert sorted(by_uid[3].details["co_user_ids"]) == [1, 2]


@pytest.mark.asyncio
async def test_concurrent_ip_login_idempotent_within_window(fake_rl, db):
    # 3 user → 3건 INSERT, 같은 user 가 다시 로그인해도 추가 INSERT 없음.
    for uid in [1, 2, 3]:
        await anomaly_service.check_concurrent_ip_login(
            ip="1.2.3.4", user_id=uid, ua="ua", redis_rl=fake_rl, db=db,
        )
    events = [o for o in db.added if isinstance(o, AnomalyEvent)]
    assert len(events) == 3

    # user_id=2 가 다시 로그인 — 사용자별 NX flag 가 막아 추가 INSERT 없음.
    await anomaly_service.check_concurrent_ip_login(
        ip="1.2.3.4", user_id=2, ua="ua", redis_rl=fake_rl, db=db,
    )
    events = [o for o in db.added if isinstance(o, AnomalyEvent)]
    assert len(events) == 3


@pytest.mark.asyncio
async def test_concurrent_ip_login_new_user_after_threshold_inserts(fake_rl, db):
    # 임계 도달 후 합류한 4번째 사용자도 자기 row 를 받아야 한다.
    for uid in [1, 2, 3]:
        await anomaly_service.check_concurrent_ip_login(
            ip="1.2.3.4", user_id=uid, ua="ua", redis_rl=fake_rl, db=db,
        )
    events = [o for o in db.added if isinstance(o, AnomalyEvent)]
    assert len(events) == 3

    await anomaly_service.check_concurrent_ip_login(
        ip="1.2.3.4", user_id=4, ua="ua4", redis_rl=fake_rl, db=db,
    )
    events = [o for o in db.added if isinstance(o, AnomalyEvent)]
    assert len(events) == 4
    new_event = events[-1]
    assert new_event.target_user_id == 4
    assert new_event.ua == "ua4"
    assert new_event.details["distinct_user_count"] == 4
    assert sorted(new_event.details["co_user_ids"]) == [1, 2, 3]


@pytest.mark.asyncio
async def test_concurrent_ip_login_different_ips_independent(fake_rl, db):
    # IP A 3건 + IP B 3건 → 각 IP 별로 사용자별 INSERT (각 3건씩 총 6건).
    for uid in [1, 2, 3]:
        await anomaly_service.check_concurrent_ip_login(
            ip="1.2.3.4", user_id=uid, ua="ua", redis_rl=fake_rl, db=db,
        )
    for uid in [10, 11, 12]:
        await anomaly_service.check_concurrent_ip_login(
            ip="5.6.7.8", user_id=uid, ua="ua", redis_rl=fake_rl, db=db,
        )
    events = [o for o in db.added if isinstance(o, AnomalyEvent)]
    assert len(events) == 6
    by_ip = {ip: [e for e in events if e.ip == ip] for ip in {"1.2.3.4", "5.6.7.8"}}
    assert len(by_ip["1.2.3.4"]) == 3
    assert len(by_ip["5.6.7.8"]) == 3
    assert sorted(e.target_user_id for e in by_ip["1.2.3.4"]) == [1, 2, 3]
    assert sorted(e.target_user_id for e in by_ip["5.6.7.8"]) == [10, 11, 12]


# ── check_rapid_followup_questions ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_rapid_followup_threshold_inserts_new_event(fake_quota, db):
    """답변 직후 3초 윈도우에서 streak 임계(3) 도달 시 status='new' (관리자 미검토)."""
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
    # 신규 throttle 적용 — InboxMessage(쪽지함 안내) + AnomalyEvent 2건 동시 등록.
    events = [o for o in db.added if isinstance(o, AnomalyEvent)]
    inboxes = [o for o in db.added if isinstance(o, InboxMessage)]
    assert len(events) == 1
    assert len(inboxes) == 1
    event = events[0]
    assert event.type == "rapid_followup_questions"
    assert event.target_user_id == user_id
    # 자동 throttle 이 걸려도 anomaly row 는 'new' 로 INSERT — 대시보드 "이상행동 미검토"
    # 카운트에 잡혀야 하기 때문. 자동조치 여부는 details.auto_actioned 표식으로 구분.
    assert event.status == "new"
    assert event.reviewed_by_admin_id is None
    assert event.reviewed_at is None
    assert event.details.get("auto_actioned") is True
    # 쪽지함 안내 — 사용자에게 자동 제한 적용 사실을 알린다.
    inbox = inboxes[0]
    assert inbox.user_id == user_id
    assert inbox.type == "system"
    assert "자동 제한" in inbox.title


@pytest.mark.asyncio
async def test_rapid_followup_already_throttled_skips_inbox(fake_quota, db):
    """이미 throttled 사용자의 재발 — anomaly 는 INSERT 하되 쪽지 중복 발송은 막는다."""
    user_id = 7
    await fake_quota.set(
        f"qa:last_done:user:{user_id}", str(time.time() - 1.0)
    )
    await fake_quota.set(f"qa:rapid_followup_streak:user:{user_id}", "2")

    from datetime import datetime, timezone

    user_row = MagicMock()
    user_row.anomaly_throttled_at = datetime.now(tz=timezone.utc)
    select_result = MagicMock()
    select_result.scalar_one_or_none = MagicMock(return_value=user_row)
    db.execute = AsyncMock(return_value=select_result)

    result = await anomaly_service.check_rapid_followup_questions(
        user_id=user_id,
        subscription_status="free",
        redis_quota=fake_quota,
        db=db,
    )

    # 이미 throttled — return False (popup 미트리거).
    assert result is False
    events = [o for o in db.added if isinstance(o, AnomalyEvent)]
    inboxes = [o for o in db.added if isinstance(o, InboxMessage)]
    # 재발 기록용 anomaly 는 그대로 INSERT, 쪽지 중복 발송은 막는다.
    assert len(events) == 1
    assert events[0].details.get("already_throttled") is True
    assert len(inboxes) == 0


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
    """답변 완료 후 윈도우 초과 — streak=1 로 초기화 (이 질문을 새 시작점으로 카운트), INSERT 없음."""
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
    # 직관적 N회 카운팅 — 윈도우 밖이라도 이 질문이 1번째로 다시 카운트되어 streak="1".
    assert await fake_quota.get(f"qa:rapid_followup_streak:user:{user_id}") == "1"


@pytest.mark.asyncio
async def test_rapid_followup_first_question_initializes_streak(fake_quota, db):
    """첫 질문(last_done 없음) — streak=1 로 초기화, INSERT 없음. 직관적 N회 카운팅."""
    user_id = 7

    result = await anomaly_service.check_rapid_followup_questions(
        user_id=user_id,
        subscription_status="free",
        redis_quota=fake_quota,
        db=db,
    )

    assert result is False
    assert db.added == []
    # 이 질문 자체를 1번째로 카운트.
    assert await fake_quota.get(f"qa:rapid_followup_streak:user:{user_id}") == "1"
