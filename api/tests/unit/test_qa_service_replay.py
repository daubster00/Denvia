"""#141 재시도 재생 로직 테스트 — stream_saved / claim_replayable.

DB는 AsyncMock으로 격리한다(pytest asyncio mode=auto).

2026-11-03 재수정 P1-1 로 재생 구조가 바뀌었다.

- ``find_replayable``(평범한 SELECT) → ``claim_replayable``(조건부 ``UPDATE ... RETURNING``
  으로 재생 권한을 **선점**). 동시 요청 중 하나만 선점에 성공한다.
- ``stream_saved`` 는 ORM 엔티티가 아니라 ``ReplayClaim``(선점 결과)을 받고,
  ``delivered=true``(사용자 전달 완료)는 **재생을 끝까지 마친 뒤**에만 확정한다.

실제 원자성(동시 요청 2개 중 1개만 선점)은 목으로 증명할 수 없어
``api/tests/integration/test_qa_replay_claim.py`` 가 실제 PostgreSQL 로 검증한다.
"""

import json
from unittest.mock import AsyncMock, MagicMock

from api.src.models.user import User
from api.src.services.qa_service import QAService, ReplayClaim


async def _collect(gen) -> list[dict]:
    return [ev async for ev in gen]


def _claim(**over) -> ReplayClaim:
    base = dict(
        qa_log_id=123,
        claim_token="tok-123",
        answer_text="임플란트는 보험 적용이 제한적입니다.",
        input_tokens=10,
        output_tokens=20,
        rule_matched=False,
        user_id=1,
    )
    base.update(over)
    return ReplayClaim(**base)


async def test_stream_saved_replays_answer_and_marks_delivered():
    svc = QAService()
    db = AsyncMock()

    events = await _collect(svc.stream_saved(db=db, claim=_claim()))

    kinds = [e["event"] for e in events]
    assert kinds == ["token", "done"]
    token = json.loads(events[0]["data"])
    assert token["delta"] == "임플란트는 보험 적용이 제한적입니다."
    done = json.loads(events[1]["data"])
    assert done["qa_log_id"] == 123
    assert done["replayed"] is True
    assert done["cost_usd"] == 0.0  # 재생은 무료(원 질의에서 이미 과금)
    assert done["total_tokens"] == 30

    # 중복 재생 방지 — 재생을 끝까지 마친 뒤 delivered 확정 UPDATE + commit
    db.execute.assert_awaited()
    db.commit.assert_awaited()
    sqls = " ".join(str(c.args[0]).lower() for c in db.execute.await_args_list)
    assert "update qa_logs" in sqls
    assert "delivered" in sqls


async def test_stream_saved_empty_answer_yields_only_done():
    svc = QAService()
    db = AsyncMock()

    events = await _collect(svc.stream_saved(db=db, claim=_claim(answer_text="")))

    assert [e["event"] for e in events] == ["done"]
    # 빈 답변이라도 재생은 끝났으므로 delivered 는 확정한다.
    db.commit.assert_awaited()


async def test_stream_saved_does_not_mark_delivered_before_finishing():
    """재생 도중에는 delivered 를 세우지 않는다 (재수정 P1-1)."""
    svc = QAService()
    db = AsyncMock()

    gen = svc.stream_saved(db=db, claim=_claim())
    first = await gen.__anext__()

    assert first["event"] == "token"
    assert db.execute.await_count == 0   # 아직 아무 UPDATE 도 나가지 않았다

    # 끝까지 소비하면 그때 확정된다.
    await _collect(gen)
    db.execute.assert_awaited()


async def test_claim_replayable_returns_claim_from_returning_row():
    svc = QAService()
    db = AsyncMock()

    row = MagicMock()
    row.id = 9
    row.answer_text = "저장된 답변"
    row.input_tokens = 3
    row.output_tokens = 4
    row.rule_matched = False
    row.user_id = 1

    result_mock = MagicMock()
    result_mock.first.return_value = row
    db.execute = AsyncMock(return_value=result_mock)

    user = MagicMock(spec=User)
    user.id = 1

    out = await svc.claim_replayable(db, user=user, question_text="q")

    assert out is not None
    assert out.qa_log_id == 9
    assert out.answer_text == "저장된 답변"
    assert out.claim_token  # 선점 소유자 표식이 생성된다
    db.execute.assert_awaited()
    db.commit.assert_awaited()


async def test_claim_replayable_returns_none_when_no_row_claimed():
    """다른 요청이 먼저 선점했으면(0행) 재생하지 않는다."""
    svc = QAService()
    db = AsyncMock()

    result_mock = MagicMock()
    result_mock.first.return_value = None
    db.execute = AsyncMock(return_value=result_mock)

    user = MagicMock(spec=User)
    user.id = 1

    assert await svc.claim_replayable(db, user=user, question_text="q") is None
