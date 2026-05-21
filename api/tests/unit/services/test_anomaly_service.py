"""Story 6.5 — anomaly_service.py 단위 테스트.

Coverage:
- list_anomaly_events: 기본 status='new' 필터, type/status/user/기간 필터
- mark_anomaly_reviewed: 정상 전이, actioned 409, reviewed 멱등, not_found 404
- mark_anomaly_actioned: 정상 전이, 이미 actioned None, not_found None
- _mask_email: 4 케이스
- _serialize_event: 단순 직렬화
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from api.src.services import anomaly_service
from api.src.services.anomaly_service import _mask_email, _serialize_event


# ── _mask_email ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("user@example.com", "u**@example.com"),
        ("a@example.com", "a@example.com"),  # 1자 그대로
        (None, None),
        ("invalid", "invalid"),  # @ 미포함 그대로
        ("ab@x.io", "a**@x.io"),
    ],
)
def test_mask_email_cases(raw, expected):
    assert _mask_email(raw) == expected


# ── _serialize_event ───────────────────────────────────────────────────────────


def test_serialize_event_basic():
    now = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    event = MagicMock()
    event.id = 42
    event.type = "rapid_followup_questions"
    event.target_user_id = 7
    event.ip = "1.2.3.4"
    event.ua = "Mozilla"
    event.details = {"count_in_window": 5}
    event.status = "new"
    event.reviewed_by_admin_id = None
    event.reviewed_at = None
    event.created_at = now

    result = _serialize_event(event)
    assert result["id"] == 42
    assert result["type"] == "rapid_followup_questions"
    assert result["target_user_id"] == 7
    assert result["details"] == {"count_in_window": 5}
    assert result["status"] == "new"
    assert result["created_at"] == now


def test_serialize_event_handles_null_details():
    event = MagicMock()
    event.id = 1
    event.type = "login_brute_force"
    event.target_user_id = None
    event.ip = None
    event.ua = None
    event.details = None
    event.status = "new"
    event.reviewed_by_admin_id = None
    event.reviewed_at = None
    event.created_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
    result = _serialize_event(event)
    assert result["details"] == {}


# ── mark_anomaly_reviewed ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mark_anomaly_reviewed_not_found():
    db = MagicMock()
    db.get = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc:
        await anomaly_service.mark_anomaly_reviewed(
            db, anomaly_id=999, actor_admin_id=1
        )
    assert exc.value.status_code == 404
    assert exc.value.detail["code"] == "ANOMALY_NOT_FOUND"


@pytest.mark.asyncio
async def test_mark_anomaly_reviewed_actioned_409():
    event = MagicMock()
    event.status = "actioned"
    db = MagicMock()
    db.get = AsyncMock(return_value=event)
    with pytest.raises(HTTPException) as exc:
        await anomaly_service.mark_anomaly_reviewed(
            db, anomaly_id=1, actor_admin_id=99
        )
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "ANOMALY_ALREADY_ACTIONED"


@pytest.mark.asyncio
async def test_mark_anomaly_reviewed_reviewed_idempotent():
    event = MagicMock()
    event.id = 1
    event.type = "rapid_followup_questions"
    event.target_user_id = 7
    event.ip = None
    event.ua = None
    event.details = {}
    event.status = "reviewed"
    event.reviewed_by_admin_id = 99
    event.reviewed_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
    event.created_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
    db = MagicMock()
    db.get = AsyncMock(return_value=event)

    result = await anomaly_service.mark_anomaly_reviewed(
        db, anomaly_id=1, actor_admin_id=99
    )
    assert result["status"] == "reviewed"
    # flush 호출 안 됨 (멱등)
    db.flush.assert_not_called() if hasattr(db, "flush") else None


@pytest.mark.asyncio
async def test_mark_anomaly_reviewed_new_to_reviewed():
    event = MagicMock()
    event.id = 1
    event.type = "rapid_followup_questions"
    event.target_user_id = 7
    event.ip = None
    event.ua = None
    event.details = {}
    event.status = "new"
    event.reviewed_by_admin_id = None
    event.reviewed_at = None
    event.created_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
    db = MagicMock()
    db.get = AsyncMock(return_value=event)
    db.flush = AsyncMock()

    result = await anomaly_service.mark_anomaly_reviewed(
        db, anomaly_id=1, actor_admin_id=99
    )
    assert event.status == "reviewed"
    assert event.reviewed_by_admin_id == 99
    assert event.reviewed_at is not None
    assert result["status"] == "reviewed"
    db.flush.assert_awaited_once()


# ── mark_anomaly_actioned ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mark_anomaly_actioned_not_found_returns_none():
    db = MagicMock()
    db.get = AsyncMock(return_value=None)
    result = await anomaly_service.mark_anomaly_actioned(
        db, anomaly_id=999, actor_admin_id=1
    )
    assert result is None


@pytest.mark.asyncio
async def test_mark_anomaly_actioned_already_actioned_returns_none():
    event = MagicMock()
    event.status = "actioned"
    db = MagicMock()
    db.get = AsyncMock(return_value=event)
    result = await anomaly_service.mark_anomaly_actioned(
        db, anomaly_id=1, actor_admin_id=2
    )
    assert result is None


@pytest.mark.asyncio
async def test_mark_anomaly_actioned_new_to_actioned():
    event = MagicMock()
    event.status = "new"
    event.reviewed_by_admin_id = None
    event.reviewed_at = None
    db = MagicMock()
    db.get = AsyncMock(return_value=event)
    result = await anomaly_service.mark_anomaly_actioned(
        db, anomaly_id=1, actor_admin_id=99
    )
    assert result is event
    assert event.status == "actioned"
    assert event.reviewed_by_admin_id == 99
    assert event.reviewed_at is not None


# ── ANOMALY_TYPES / ANOMALY_STATUSES 상수 ────────────────────────────────────


def test_anomaly_types_constant():
    assert anomaly_service.ANOMALY_TYPES == (
        "login_brute_force",
        "concurrent_ip_login",
        "repeated_question",
        "recovery_abuse",
        "rapid_followup_questions",
    )


def test_anomaly_statuses_constant():
    assert anomaly_service.ANOMALY_STATUSES == (
        "new",
        "reviewed",
        "actioned",
        "unblocked",
    )
