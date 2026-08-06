"""#141 재시도 재생 로직 테스트 — stream_saved / find_replayable.

DB는 AsyncMock으로 격리한다(pytest asyncio mode=auto).
"""

import json
from unittest.mock import AsyncMock, MagicMock

from api.src.models.qa_log import QALog
from api.src.models.user import User
from api.src.services.qa_service import QAService


async def _collect(gen) -> list[dict]:
    return [ev async for ev in gen]


async def test_stream_saved_replays_answer_and_marks_delivered():
    svc = QAService()
    db = AsyncMock()
    log = QALog(
        id=123,
        user_id=1,
        question_text="임플란트 보험",
        answer_text="임플란트는 보험 적용이 제한적입니다.",
        rule_matched=False,
        status="completed",
        delivered=False,
        input_tokens=10,
        output_tokens=20,
    )

    events = await _collect(svc.stream_saved(db=db, log=log))

    # 중복 재생 방지 — delivered=True 마킹 + commit
    assert log.delivered is True
    db.commit.assert_awaited()

    kinds = [e["event"] for e in events]
    assert kinds == ["token", "done"]
    token = json.loads(events[0]["data"])
    assert token["delta"] == "임플란트는 보험 적용이 제한적입니다."
    done = json.loads(events[1]["data"])
    assert done["qa_log_id"] == 123
    assert done["replayed"] is True
    assert done["cost_usd"] == 0.0  # 재생은 무료(원 질의에서 이미 과금)


async def test_stream_saved_empty_answer_yields_only_done():
    svc = QAService()
    db = AsyncMock()
    log = QALog(
        id=1, user_id=1, question_text="q", answer_text="",
        status="completed", delivered=False,
    )
    events = await _collect(svc.stream_saved(db=db, log=log))
    assert [e["event"] for e in events] == ["done"]


async def test_find_replayable_returns_scalar_result():
    svc = QAService()
    db = AsyncMock()
    sentinel = QALog(id=9, user_id=1, question_text="q", status="completed", delivered=False)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = sentinel
    db.execute = AsyncMock(return_value=result_mock)

    user = MagicMock(spec=User)
    user.id = 1

    out = await svc.find_replayable(db, user=user, question_text="q")

    assert out is sentinel
    db.execute.assert_awaited()
