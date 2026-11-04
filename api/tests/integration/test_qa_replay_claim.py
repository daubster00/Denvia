"""저장 답변 재생 선점의 **실제 원자성** — 재수정 P1-1. 실제 PostgreSQL 필요.

목(mock)으로는 "동시 요청 2개 중 하나만 선점한다" 를 증명할 수 없다. 원자성은 DB 가
제공하는 성질이므로, 이 파일만 실제 세션(``async_session_factory``)으로 돈다.

DB 가 없으면 전체를 skip 한다(단위 테스트 환경 호환).

**안전 규칙** — 이 테스트는 자기가 만든 ``qa_logs`` 행만 건드리고 끝나면 지운다.
사용자 행은 **만들지도 지우지도 않는다**(기존 사용자 id 를 읽기 전용으로 빌려 쓴다).
테이블 생성·삭제·마이그레이션은 하지 않는다.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy import delete, select, text

from api.src.models.base import async_session_factory
from api.src.models.qa_log import QALog
from api.src.models.user import User
from api.src.services.chat_history_service import HistoryState, history_context_key
from api.src.services.qa_service import REPLAY_CLAIM_LEASE_SECONDS, QAService

QUESTION = "재생 선점 동시성 테스트 질문"


def _fake_user(user_id: int) -> MagicMock:
    user = MagicMock(spec=User)
    user.id = user_id
    return user


async def _db_available() -> bool:
    try:
        async with async_session_factory() as s:
            await s.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def _borrow_user_id() -> int | None:
    """기존 사용자 id 하나를 읽기 전용으로 빌린다. 없으면 None (skip)."""
    async with async_session_factory() as s:
        row = (await s.execute(select(User.id).order_by(User.id.asc()).limit(1))).first()
    return int(row.id) if row else None


@pytest.fixture
async def real_db_user_id():
    if not await _db_available():
        pytest.skip("실제 PostgreSQL 이 없어 원자성 검증을 건너뛴다")
    user_id = await _borrow_user_id()
    if user_id is None:
        pytest.skip("dev DB 에 사용자 행이 없어 qa_logs FK 를 만들 수 없다")
    yield user_id
    # 이 테스트가 만든 행만 지운다.
    async with async_session_factory() as s:
        await s.execute(delete(QALog).where(QALog.question_text == QUESTION))
        await s.commit()


async def _insert_undelivered(
    user_id: int,
    *,
    answer: str = "저장된 답변 본문",
    context_key: str | None = None,
    claimed_at: datetime | None = None,
    claim_token: str | None = None,
) -> int:
    """'완성됐지만 전송 못 한' 답변 행 1개를 만든다."""
    async with async_session_factory() as s:
        log = QALog(
            user_id=user_id,
            question_text=QUESTION,
            answer_text=answer,
            rule_matched=False,
            status="completed",
            delivered=False,
            input_tokens=11,
            output_tokens=22,
            history_context_key=context_key,
            replay_claimed_at=claimed_at,
            replay_claim_token=claim_token,
            created_at=datetime.now(timezone.utc),
        )
        s.add(log)
        await s.flush()
        await s.refresh(log)
        log_id = int(log.id)
        await s.commit()
    return log_id


async def _read(log_id: int) -> QALog:
    async with async_session_factory() as s:
        return (
            await s.execute(select(QALog).where(QALog.id == log_id))
        ).scalar_one()


async def _claim_once(user_id: int, barrier: asyncio.Barrier | None = None):
    """독립 세션에서 선점을 1회 시도한다 — 동시 요청을 흉내낸다.

    ``barrier`` 를 주면 세션을 **모두 열어 둔 뒤** 선점 UPDATE 만 동시에 때린다.
    이렇게 하지 않으면 한쪽이 커넥션을 맺는 동안 다른 쪽이 먼저 커밋해 버려,
    경쟁이 실제로 일어나지 않고도 테스트가 통과할 수 있다.
    """
    svc = QAService()
    async with async_session_factory() as s:
        # 커넥션을 미리 확보해 둔다(첫 쿼리에서 커넥션을 맺느라 생기는 시차 제거).
        await s.execute(text("SELECT 1"))
        if barrier is not None:
            await barrier.wait()
        return await svc.claim_replayable(
            s,
            user=_fake_user(user_id),
            question_text=QUESTION,
            history_context_key=None,
            explicit_retry=False,
            history_state=HistoryState.NONE,
        )


@pytest.mark.asyncio
async def test_two_concurrent_requests_only_one_claims(real_db_user_id):
    """**핵심.** 같은 답변에 동시 요청 2개 → 정확히 1개만 재생 권한을 얻는다."""
    log_id = await _insert_undelivered(real_db_user_id)

    barrier = asyncio.Barrier(2)
    first, second = await asyncio.gather(
        _claim_once(real_db_user_id, barrier), _claim_once(real_db_user_id, barrier)
    )

    winners = [c for c in (first, second) if c is not None]
    assert len(winners) == 1, "동시 요청 2개가 같은 답변을 함께 재생했다"
    assert winners[0].qa_log_id == log_id
    assert winners[0].answer_text == "저장된 답변 본문"

    row = await _read(log_id)
    assert row.replay_claimed_at is not None
    assert row.replay_claim_token == winners[0].claim_token
    # 선점만으로는 전달 완료가 아니다.
    assert row.delivered is False


@pytest.mark.asyncio
async def test_five_concurrent_requests_only_one_claims(real_db_user_id):
    """요청이 더 많아도 승자는 하나다."""
    await _insert_undelivered(real_db_user_id)

    barrier = asyncio.Barrier(5)
    results = await asyncio.gather(
        *[_claim_once(real_db_user_id, barrier) for _ in range(5)]
    )
    assert sum(1 for r in results if r is not None) == 1


@pytest.mark.asyncio
async def test_finished_replay_marks_delivered(real_db_user_id):
    """재생을 끝까지 마치면 delivered=true 로 확정된다."""
    log_id = await _insert_undelivered(real_db_user_id)
    svc = QAService()

    async with async_session_factory() as s:
        claim = await svc.claim_replayable(
            s,
            user=_fake_user(real_db_user_id),
            question_text=QUESTION,
            history_state=HistoryState.NONE,
        )
        assert claim is not None
        events = [ev async for ev in svc.stream_saved(db=s, claim=claim)]

    assert [ev["event"] for ev in events] == ["token", "done"]
    row = await _read(log_id)
    assert row.delivered is True


@pytest.mark.asyncio
async def test_delivered_row_is_never_claimed_again(real_db_user_id):
    """전달 완료된 답변은 다시 선점되지 않는다 (중복 재생 차단)."""
    log_id = await _insert_undelivered(real_db_user_id)
    svc = QAService()

    async with async_session_factory() as s:
        claim = await svc.claim_replayable(
            s,
            user=_fake_user(real_db_user_id),
            question_text=QUESTION,
            history_state=HistoryState.NONE,
        )
        assert claim is not None
        async for _ in svc.stream_saved(db=s, claim=claim):
            pass

    assert (await _read(log_id)).delivered is True
    # 두 번째 시도는 후보가 없다.
    assert await _claim_once(real_db_user_id) is None


@pytest.mark.asyncio
async def test_disconnect_releases_claim_for_immediate_retry(real_db_user_id):
    """재생 중 연결이 끊기면 선점이 풀려 **즉시** 다시 가져갈 수 있다."""
    log_id = await _insert_undelivered(real_db_user_id)
    svc = QAService()

    async with async_session_factory() as s:
        claim = await svc.claim_replayable(
            s,
            user=_fake_user(real_db_user_id),
            question_text=QUESTION,
            history_state=HistoryState.NONE,
        )
        assert claim is not None
        gen = svc.stream_saved(db=s, claim=claim)
        await gen.__anext__()        # token 만 받고
        await gen.aclose()           # 연결 끊김

    row = await _read(log_id)
    assert row.replay_claimed_at is None     # 선점이 풀렸다
    assert row.replay_claim_token is None
    assert row.delivered is False            # 전달되지 않았다

    # 리스 만료를 기다리지 않고 바로 재시도가 가능하다.
    retry = await _claim_once(real_db_user_id)
    assert retry is not None
    assert retry.qa_log_id == log_id


@pytest.mark.asyncio
async def test_expired_lease_can_be_reclaimed(real_db_user_id):
    """해제조차 못 돌아간 선점도 **리스 만료 뒤** 다시 가져갈 수 있다.

    프로세스가 죽는 등으로 해제가 못 돌아가면 행이 영구히 잠길 위험이 있다.
    """
    stale = datetime.now(timezone.utc) - timedelta(
        seconds=REPLAY_CLAIM_LEASE_SECONDS + 5
    )
    log_id = await _insert_undelivered(
        real_db_user_id, claimed_at=stale, claim_token="dead-process-token"
    )

    claim = await _claim_once(real_db_user_id)

    assert claim is not None
    assert claim.qa_log_id == log_id
    assert claim.claim_token != "dead-process-token"


@pytest.mark.asyncio
async def test_fresh_lease_blocks_reclaim(real_db_user_id):
    """아직 유효한 선점은 다시 가져갈 수 없다 (리스가 너무 짧으면 중복 재생)."""
    fresh = datetime.now(timezone.utc)
    await _insert_undelivered(
        real_db_user_id, claimed_at=fresh, claim_token="live-token"
    )

    assert await _claim_once(real_db_user_id) is None


@pytest.mark.asyncio
async def test_release_only_touches_own_claim(real_db_user_id):
    """해제는 **자기 토큰**의 선점만 푼다.

    토큰을 안 보고 풀면, 리스 만료로 다른 요청이 이미 가져간 선점을 지워 중복 재생을
    허용하게 된다.
    """
    from api.src.services.qa_service import ReplayClaim

    now = datetime.now(timezone.utc)
    log_id = await _insert_undelivered(
        real_db_user_id, claimed_at=now, claim_token="owner-token"
    )
    svc = QAService()
    stranger = ReplayClaim(
        qa_log_id=log_id,
        claim_token="stranger-token",
        answer_text="x",
        input_tokens=0,
        output_tokens=0,
        rule_matched=False,
        user_id=real_db_user_id,
    )

    async with async_session_factory() as s:
        await svc._release_replay_claim(s, stranger)

    row = await _read(log_id)
    assert row.replay_claimed_at is not None      # 남의 선점은 그대로다
    assert row.replay_claim_token == "owner-token"


@pytest.mark.asyncio
async def test_context_key_mismatch_is_not_claimable(real_db_user_id):
    """맥락 지문이 다르면 선점 후보가 아니다 (검수 P0-1 — 실제 DB 로 재확인)."""
    scaling_key = history_context_key([111])
    implant_key = history_context_key([777])
    await _insert_undelivered(real_db_user_id, context_key=scaling_key)

    svc = QAService()
    async with async_session_factory() as s:
        claim = await svc.claim_replayable(
            s,
            user=_fake_user(real_db_user_id),
            question_text=QUESTION,
            history_context_key=implant_key,
            explicit_retry=True,
            history_state=HistoryState.VERIFIED,
        )
    assert claim is None

    # 같은 지문 + 명시적 재시도면 가져온다.
    async with async_session_factory() as s:
        claim = await svc.claim_replayable(
            s,
            user=_fake_user(real_db_user_id),
            question_text=QUESTION,
            history_context_key=scaling_key,
            explicit_retry=True,
            history_state=HistoryState.VERIFIED,
        )
    assert claim is not None


@pytest.mark.asyncio
async def test_contextual_answer_is_not_autoreplayed_to_first_question(
    real_db_user_id,
):
    """대화 중 만든 답변은 "맥락 없는 요청" 에 자동 재생되지 않는다."""
    await _insert_undelivered(
        real_db_user_id, context_key=history_context_key([111])
    )
    assert await _claim_once(real_db_user_id) is None


@pytest.mark.asyncio
async def test_other_users_undelivered_answer_is_not_claimable(real_db_user_id):
    """소유권 — 다른 사용자의 미전송 답변은 선점 대상이 아니다."""
    await _insert_undelivered(real_db_user_id)

    # 존재하지 않을 만큼 큰 사용자 id 로 시도.
    claim = await _claim_once(real_db_user_id + 10_000_000)
    assert claim is None
