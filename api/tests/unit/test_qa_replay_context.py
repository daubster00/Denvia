"""전송 실패 답변 재생의 대화 맥락 게이팅 + 원자적 선점 — 검수 P0-1 · 재수정 P0-3 · P1-1.

#141 재생 기능은 "같은 사용자 + 같은 질문 문자열 + 3분 이내 + 미전송" 만 봤다.
대화가 쌓이게 되면서 **다른 대화의 같은 조각 질문**("몇 번까지 돼?")에 엉뚱한 답변이
재생됐다(스케일링 답변이 임플란트 질문에). 치과 청구에서는 그대로 삭감으로 이어진다.

고정하는 규칙:
  1) 맥락 없는 요청(첫 질문 등)은 **기존과 동일하게** 자동 재생 — 단, 맥락 없이 만든
     답변만 후보(``history_context_key IS NULL``).
  2) 맥락 있는 요청은 맥락 지문이 **정확히 같고** 사용자가 명시적으로 재시도했을 때만.
  3) 맥락이 다르면 쿼리 결과가 없어 재생되지 않는다.
  4) **REJECTED**(맥락 id 를 보냈지만 전부 거부됨)는 아예 재생하지 않는다 — 재수정 P0-3.
     허용하면 맥락 키가 NULL 이라 "첫 질문" 후보에 걸려 다른 대화의 답변이 재생된다.
  5) 재생 권한은 조건부 ``UPDATE ... RETURNING`` 으로 **선점**한다 — 재수정 P1-1.
     ``delivered=true`` 는 재생을 끝까지 마친 뒤에만 확정하고, 중간에 끊기면 선점을 푼다.

동시 요청 2개 중 하나만 선점하는 **실제 원자성**은 목으로 증명할 수 없다.
그 검증은 실제 PostgreSQL 을 쓰는 ``api/tests/integration/test_qa_replay_claim.py`` 에 있다.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from api.src.models.user import User
from api.src.services.chat_history_service import HistoryState, history_context_key
from api.src.services.qa_service import QAService, ReplayClaim


def _make_user(user_id: int = 1) -> MagicMock:
    user = MagicMock(spec=User)
    user.id = user_id
    return user


class _ClaimRow:
    """선점 UPDATE ... RETURNING 이 돌려주는 한 행."""

    def __init__(self, log_id: int = 7, answer: str = "저장된 답변"):
        self.id = log_id
        self.answer_text = answer
        self.input_tokens = 10
        self.output_tokens = 20
        self.rule_matched = False
        self.user_id = 1


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _FakeDB:
    def __init__(self, row=None):
        self.row = row
        self.statements: list = []
        self.commits = 0

    async def execute(self, stmt):
        self.statements.append(stmt)
        return _FakeResult(self.row)

    async def commit(self):
        self.commits += 1

    def sql(self) -> str:
        return str(self.statements[-1])

    def params(self) -> dict:
        return self.statements[-1].compile().params


def _make_claim(**over) -> ReplayClaim:
    base = dict(
        qa_log_id=7,
        claim_token="tok-abc",
        answer_text="저장된 답변",
        input_tokens=10,
        output_tokens=20,
        rule_matched=False,
        user_id=1,
    )
    base.update(over)
    return ReplayClaim(**base)


# ──────────────────────────────────────────────────────────────────────────────
# 맥락 게이팅 (검수 P0-1)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_context_free_request_keeps_legacy_autoreplay():
    """첫 질문처럼 맥락이 없는 요청은 예전처럼 자동 재생된다(회귀 금지)."""
    svc = QAService()
    db = _FakeDB(row=_ClaimRow())

    claim = await svc.claim_replayable(
        db, user=_make_user(), question_text="스케일링 산정 기준"
    )

    assert claim is not None
    assert claim.qa_log_id == 7
    sql = db.sql().lower()
    # 맥락 없이 만든 답변만 후보 — 대화 중 만들어진 답변이 섞이면 안 된다.
    assert "history_context_key is null" in sql


@pytest.mark.asyncio
async def test_contextual_request_without_explicit_retry_never_replays():
    """맥락이 있는 질문은 사용자가 "다시 시도" 를 누르지 않으면 재생하지 않는다.

    쿼리 자체를 쏘지 않아야 한다(= 재생 후보를 찾지도 않는다).
    """
    svc = QAService()
    db = _FakeDB(row=_ClaimRow())

    claim = await svc.claim_replayable(
        db,
        user=_make_user(),
        question_text="몇 번까지 돼?",
        history_context_key=history_context_key([11, 12]),
        explicit_retry=False,
        history_state=HistoryState.VERIFIED,
    )

    assert claim is None
    assert db.statements == []


@pytest.mark.asyncio
async def test_contextual_retry_matches_only_same_context():
    """명시적 재시도 + 같은 맥락 지문일 때만 후보를 찾는다."""
    svc = QAService()
    db = _FakeDB(row=_ClaimRow())
    key = history_context_key([11, 12])

    claim = await svc.claim_replayable(
        db,
        user=_make_user(),
        question_text="몇 번까지 돼?",
        history_context_key=key,
        explicit_retry=True,
        history_state=HistoryState.VERIFIED,
    )

    assert claim is not None
    sql = db.sql().lower()
    assert "history_context_key =" in sql
    assert "history_context_key is null" not in sql
    assert key in db.params().values()


@pytest.mark.asyncio
async def test_different_conversation_yields_different_key():
    """스케일링 대화와 임플란트 대화는 서로 다른 지문을 갖는다.

    같은 질문 문자열이어도 지문이 달라 쿼리 조건이 달라지고, 상대 대화의 답변은
    후보로 잡히지 않는다.
    """
    svc = QAService()
    scaling_key = history_context_key([11])      # 스케일링 대화의 턴
    implant_key = history_context_key([77])      # 임플란트 대화의 턴
    assert scaling_key != implant_key

    db = _FakeDB(row=None)   # 다른 맥락이면 DB 에 후보가 없다
    claim = await svc.claim_replayable(
        db,
        user=_make_user(),
        question_text="몇 번까지 돼?",
        history_context_key=implant_key,
        explicit_retry=True,
        history_state=HistoryState.VERIFIED,
    )
    assert claim is None
    assert implant_key in db.params().values()
    assert scaling_key not in db.params().values()


# ──────────────────────────────────────────────────────────────────────────────
# REJECTED 상태는 자동 재생 금지 (재수정 P0-3)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("explicit_retry", [False, True])
async def test_rejected_history_never_replays(explicit_retry: bool):
    """맥락 id 를 보냈지만 전부 거부된 요청은 저장 답변을 재생하지 않는다.

    이 상태의 맥락 키는 NULL 이다. 허용하면 ``history_context_key IS NULL`` 후보에
    걸려 **전혀 다른 대화에서 만든 답변**이 자동 재생된다(= 검수 P0-1 결함 재발).
    재시도 버튼을 눌렀더라도 마찬가지다 — 재생할 '같은 맥락' 이 존재하지 않는다.
    """
    svc = QAService()
    db = _FakeDB(row=_ClaimRow())

    claim = await svc.claim_replayable(
        db,
        user=_make_user(),
        question_text="몇 번까지 돼?",
        history_context_key=None,     # 전부 거부 → 지문 없음
        explicit_retry=explicit_retry,
        history_state=HistoryState.REJECTED,
    )

    assert claim is None
    # 쿼리 자체를 쏘지 않는다.
    assert db.statements == []


# ──────────────────────────────────────────────────────────────────────────────
# 원자적 선점 · delivered 확정 시점 (재수정 P1-1)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_claim_uses_conditional_update_returning():
    """단순 SELECT 가 아니라 **조건부 UPDATE ... RETURNING** 이어야 한다."""
    svc = QAService()
    db = _FakeDB(row=_ClaimRow())

    await svc.claim_replayable(db, user=_make_user(), question_text="q")

    sql = db.sql().lower()
    assert sql.startswith("update qa_logs")
    assert "returning" in sql
    # 선점 컬럼을 세운다.
    assert "replay_claimed_at" in sql
    assert "replay_claim_token" in sql
    # 선점 가능 조건(없음 OR 리스 만료)이 WHERE 에 들어 있다.
    assert "replay_claimed_at is null" in sql
    # delivered 는 선점 단계에서 세우지 않는다 — 재생을 끝까지 마친 뒤에만 확정한다.
    assert "set delivered" not in sql


@pytest.mark.asyncio
async def test_claim_returns_none_when_update_hits_no_row():
    """다른 요청이 먼저 선점했으면 0행 → None (재생하지 않는다)."""
    svc = QAService()
    db = _FakeDB(row=None)

    claim = await svc.claim_replayable(db, user=_make_user(), question_text="q")

    assert claim is None


@pytest.mark.asyncio
async def test_replay_confirms_delivered_only_after_finishing():
    """재생을 끝까지 마친 **뒤에** delivered=true 를 확정한다."""
    svc = QAService()
    db = _FakeDB(row=None)
    claim = _make_claim()

    events: list[dict] = []
    async for ev in svc.stream_saved(db=db, claim=claim):
        # 아직 스트림이 끝나지 않은 시점 — delivered 확정 쿼리가 나가면 안 된다.
        assert all("set delivered" not in str(s).lower() for s in db.statements)
        events.append(ev)

    assert [ev["event"] for ev in events] == ["token", "done"]
    # 끝난 뒤에 delivered=true UPDATE 가 나갔다.
    assert any("delivered" in str(s).lower() for s in db.statements)
    assert db.commits == 1
    # 자기 선점만 건드린다 — claim_token 비교가 들어 있다.
    assert claim.claim_token in db.params().values()


@pytest.mark.asyncio
async def test_disconnect_during_replay_releases_the_claim():
    """재생 중 연결이 끊기면 delivered 를 세우지 않고 선점을 **즉시 푼다**.

    그래야 사용자가 다시 시도할 때 리스 만료(30초)를 기다리지 않고 바로 재생된다.
    """
    svc = QAService()
    db = _FakeDB(row=None)
    claim = _make_claim()

    gen = svc.stream_saved(db=db, claim=claim)
    first = await gen.__anext__()          # token 까지만 받고
    assert first["event"] == "token"
    await gen.aclose()                     # 연결 끊김 = GeneratorExit

    sqls = " ".join(str(s).lower() for s in db.statements)
    # 선점 해제 UPDATE 가 나갔다(두 컬럼을 NULL 로).
    assert "replay_claimed_at" in sqls
    assert "replay_claim_token" in sqls
    # delivered 는 세우지 않았다 — 전달되지 않았으므로 다음 재시도의 후보로 남아야 한다.
    assert "set delivered=" not in sqls.replace(" ", "")
    assert claim.claim_token in db.params().values()


@pytest.mark.asyncio
async def test_claim_release_failure_is_swallowed():
    """선점 해제가 실패해도 예외를 올리지 않는다 — 리스 만료로 복구된다."""
    svc = QAService()

    class _BoomDB(_FakeDB):
        async def execute(self, stmt):
            raise RuntimeError("DB 끊김")

    claim = _make_claim()
    await svc._release_replay_claim(_BoomDB(), claim)  # 예외가 새어 나오면 실패


def test_lease_constant_is_positive():
    """리스가 0 이하면 선점이 즉시 만료돼 중복 재생을 막지 못한다."""
    from api.src.services.qa_service import REPLAY_CLAIM_LEASE_SECONDS

    assert REPLAY_CLAIM_LEASE_SECONDS > 0
