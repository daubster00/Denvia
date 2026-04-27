"""qa_feedback_service 단위 테스트 — Story 2.4."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
import structlog.testing
from fastapi import HTTPException

from api.src.models.qa_feedback import QAFeedback
from api.src.models.qa_log import QALog
from api.src.models.user import User
from api.src.services.qa_feedback_service import upsert_feedback


_SENTINEL_DT = datetime(2000, 1, 1, tzinfo=timezone.utc)


def _make_user(user_id: int = 1) -> MagicMock:
    u = MagicMock(spec=User)
    u.id = user_id
    return u


def _make_qa_log(log_id: int = 10, user_id: int = 1) -> MagicMock:
    log = MagicMock(spec=QALog)
    log.id = log_id
    log.user_id = user_id
    return log


def _make_existing_feedback(rating: str = "good", change_count: int = 0) -> MagicMock:
    fb = MagicMock(spec=QAFeedback)
    fb.qa_log_id = 10
    fb.rating = rating
    fb.change_count = change_count
    fb.updated_at = _SENTINEL_DT
    return fb


def _build_db(results: list) -> AsyncMock:
    """순서대로 scalar_one_or_none()을 반환하는 db mock."""
    call_count = 0

    async def _execute(*args, **kwargs):
        nonlocal call_count
        result = MagicMock()
        result.scalar_one_or_none.return_value = results[min(call_count, len(results) - 1)]
        call_count += 1
        return result

    db = AsyncMock()
    db.execute = _execute
    return db


# ──────────────────────────────────────────────
# AC-3: upsert 분기 테스트
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_created_path():
    """기존 레코드 없음 → INSERT → action=created, change_count=0."""
    user = _make_user(user_id=1)
    qa_log = _make_qa_log(log_id=10, user_id=1)
    db = _build_db([qa_log, None])  # 1st: qa_log 소유권 확인, 2nd: 기존 피드백 없음

    with structlog.testing.capture_logs() as logs:
        result = await upsert_feedback(db=db, user=user, qa_log_id=10, rating="good")

    assert result.action == "created"
    assert result.rating == "good"
    assert result.change_count == 0
    assert result.qa_log_id == 10
    db.commit.assert_called_once()
    assert any(l["event"] == "qa.feedback.created" for l in logs)


@pytest.mark.asyncio
async def test_updated_path():
    """기존 rating=good → bad 전송 → action=updated, change_count=1, updated_at 갱신."""
    user = _make_user(user_id=1)
    qa_log = _make_qa_log(log_id=10, user_id=1)
    existing_fb = _make_existing_feedback(rating="good", change_count=0)
    db = _build_db([qa_log, existing_fb])

    with structlog.testing.capture_logs() as logs:
        result = await upsert_feedback(db=db, user=user, qa_log_id=10, rating="bad")

    assert result.action == "updated"
    assert result.rating == "bad"
    assert result.change_count == 1
    # updated_at 명시 갱신 검증 (sentinel과 달라야 함)
    assert existing_fb.updated_at != _SENTINEL_DT
    assert isinstance(existing_fb.updated_at, datetime)

    update_log = next((l for l in logs if l["event"] == "qa.feedback.updated"), None)
    assert update_log is not None
    assert update_log["from_rating"] == "good"
    assert update_log["to_rating"] == "bad"
    assert update_log["change_count"] == 1


@pytest.mark.asyncio
async def test_unchanged_path():
    """기존 rating=good → good 재전송 → action=unchanged, change_count 불변."""
    user = _make_user(user_id=1)
    qa_log = _make_qa_log(log_id=10, user_id=1)
    existing_fb = _make_existing_feedback(rating="good", change_count=2)
    db = _build_db([qa_log, existing_fb])

    with structlog.testing.capture_logs() as logs:
        result = await upsert_feedback(db=db, user=user, qa_log_id=10, rating="good")

    assert result.action == "unchanged"
    assert result.change_count == 2  # 불변
    db.commit.assert_not_called()
    assert any(l["event"] == "qa.feedback.unchanged" for l in logs)


# ──────────────────────────────────────────────
# AC-2: 권한 검증 테스트
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_not_owner_returns_404():
    """타사용자 qa_log_id → 404 + structlog unauthorized reason=not_owner."""
    user = _make_user(user_id=1)
    qa_log = _make_qa_log(log_id=10, user_id=999)  # 다른 사용자
    db = _build_db([qa_log])

    with structlog.testing.capture_logs() as logs:
        with pytest.raises(HTTPException) as exc_info:
            await upsert_feedback(db=db, user=user, qa_log_id=10, rating="good")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["code"] == "QA_LOG_NOT_FOUND"

    unauth_log = next((l for l in logs if l["event"] == "qa.feedback.unauthorized"), None)
    assert unauth_log is not None
    assert unauth_log["reason"] == "not_owner"
    assert unauth_log["user_id"] == 1
    assert unauth_log["qa_log_id"] == 10


@pytest.mark.asyncio
async def test_not_found_returns_404():
    """부재 qa_log_id → 404 + structlog unauthorized reason=not_found."""
    user = _make_user(user_id=1)
    db = _build_db([None])  # qa_log 없음

    with structlog.testing.capture_logs() as logs:
        with pytest.raises(HTTPException) as exc_info:
            await upsert_feedback(db=db, user=user, qa_log_id=99999, rating="good")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["code"] == "QA_LOG_NOT_FOUND"

    unauth_log = next((l for l in logs if l["event"] == "qa.feedback.unauthorized"), None)
    assert unauth_log is not None
    assert unauth_log["reason"] == "not_found"
