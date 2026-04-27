"""QAService.echo 단위 테스트 — AsyncMock으로 DB 세션 격리."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.src.models.qa_log import QALog
from api.src.models.user import User
from api.src.schemas.qa import QAEchoResponse
from api.src.services.qa_service import QAService, _ECHO_ANSWER


def _make_user(user_id: int = 1) -> User:
    user = MagicMock(spec=User)
    user.id = user_id
    return user


def _make_db(log_id: int = 42) -> AsyncMock:
    db = AsyncMock()

    async def _fake_refresh(obj):
        obj.id = log_id

    db.refresh = _fake_refresh
    db.add = MagicMock()
    return db


@pytest.mark.asyncio
async def test_echo_returns_response():
    svc = QAService()
    db = _make_db(log_id=7)
    user = _make_user(user_id=3)

    result = await svc.echo(db=db, user=user, question_text="임플란트 보험")

    assert isinstance(result, QAEchoResponse)
    assert result.qa_log_id == 7
    assert result.question_text == "임플란트 보험"
    assert result.rule_matched is False
    assert result.answer_text == _ECHO_ANSWER


@pytest.mark.asyncio
async def test_echo_inserts_qa_log():
    svc = QAService()
    db = _make_db(log_id=1)
    user = _make_user(user_id=5)

    await svc.echo(db=db, user=user, question_text="치료비 질문")

    db.add.assert_called_once()
    added: QALog = db.add.call_args[0][0]
    assert isinstance(added, QALog)
    assert added.user_id == 5
    assert added.question_text == "치료비 질문"
    assert added.rule_matched is False
    assert added.answer_text == _ECHO_ANSWER


@pytest.mark.asyncio
async def test_echo_commits():
    svc = QAService()
    db = _make_db()
    user = _make_user()

    await svc.echo(db=db, user=user, question_text="질문")

    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_echo_does_not_log_question_text(caplog):
    """PII 원칙 — question_text가 structlog 이벤트에 포함되면 안 됨."""
    import logging

    svc = QAService()
    db = _make_db()
    user = _make_user()
    sensitive = "매우민감한질문"

    with caplog.at_level(logging.INFO):
        await svc.echo(db=db, user=user, question_text=sensitive)

    for record in caplog.records:
        assert sensitive not in record.getMessage(), "question_text가 로그에 노출되면 안 됨"
