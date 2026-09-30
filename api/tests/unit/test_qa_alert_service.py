"""질의응답 실패 몰림 → 관리자 알림톡 (2026-09-30 장애 후속).

여기서 보는 것은 세 가지다.
  1. 문턱(10분 3건) 아래면 아무것도 보내지 않는다 — 한두 건은 평소에도 난다.
  2. 문턱을 넘으면 `notification_queue` 에 넣는다.
  3. 같은 10분 구간에는 한 번만 — 멱등 키가 구간 단위로 잘린다.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.src.services import qa_alert_service as svc


def _make_session(failure_count: int) -> tuple[MagicMock, MagicMock]:
    """`async with async_session_factory() as s:` 를 흉내내는 (세션, 컨텍스트) 목."""
    session = MagicMock()

    count_result = MagicMock()
    count_result.scalar.return_value = failure_count

    insert_result = MagicMock()
    insert_result.rowcount = 1

    # 첫 execute = 실패 건수 SELECT, 두 번째 = 큐 INSERT
    session.execute = AsyncMock(side_effect=[count_result, insert_result])
    session.commit = AsyncMock()

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return session, ctx


def _patch_env(session_ctx, *, admin_phone: str | None = "01012345678"):
    admin = MagicMock()
    admin.id = 1
    return (
        patch("api.src.models.base.async_session_factory", return_value=session_ctx),
        patch(
            "api.src.integrations.messaging.admin_recipient.resolve_admin_target",
            new=AsyncMock(return_value=(admin if admin_phone else None, admin_phone)),
        ),
    )


@pytest.mark.asyncio
async def test_below_threshold_does_not_enqueue():
    """10분에 2건이면 조용히 넘어간다 — 알림톡이 울리면 안 된다."""
    session, ctx = _make_session(failure_count=2)
    p_factory, p_admin = _patch_env(ctx)

    with p_factory, p_admin:
        await svc.maybe_alert_admin_qa_failures(qa_log_id=101)

    # SELECT 한 번만 — INSERT 로 넘어가지 않았다
    assert session.execute.await_count == 1
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_threshold_reached_enqueues_alimtalk():
    """10분에 3건이면 관리자 알림톡을 큐에 넣는다."""
    session, ctx = _make_session(failure_count=3)
    p_factory, p_admin = _patch_env(ctx)

    with p_factory, p_admin:
        await svc.maybe_alert_admin_qa_failures(qa_log_id=102)

    assert session.execute.await_count == 2
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_no_admin_phone_skips_silently():
    """관리자 휴대폰이 비어 있으면 건너뛴다 — 예외를 던지면 안 된다."""
    session, ctx = _make_session(failure_count=5)
    p_factory, p_admin = _patch_env(ctx, admin_phone=None)

    with p_factory, p_admin:
        await svc.maybe_alert_admin_qa_failures(qa_log_id=103)

    assert session.execute.await_count == 1
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_alert_failure_is_swallowed():
    """알림 쪽에서 터져도 예외가 밖으로 새면 안 된다.

    이미 실패한 요청을 두 번 죽이는 꼴이 되면 안 되기 때문이다.
    """
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("DB down"))
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("api.src.models.base.async_session_factory", return_value=ctx):
        await svc.maybe_alert_admin_qa_failures(qa_log_id=104)  # 예외 없이 끝나야 한다


def test_window_bucket_is_stable_within_window():
    """같은 10분 안에서는 같은 키 → 구간당 알림톡 1통."""
    a = svc._window_bucket(datetime(2026, 9, 30, 5, 31, 0))
    b = svc._window_bucket(datetime(2026, 9, 30, 5, 39, 59))
    c = svc._window_bucket(datetime(2026, 9, 30, 5, 40, 0))

    assert a == b  # 5:31 과 5:39 는 같은 구간
    assert a != c  # 5:40 부터는 다음 구간
