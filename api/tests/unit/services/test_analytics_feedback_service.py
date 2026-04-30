"""Unit 테스트 — analytics_service 피드백 함수 (Story 5.4 AC-11)."""

from __future__ import annotations

import pytest

from api.src.services.analytics_service import get_feedback_summary


@pytest.mark.asyncio
async def test_good_ratio_zero_division():
    """good_count=bad_count=0 → good_ratio=None (ZeroDivisionError 방지)."""
    from unittest.mock import AsyncMock, MagicMock
    from datetime import datetime, timezone
    from api.src.services.budget_service import KST

    session = MagicMock()
    mock_rows = []
    mock_result = MagicMock()
    mock_result.all = MagicMock(return_value=mock_rows)
    session.execute = AsyncMock(return_value=mock_result)

    start = datetime(2026, 1, 1, tzinfo=KST)
    end = datetime(2026, 2, 1, tzinfo=KST)
    result = await get_feedback_summary(session, start, end, q_like=None)

    assert result["good_count"] == 0
    assert result["bad_count"] == 0
    assert result["good_ratio"] is None
