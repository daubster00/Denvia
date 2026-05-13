"""Story 9.3 — admin_support_service unit tests (확장 영역).

대상:
- _escape_ilike (q ILIKE escape)
- _kst_date_range (날짜 → datetime UTC 변환)
- _FORWARD_TRANSITIONS (force 분기)
- get_inquiry: subscription_status 매핑 (pro/free/blocked)
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.src.services import admin_support_service as svc


class TestEscapeIlike:
    def test_escape_percent(self):
        assert svc._escape_ilike("환불%") == "환불\\%"

    def test_escape_underscore(self):
        assert svc._escape_ilike("a_b") == "a\\_b"

    def test_escape_backslash(self):
        assert svc._escape_ilike("a\\b") == "a\\\\b"

    def test_no_escape_for_plain(self):
        assert svc._escape_ilike("환불") == "환불"


class TestKstDateRange:
    def test_both_none(self):
        s, e = svc._kst_date_range(None, None)
        assert s is None
        assert e is None

    def test_from_only_returns_kst_midnight(self):
        s, e = svc._kst_date_range(date(2026, 5, 1), None)
        assert s is not None and e is None
        assert s.tzinfo is not None
        assert s.year == 2026 and s.month == 5 and s.day == 1
        assert s.hour == 0 and s.minute == 0

    def test_to_includes_full_day(self):
        # to=2026-05-01 → 결과 끝은 2026-05-02 00:00 KST (exclusive)
        s, e = svc._kst_date_range(None, date(2026, 5, 1))
        assert e is not None
        assert e.day == 2  # +1일


class TestForwardTransitions:
    def test_open_can_go_to_in_progress(self):
        assert "in_progress" in svc._FORWARD_TRANSITIONS["open"]

    def test_open_can_go_to_resolved(self):
        assert "resolved" in svc._FORWARD_TRANSITIONS["open"]

    def test_in_progress_can_resolve(self):
        assert "resolved" in svc._FORWARD_TRANSITIONS["in_progress"]

    def test_resolved_blocks_revert_without_force(self):
        # resolved → 무엇이든 force 필요
        assert svc._FORWARD_TRANSITIONS["resolved"] == set()


class TestRecentQALimit:
    def test_recent_qa_limit_is_3(self):
        # Story 6.1은 10건. 9.3은 3건만 보여줌(컨텍스트용).
        assert svc._RECENT_QA_LIMIT == 3


def _make_inquiry_row(subscription_status: str = "free"):
    """get_inquiry SELECT 결과 row mock."""
    row = MagicMock()
    row.id = 7
    row.user_id = 10
    row.email = "user@example.com"
    row.phone = "01012345678"
    row.segment = "doctor"
    row.subscription_status = subscription_status
    row.user_created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    row.subject = "결제 환불"
    row.body = "문의 본문"
    row.inquiry_type = "billing"
    row.status = "open"
    row.created_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
    row.resolved_at = None
    return row


class TestGetInquirySubscriptionStatusMapping:
    """users.subscription_status 가 'pro' 인 경우 그대로 'pro' 로 응답되어야 함.

    이전엔 schema 가 'active' 만 허용해 service 가 'pro' 를 'free' 로 깎아내렸다 → 코드리뷰 지적.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "raw_status,expected",
        [
            ("free", "free"),
            ("pro", "pro"),
            ("blocked", "blocked"),
            ("unknown_value", "free"),  # 미지의 값은 free 로 fallback
        ],
    )
    async def test_subscription_status_passthrough(self, raw_status, expected):
        row = _make_inquiry_row(subscription_status=raw_status)
        select_result = MagicMock()
        select_result.first = MagicMock(return_value=row)

        db = MagicMock()
        db.execute = AsyncMock(return_value=select_result)

        with (
            patch.object(svc, "_fetch_recent_qa", new=AsyncMock(return_value=[])),
            patch.object(svc, "_fetch_replies", new=AsyncMock(return_value=[])),
        ):
            detail = await svc.get_inquiry(db, inquiry_id=7)

        assert detail is not None
        assert detail.user_subscription_status == expected


# ──────────────────────────────────────────────────────────────────────────────
# delete_reply auto-revert (Story 9.3 v1.1 후속 — 답변 전체 삭제 시 status='open' 자동 복귀)
# ──────────────────────────────────────────────────────────────────────────────


def _make_detail_stub(status: str = "open"):
    """get_inquiry 반환 stub — delete_reply 마지막 줄에서만 호출됨."""
    from api.src.schemas.admin.support import InquiryDetailResponse

    return InquiryDetailResponse(
        id=7,
        user_id=10,
        user_email="user@example.com",
        user_phone="01012345678",
        subject="결제 환불",
        body="문의 본문",
        status=status,
        created_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        resolved_at=None if status != "resolved" else datetime(2026, 5, 2, tzinfo=timezone.utc),
        user_segment="doctor",
        user_subscription_status="pro",
        user_created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        recent_qa=[],
        replies=[],
    )


def _make_delete_reply_db(
    *,
    reply_exists: bool,
    current_status: str,
    remaining_count: int,
    inbox_deleted_count: int = 1,
):
    """delete_reply 내부 4회 execute 호출을 시나리오별로 시뮬레이션.

    호출 순서:
      1) select(InquiryReply) — reply row → scalar_one_or_none()
      2) select(CustomerInquiry) — inquiry row → scalar_one()
      3) sa_delete(InboxMessage) — rowcount
      4) select(func.count()).select_from(InquiryReply) → scalar_one()
    """
    reply_row_result = MagicMock()
    if reply_exists:
        reply_obj = MagicMock()
        reply_obj.id = 42
        reply_obj.inquiry_id = 7
        reply_row_result.scalar_one_or_none = MagicMock(return_value=reply_obj)
    else:
        reply_row_result.scalar_one_or_none = MagicMock(return_value=None)

    inquiry = MagicMock()
    inquiry.id = 7
    inquiry.status = current_status
    inquiry.resolved_at = (
        datetime(2026, 5, 2, tzinfo=timezone.utc) if current_status == "resolved" else None
    )
    inquiry_result = MagicMock()
    inquiry_result.scalar_one = MagicMock(return_value=inquiry)

    inbox_result = MagicMock()
    inbox_result.rowcount = inbox_deleted_count

    count_result = MagicMock()
    count_result.scalar_one = MagicMock(return_value=remaining_count)

    db = MagicMock()
    if reply_exists:
        db.execute = AsyncMock(
            side_effect=[reply_row_result, inquiry_result, inbox_result, count_result]
        )
    else:
        # reply 없으면 첫 execute 후 즉시 return None — 이후 execute 호출 없음.
        db.execute = AsyncMock(side_effect=[reply_row_result])
    db.delete = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db, inquiry


class TestDeleteReplyAutoRevert:
    """답변 전체 삭제 시 status='resolved' → 'open' 자동 되돌림.

    조건:
      - remaining_replies == 0 AND inquiry.status == 'resolved' 일 때만 revert.
      - revert 시 resolved_at = None 동기 정리.
      - audit_diff JSON 에 status_reverted / status_before / status_after 기록.

    이 로직은 라우터 mocked 통합 테스트가 service 자체를 patch 처리해 검증 못 함 —
    service 함수를 직접 호출해 분기 4종을 망라한다.
    """

    @pytest.mark.asyncio
    async def test_last_reply_deleted_from_resolved_reverts_to_open(self):
        db, inquiry = _make_delete_reply_db(
            reply_exists=True, current_status="resolved", remaining_count=0
        )
        request = MagicMock()
        request.state = MagicMock()

        with patch.object(
            svc, "get_inquiry", new=AsyncMock(return_value=_make_detail_stub(status="open"))
        ):
            result = await svc.delete_reply(request, db, 7, 42, admin_id=99)

        assert result is not None
        assert inquiry.status == "open"
        assert inquiry.resolved_at is None
        db.commit.assert_awaited_once()

        import json as _json

        diff = _json.loads(request.state.audit_diff)
        assert diff["status_reverted"] is True
        assert diff["status_before"] == "resolved"
        assert diff["status_after"] == "open"
        assert diff["remaining_replies"] == 0
        assert diff["inbox_deleted"] == 1

    @pytest.mark.asyncio
    async def test_one_reply_remaining_keeps_status(self):
        # 2건 중 1건 삭제 → 남은 1건 → status 불변.
        db, inquiry = _make_delete_reply_db(
            reply_exists=True, current_status="resolved", remaining_count=1
        )
        request = MagicMock()
        request.state = MagicMock()

        with patch.object(
            svc, "get_inquiry", new=AsyncMock(return_value=_make_detail_stub(status="resolved"))
        ):
            await svc.delete_reply(request, db, 7, 42, admin_id=99)

        assert inquiry.status == "resolved"
        assert inquiry.resolved_at is not None  # 그대로 유지

        import json as _json

        diff = _json.loads(request.state.audit_diff)
        assert diff["status_reverted"] is False
        assert diff["status_before"] == "resolved"
        assert diff["status_after"] == "resolved"
        assert diff["remaining_replies"] == 1

    @pytest.mark.asyncio
    async def test_last_reply_deleted_from_in_progress_keeps_status(self):
        # remaining=0 이어도 status='resolved' 가 아니면 revert 트리거 X.
        db, inquiry = _make_delete_reply_db(
            reply_exists=True, current_status="in_progress", remaining_count=0
        )
        request = MagicMock()
        request.state = MagicMock()

        with patch.object(
            svc, "get_inquiry", new=AsyncMock(return_value=_make_detail_stub(status="in_progress"))
        ):
            await svc.delete_reply(request, db, 7, 42, admin_id=99)

        assert inquiry.status == "in_progress"
        assert inquiry.resolved_at is None  # 원래도 None

        import json as _json

        diff = _json.loads(request.state.audit_diff)
        assert diff["status_reverted"] is False
        assert diff["status_before"] == "in_progress"
        assert diff["status_after"] == "in_progress"

    @pytest.mark.asyncio
    async def test_reply_not_found_returns_none_without_side_effects(self):
        db, inquiry = _make_delete_reply_db(
            reply_exists=False, current_status="resolved", remaining_count=0
        )
        request = MagicMock()
        request.state = MagicMock()

        # get_inquiry 는 호출되지 않아야 함 — patch 하되 호출 안 됐다는 사실로 검증.
        get_inquiry_mock = AsyncMock(return_value=_make_detail_stub())
        with patch.object(svc, "get_inquiry", new=get_inquiry_mock):
            result = await svc.delete_reply(request, db, 7, 999, admin_id=99)

        assert result is None
        # status 변경 / delete / commit 모두 호출 안 됨.
        assert inquiry.status == "resolved"  # 진입 시점 그대로
        db.delete.assert_not_awaited()
        db.commit.assert_not_awaited()
        get_inquiry_mock.assert_not_awaited()
