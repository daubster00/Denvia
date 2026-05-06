"""Story 6.5 — anomaly_tasks.scan_anomalies 단위 테스트.

Coverage:
- _scan_repeated_question_async: 0건 / 1그룹 5건 INSERT / 멱등 (이미 INSERT 시 skip)

DB 의존성은 module-level 패치로 격리한다.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def fake_session():
    s = MagicMock()
    s.added = []
    s.add = lambda obj: s.added.append(obj)
    s.execute = AsyncMock()
    s.commit = AsyncMock()
    return s


def _row(user_id: int, question: str, cnt: int):
    r = MagicMock()
    r.user_id = user_id
    r.question_text = question
    r.cnt = cnt
    r.last_at = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    return r


@pytest.mark.asyncio
async def test_scan_no_groups_returns_zero(fake_session):
    fake_session.execute.side_effect = [
        MagicMock(all=lambda: []),  # GROUP BY 결과 없음
    ]

    with patch(
        "api.src.workers.anomaly_tasks.create_async_engine"
    ) as mock_engine:
        mock_engine_inst = MagicMock()
        mock_engine_inst.dispose = AsyncMock()
        mock_engine.return_value = mock_engine_inst

        with patch(
            "api.src.workers.anomaly_tasks.async_sessionmaker"
        ) as mock_smkr:
            class _Ctx:
                async def __aenter__(self_inner):
                    return fake_session

                async def __aexit__(self_inner, *args):
                    return None

            mock_smkr.return_value = lambda: _Ctx()

            from api.src.workers import anomaly_tasks

            result = await anomaly_tasks._scan_repeated_question_async()
    assert result["inserted"] == 0
    assert fake_session.added == []


@pytest.mark.asyncio
async def test_scan_inserts_for_one_group(fake_session):
    rows = [_row(7, "동일질문?", 6)]
    # 1) GROUP BY rows
    # 2) exists_q for user 7 → 0
    fake_session.execute.side_effect = [
        MagicMock(all=lambda: rows),
        MagicMock(scalar_one=lambda: 0),
    ]

    with patch(
        "api.src.workers.anomaly_tasks.create_async_engine"
    ) as mock_engine:
        mock_engine_inst = MagicMock()
        mock_engine_inst.dispose = AsyncMock()
        mock_engine.return_value = mock_engine_inst

        with patch(
            "api.src.workers.anomaly_tasks.async_sessionmaker"
        ) as mock_smkr:
            class _Ctx:
                async def __aenter__(self_inner):
                    return fake_session

                async def __aexit__(self_inner, *args):
                    return None

            mock_smkr.return_value = lambda: _Ctx()

            from api.src.workers import anomaly_tasks

            result = await anomaly_tasks._scan_repeated_question_async()

    assert result["inserted"] == 1
    assert len(fake_session.added) == 1
    event = fake_session.added[0]
    assert event.type == "repeated_question"
    assert event.target_user_id == 7
    assert event.details["count_in_window"] == 6
    assert "question_excerpt" in event.details


@pytest.mark.asyncio
async def test_scan_idempotent_when_exists(fake_session):
    rows = [_row(7, "동일질문?", 6)]
    fake_session.execute.side_effect = [
        MagicMock(all=lambda: rows),
        MagicMock(scalar_one=lambda: 1),  # 이미 INSERT됨
    ]

    with patch(
        "api.src.workers.anomaly_tasks.create_async_engine"
    ) as mock_engine:
        mock_engine_inst = MagicMock()
        mock_engine_inst.dispose = AsyncMock()
        mock_engine.return_value = mock_engine_inst

        with patch(
            "api.src.workers.anomaly_tasks.async_sessionmaker"
        ) as mock_smkr:
            class _Ctx:
                async def __aenter__(self_inner):
                    return fake_session

                async def __aexit__(self_inner, *args):
                    return None

            mock_smkr.return_value = lambda: _Ctx()

            from api.src.workers import anomaly_tasks

            result = await anomaly_tasks._scan_repeated_question_async()

    assert result["inserted"] == 0
    assert fake_session.added == []
