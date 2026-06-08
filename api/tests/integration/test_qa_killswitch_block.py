"""QA 킬스위치 차단 통합 테스트 — Story 5.2 (AC-7)."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest
from httpx import ASGITransport, AsyncClient

from api.src.main import app
from api.src.models.base import get_session
from api.src.settings import settings


def _make_jwt(role: str = "user", sub_status: str = "free") -> str:
    payload = {
        "sub": "10",
        "role": role,
        "sub_status": sub_status,
        "exp": int(time.time()) + 3600,
    }
    return pyjwt.encode(payload, settings.denvia_jwt_secret, algorithm=settings.denvia_jwt_algorithm)


def _make_user(role: str = "user", subscription_status: str = "free"):
    user = MagicMock()
    user.id = 10
    user.email = "test@denvia.com"
    user.role = role
    user.subscription_status = subscription_status
    user.segment = None
    user.withdrawn_at = None
    user.must_reset_password = False
    user.daily_quota_override = None
    user.free_delay_override = None
    user.current_session_id = None
    user.admin_grade = "master"
    return user


def _mock_db_with_modes(modes: list[str]):
    """killswitch 상태 반환용 DB session mock."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = modes
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()

    async def gen():
        yield session

    return gen


@pytest.mark.asyncio
class TestQAKillswitchBlock:
    async def test_auto_free_only_무료_사용자_429(self):
        """auto_free_only 활성 + 무료 사용자 → 429 BUDGET_HARD_CAP_REACHED."""
        token = _make_jwt(sub_status="free")
        user = _make_user(subscription_status="free")
        gen = _mock_db_with_modes(["auto_free_only"])

        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)),
        ):
            app.dependency_overrides[get_session] = gen
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post(
                    "/api/v1/qa/stream",
                    json={"question_text": "임플란트 비용?"},
                    cookies={"denvia_session": token},
                )
            app.dependency_overrides.clear()

        assert res.status_code == 429
        data = res.json()
        assert data["code"] == "BUDGET_HARD_CAP_REACHED"

    async def test_auto_free_only_유료_사용자_통과(self):
        """auto_free_only 활성 + 유료 사용자 → 차단 안 됨 (preflight까지 진행)."""
        token = _make_jwt(sub_status="pro")
        user = _make_user(subscription_status="pro")
        # auto_free_only만 있으면 pro는 통과해야 함
        gen = _mock_db_with_modes(["auto_free_only"])

        # preflight와 stream을 mock해서 실제 RAG 호출 없이 응답 완료
        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)),
            patch("api.src.services.qa_service.QAService.preflight", new_callable=AsyncMock),
            patch(
                "api.src.services.qa_service.QAService.stream",
                return_value=_mock_stream(),
            ),
        ):
            app.dependency_overrides[get_session] = gen
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post(
                    "/api/v1/qa/stream",
                    json={"question_text": "임플란트 비용?"},
                    cookies={"denvia_session": token},
                )
            app.dependency_overrides.clear()

        # 차단 에러(429/503)가 아님
        assert res.status_code != 429
        assert res.status_code != 503

    async def test_manual_total_모든_사용자_503(self):
        """manual_total 활성 → 유료/무료 관계없이 503 SERVICE_KILL_SWITCH."""
        for sub_status in ("free", "pro"):
            token = _make_jwt(sub_status=sub_status)
            user = _make_user(subscription_status=sub_status)
            gen = _mock_db_with_modes(["manual_total"])

            with patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)):
                app.dependency_overrides[get_session] = gen
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.post(
                        "/api/v1/qa/stream",
                        json={"question_text": "임플란트 비용?"},
                        cookies={"denvia_session": token},
                    )
                app.dependency_overrides.clear()

            assert res.status_code == 503, f"sub_status={sub_status} expected 503"
            # Story 9.2 AC-7: 503 코드를 spec 일관성을 위해 KILLSWITCH_ACTIVE로 통일.
            assert res.json()["code"] == "KILLSWITCH_ACTIVE"

    async def test_킬스위치_없을_때_정상_진행(self):
        """활성 킬스위치 없음 → 정상적으로 preflight로 넘어감."""
        token = _make_jwt(sub_status="free")
        user = _make_user(subscription_status="free")
        gen = _mock_db_with_modes([])

        with (
            patch("api.src.deps.auth.get_user_by_id", new=AsyncMock(return_value=user)),
            patch("api.src.services.qa_service.QAService.preflight", new_callable=AsyncMock),
            patch(
                "api.src.services.qa_service.QAService.stream",
                return_value=_mock_stream(),
            ),
        ):
            app.dependency_overrides[get_session] = gen
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post(
                    "/api/v1/qa/stream",
                    json={"question_text": "임플란트 비용?"},
                    cookies={"denvia_session": token},
                )
            app.dependency_overrides.clear()

        assert res.status_code not in (429, 503)


async def _mock_stream():
    """SSE stream mock — 빈 응답."""
    yield {"event": "done", "data": '{"qa_log_id": 1}'}
