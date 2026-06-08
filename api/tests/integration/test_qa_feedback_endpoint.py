"""POST /api/v1/qa/feedback 통합 테스트 — Story 2.4 (AC-1~AC-4, AC-7~AC-8)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError

from api.src.deps.auth import get_current_user
from api.src.main import app
from api.src.models.base import get_session
from api.src.models.qa_feedback import QAFeedback
from api.src.models.qa_log import QALog
from api.src.models.user import User


# ──────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────

def _make_user(user_id: int = 1) -> MagicMock:
    u = MagicMock(spec=User)
    u.id = user_id
    u.subscription_status = "pro"
    u.current_session_id = None
    u.admin_grade = "master"
    return u


def _make_qa_log(log_id: int = 10, user_id: int = 1) -> MagicMock:
    log = MagicMock(spec=QALog)
    log.id = log_id
    log.user_id = user_id
    log.current_session_id = None
    log.admin_grade = "master"
    return log


def _make_existing_feedback(rating: str, change_count: int = 0) -> MagicMock:
    fb = MagicMock(spec=QAFeedback)
    fb.qa_log_id = 10
    fb.rating = rating
    fb.change_count = change_count
    return fb


def _db_session_dep(results: list):
    """순서대로 scalar_one_or_none()을 반환하는 DB 세션 의존성.
    매 request마다 독립된 call_count를 가진 세션을 생성한다.
    """
    async def _gen():
        cnt = [0]

        async def _execute(*args, **kwargs):
            result = MagicMock()
            result.scalar_one_or_none.return_value = results[min(cnt[0], len(results) - 1)]
            cnt[0] += 1
            return result

        db = AsyncMock()
        db.execute = _execute
        yield db

    return _gen


def _db_session_with_integrity_error():
    """첫 번째 commit 시 IntegrityError 발생 → 재시도 시 기존 피드백 반환."""
    qa_log = _make_qa_log(log_id=10, user_id=1)
    existing_fb = _make_existing_feedback(rating="good", change_count=0)

    call_count = 0

    async def _execute(*args, **kwargs):
        nonlocal call_count
        result = MagicMock()
        # call 0: qa_log 소유권 확인
        # call 1: 피드백 SELECT (None — 첫 시도)
        # call 2: 피드백 SELECT with_for_update (재귀 후 — existing_fb 반환)
        mapping = {0: qa_log, 1: None, 2: existing_fb}
        result.scalar_one_or_none.return_value = mapping.get(call_count, existing_fb)
        call_count += 1
        return result

    commit_count = 0

    async def _commit():
        nonlocal commit_count
        if commit_count == 0:
            commit_count += 1
            raise IntegrityError("UNIQUE violation", {}, Exception())
        commit_count += 1

    db = AsyncMock()
    db.execute = _execute
    db.commit = _commit

    async def _gen():
        yield db

    return _gen


# ──────────────────────────────────────────────
# 픽스처
# ──────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


# ──────────────────────────────────────────────
# 라우트 등록 확인 (Task 1.3)
# ──────────────────────────────────────────────

def test_route_registered():
    """POST /api/v1/qa/feedback 라우트가 앱에 등록되어 있는지 확인."""
    routes = {r.path for r in app.routes if hasattr(r, "path")}
    assert "/api/v1/qa/feedback" in routes


# ──────────────────────────────────────────────
# AC-3: upsert 분기 HTTP 응답 검증
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_post_new_feedback_returns_created():
    """POST 신규 → 200 + action=created + change_count=0."""
    user = _make_user(user_id=1)
    qa_log = _make_qa_log(log_id=10, user_id=1)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = _db_session_dep([qa_log, None])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/v1/qa/feedback", json={"qa_log_id": 10, "rating": "good"})

    assert res.status_code == 200
    body = res.json()
    assert body["action"] == "created"
    assert body["rating"] == "good"
    assert body["change_count"] == 0
    assert body["qa_log_id"] == 10


@pytest.mark.asyncio
async def test_post_same_rating_returns_unchanged():
    """같은 rating 재전송 → 200 + action=unchanged + change_count 불변."""
    user = _make_user(user_id=1)
    qa_log = _make_qa_log(log_id=10, user_id=1)
    existing_fb = _make_existing_feedback(rating="good", change_count=3)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = _db_session_dep([qa_log, existing_fb])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/v1/qa/feedback", json={"qa_log_id": 10, "rating": "good"})

    assert res.status_code == 200
    body = res.json()
    assert body["action"] == "unchanged"
    assert body["change_count"] == 3


@pytest.mark.asyncio
async def test_post_different_rating_returns_updated():
    """다른 rating 전송 → 200 + action=updated + change_count=1."""
    user = _make_user(user_id=1)
    qa_log = _make_qa_log(log_id=10, user_id=1)
    existing_fb = _make_existing_feedback(rating="good", change_count=0)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = _db_session_dep([qa_log, existing_fb])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/v1/qa/feedback", json={"qa_log_id": 10, "rating": "bad"})

    assert res.status_code == 200
    body = res.json()
    assert body["action"] == "updated"
    assert body["rating"] == "bad"
    assert body["change_count"] == 1


@pytest.mark.asyncio
async def test_post_multiple_changes_no_limit():
    """2회 변경 → change_count=2 (변경 횟수 한도 없음 검증)."""
    user = _make_user(user_id=1)
    qa_log = _make_qa_log(log_id=10, user_id=1)
    existing_fb = _make_existing_feedback(rating="good", change_count=1)  # 이미 1번 변경됨
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = _db_session_dep([qa_log, existing_fb])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/v1/qa/feedback", json={"qa_log_id": 10, "rating": "bad"})

    assert res.status_code == 200
    assert res.json()["change_count"] == 2


# ──────────────────────────────────────────────
# AC-2: 권한/소유권 검증
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_other_user_qa_log_returns_404():
    """타사용자 qa_log_id → 404 + code=QA_LOG_NOT_FOUND."""
    user = _make_user(user_id=1)
    qa_log = _make_qa_log(log_id=10, user_id=999)  # 다른 사용자
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = _db_session_dep([qa_log])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/v1/qa/feedback", json={"qa_log_id": 10, "rating": "good"})

    assert res.status_code == 404
    body = res.json()
    assert body["code"] == "QA_LOG_NOT_FOUND"


@pytest.mark.asyncio
async def test_nonexistent_qa_log_returns_404():
    """부재 qa_log_id → 404 + code=QA_LOG_NOT_FOUND."""
    user = _make_user(user_id=1)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = _db_session_dep([None])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/v1/qa/feedback", json={"qa_log_id": 99999, "rating": "good"})

    assert res.status_code == 404
    body = res.json()
    assert body["code"] == "QA_LOG_NOT_FOUND"


# ──────────────────────────────────────────────
# 입력 검증 (AC-1 + AC-7)
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_invalid_rating_returns_422():
    """`rating="invalid"` → 422 (Pydantic Literal 자동 검증)."""
    user = _make_user(user_id=1)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = _db_session_dep([None])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/v1/qa/feedback", json={"qa_log_id": 10, "rating": "invalid"})

    assert res.status_code == 422


@pytest.mark.asyncio
async def test_qa_log_id_zero_returns_422():
    """`qa_log_id=0` → 422 (Field ge=1 검증)."""
    user = _make_user(user_id=1)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = _db_session_dep([None])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/v1/qa/feedback", json={"qa_log_id": 0, "rating": "good"})

    assert res.status_code == 422


# ──────────────────────────────────────────────
# AC-4: 동시성 race 방어 (IntegrityError → 재시도)
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_concurrent_insert_integrity_error_handled():
    """동시 INSERT 시뮬레이션 — IntegrityError 발생 시 재시도 후 정상 응답."""
    user = _make_user(user_id=1)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = _db_session_with_integrity_error()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/v1/qa/feedback", json={"qa_log_id": 10, "rating": "good"})

    # IntegrityError 발생 시 재귀 호출 후 unchanged/updated/created 중 하나로 정상 응답
    assert res.status_code == 200
    body = res.json()
    assert body["action"] in ("created", "updated", "unchanged")


@pytest.mark.asyncio
async def test_concurrent_requests_both_succeed():
    """독립된 두 요청 모두 정상 응답 반환 — per-request 세션 격리 검증."""
    user = _make_user(user_id=1)
    qa_log = _make_qa_log(log_id=10, user_id=1)

    # 매 request마다 독립된 call_count를 가진 세션 의존성 설정
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = _db_session_dep([qa_log, None])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res1 = await client.post("/api/v1/qa/feedback", json={"qa_log_id": 10, "rating": "good"})
        res2 = await client.post("/api/v1/qa/feedback", json={"qa_log_id": 10, "rating": "good"})

    assert res1.status_code == 200
    assert res2.status_code == 200
