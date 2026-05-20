"""Story 6.1 — admin_user_service 단위 테스트.

본 테스트는 OR-검색 분기 결정·페이지네이션·is_blocked 매핑·404 분기 같은
service 레이어 책임을 mock DB로 검증한다.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from api.src.services import admin_user_service
from api.src.services.admin_user_service import (
    _build_or_clause,
    _is_card_last4_query,
    _resolve_active_billing_keys,
    _serialize_user,
)


def _make_user(
    *,
    user_id: int = 1,
    email: str = "user@example.com",
    phone: str | None = "01012345678",
    segment: str | None = "doctor",
    years_of_experience: int | None = 5,
    subscription_status: str = "free",
    daily_quota_override: int | None = None,
    withdrawn_at: datetime | None = None,
) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.email = email
    user.phone = phone
    user.segment = segment
    user.years_of_experience = years_of_experience
    user.subscription_status = subscription_status
    user.daily_quota_override = daily_quota_override
    user.withdrawn_at = withdrawn_at
    user.created_at = datetime(2026, 4, 1, tzinfo=timezone.utc)
    return user


def _stub_db_execute(values: list) -> AsyncMock:
    """db.execute가 순차적으로 values를 반환하도록 AsyncMock 구성."""
    db = MagicMock()
    db.execute = AsyncMock(side_effect=values)
    return db


class TestCardLast4Branching:
    def test_4digit_numeric_triggers_card_branch(self):
        assert _is_card_last4_query("1234") is True

    def test_3digit_numeric_does_not_trigger(self):
        assert _is_card_last4_query("123") is False

    def test_5digit_numeric_does_not_trigger(self):
        assert _is_card_last4_query("12345") is False

    def test_4chars_non_numeric_does_not_trigger(self):
        assert _is_card_last4_query("abcd") is False

    def test_empty_q_returns_none_or_clause(self):
        assert _build_or_clause(None) is None
        assert _build_or_clause("") is None


class TestSerializeUser:
    def test_blocked_status_maps_to_is_blocked_true(self):
        user = _make_user(subscription_status="blocked")
        item = _serialize_user(user, None)
        assert item.is_blocked is True
        assert item.subscription_status == "blocked"

    def test_pro_status_does_not_set_is_blocked(self):
        user = _make_user(subscription_status="pro")
        item = _serialize_user(user, None)
        assert item.is_blocked is False
        assert item.subscription_status == "pro"

    def test_serialize_includes_billing_when_provided(self):
        user = _make_user()
        item = _serialize_user(user, ("4321", "삼성카드"))
        assert item.card_last4 == "4321"
        assert item.card_company == "삼성카드"

    def test_serialize_billing_none_when_no_active_key(self):
        user = _make_user()
        item = _serialize_user(user, None)
        assert item.card_last4 is None
        assert item.card_company is None

    def test_pro_since_and_last_login_are_null_in_story_6_1(self):
        """Story 6.2가 컬럼 추가 후 채울 자리 — 본 스토리는 null 고정."""
        user = _make_user(subscription_status="pro")
        item = _serialize_user(user, None)
        assert item.pro_since is None
        assert item.last_login_at is None
        assert item.block_until is None


@pytest.mark.asyncio
class TestResolveActiveBillingKeys:
    async def test_empty_user_ids_returns_empty_dict(self):
        db = MagicMock()
        result = await _resolve_active_billing_keys(db, [])
        assert result == {}

    async def test_single_billing_key_per_user(self):
        row1 = MagicMock(user_id=1, card_last4="1234", card_company="신한")
        row2 = MagicMock(user_id=2, card_last4="5678", card_company="삼성")
        result_mock = MagicMock()
        result_mock.all = MagicMock(return_value=[row1, row2])
        db = MagicMock()
        db.execute = AsyncMock(return_value=result_mock)

        out = await _resolve_active_billing_keys(db, [1, 2])
        assert out == {1: ("1234", "신한"), 2: ("5678", "삼성")}

    async def test_duplicate_active_keys_picks_max_card_last4(self):
        """비정상 상태에서 결정론적 선택 — MAX(card_last4) 채택."""
        row_a = MagicMock(user_id=1, card_last4="1111", card_company="A")
        row_b = MagicMock(user_id=1, card_last4="9999", card_company="B")
        result_mock = MagicMock()
        result_mock.all = MagicMock(return_value=[row_a, row_b])
        db = MagicMock()
        db.execute = AsyncMock(return_value=result_mock)

        out = await _resolve_active_billing_keys(db, [1])
        assert out[1] == ("9999", "B")


@pytest.mark.asyncio
class TestSearchUsers:
    async def test_search_with_no_filters_returns_all(self):
        users = [_make_user(user_id=1), _make_user(user_id=2)]
        # 1) count, 2) items, 3) billing keys
        count_res = MagicMock()
        count_res.scalar_one = MagicMock(return_value=2)
        items_res = MagicMock()
        items_res.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=users))
        )
        billing_res = MagicMock()
        billing_res.all = MagicMock(return_value=[])

        db = _stub_db_execute([count_res, items_res, billing_res])
        out = await admin_user_service.search_users(db)
        assert out.total == 2
        assert len(out.items) == 2
        assert out.page == 1
        assert out.per_page == 20

    async def test_search_with_q_includes_or_clause(self):
        users = [_make_user(email="abc@naver.com")]
        count_res = MagicMock()
        count_res.scalar_one = MagicMock(return_value=1)
        items_res = MagicMock()
        items_res.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=users))
        )
        billing_res = MagicMock()
        billing_res.all = MagicMock(return_value=[])

        db = _stub_db_execute([count_res, items_res, billing_res])
        out = await admin_user_service.search_users(db, q="naver")
        assert out.total == 1
        assert out.items[0].email == "abc@naver.com"

    async def test_search_with_card_last4_4digit_branch(self):
        users = [_make_user(user_id=42)]
        count_res = MagicMock()
        count_res.scalar_one = MagicMock(return_value=1)
        items_res = MagicMock()
        items_res.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=users))
        )
        # billing_keys에 카드 매칭 결과
        billing_row = MagicMock(user_id=42, card_last4="1234", card_company="신한")
        billing_res = MagicMock()
        billing_res.all = MagicMock(return_value=[billing_row])

        db = _stub_db_execute([count_res, items_res, billing_res])
        out = await admin_user_service.search_users(db, q="1234")
        assert out.total == 1
        assert out.items[0].card_last4 == "1234"

    async def test_search_includes_withdrawn_users(self):
        withdrawn_user = _make_user(
            user_id=9,
            email="withdrawn_9_abcdef",
            phone=None,
            withdrawn_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        )
        count_res = MagicMock()
        count_res.scalar_one = MagicMock(return_value=1)
        items_res = MagicMock()
        items_res.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[withdrawn_user]))
        )
        billing_res = MagicMock()
        billing_res.all = MagicMock(return_value=[])

        db = _stub_db_execute([count_res, items_res, billing_res])
        out = await admin_user_service.search_users(db)
        assert out.total == 1
        assert out.items[0].withdrawn_at is not None

    async def test_search_pagination_respects_page_per_page(self):
        users = [_make_user(user_id=i) for i in range(1, 6)]
        count_res = MagicMock()
        count_res.scalar_one = MagicMock(return_value=152)
        items_res = MagicMock()
        items_res.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=users))
        )
        billing_res = MagicMock()
        billing_res.all = MagicMock(return_value=[])

        db = _stub_db_execute([count_res, items_res, billing_res])
        out = await admin_user_service.search_users(db, page=3, per_page=5)
        assert out.total == 152
        assert out.page == 3
        assert out.per_page == 5

    async def test_search_blocked_filter_only_blocked(self):
        blocked_user = _make_user(user_id=10, subscription_status="blocked")
        count_res = MagicMock()
        count_res.scalar_one = MagicMock(return_value=1)
        items_res = MagicMock()
        items_res.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[blocked_user]))
        )
        billing_res = MagicMock()
        billing_res.all = MagicMock(return_value=[])

        db = _stub_db_execute([count_res, items_res, billing_res])
        out = await admin_user_service.search_users(db, blocked=True)
        assert out.total == 1
        assert out.items[0].is_blocked is True
        assert out.items[0].subscription_status == "blocked"


@pytest.mark.asyncio
class TestGetUserDetail:
    async def test_user_not_found_raises_404(self):
        miss_res = MagicMock()
        miss_res.scalar_one_or_none = MagicMock(return_value=None)
        db = _stub_db_execute([miss_res])

        with pytest.raises(HTTPException) as exc_info:
            await admin_user_service.get_user_detail(db, 99999)
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail["code"] == "ADMIN_USER_NOT_FOUND"

    async def test_user_found_returns_detail_response(self):
        user = _make_user(user_id=1, subscription_status="pro")
        # 1) user lookup
        user_res = MagicMock()
        user_res.scalar_one_or_none = MagicMock(return_value=user)
        # 2) billing keys (active)
        billing_row = MagicMock(user_id=1, card_last4="1234", card_company="신한")
        billing_res = MagicMock()
        billing_res.all = MagicMock(return_value=[billing_row])
        # 3) subscription
        subscription = MagicMock(
            started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            next_charge_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        )
        sub_res = MagicMock()
        sub_res.scalar_one_or_none = MagicMock(return_value=subscription)
        # 4) qa_logs
        qa_row = MagicMock(
            id=1,
            question_text="가" * 100,
            answer_text="나" * 200,
            input_tokens=120,
            output_tokens=380,
            cost_usd=Decimal("0.0042"),
            status="completed",
            created_at=datetime(2026, 4, 30, tzinfo=timezone.utc),
        )
        qa_res = MagicMock()
        qa_res.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[qa_row]))
        )
        # 5) anomaly events (empty)
        anomaly_res = MagicMock()
        anomaly_res.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[]))
        )

        db = _stub_db_execute(
            [user_res, billing_res, sub_res, qa_res, anomaly_res]
        )
        out = await admin_user_service.get_user_detail(db, 1)
        assert out.user.user_id == 1
        assert out.subscription_summary.billing_key_active is True
        assert out.subscription_summary.card_last4 == "1234"
        assert len(out.recent_qa) == 1
        assert out.recent_qa[0].question_excerpt == "가" * 100
        assert out.recent_qa[0].answer_excerpt == "나" * 200
        assert out.recent_qa[0].input_tokens == 120
        assert out.recent_anomaly_events == []

    async def test_withdrawn_user_returns_user_with_withdrawn_at(self):
        user = _make_user(
            user_id=2,
            email="withdrawn_2_abcdef",
            phone=None,
            withdrawn_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        )
        user_res = MagicMock()
        user_res.scalar_one_or_none = MagicMock(return_value=user)
        billing_res = MagicMock()
        billing_res.all = MagicMock(return_value=[])
        sub_res = MagicMock()
        sub_res.scalar_one_or_none = MagicMock(return_value=None)
        qa_res = MagicMock()
        qa_res.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[]))
        )
        anomaly_res = MagicMock()
        anomaly_res.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[]))
        )

        db = _stub_db_execute(
            [user_res, billing_res, sub_res, qa_res, anomaly_res]
        )
        out = await admin_user_service.get_user_detail(db, 2)
        assert out.user.withdrawn_at is not None
        assert out.subscription_summary.billing_key_active is False
        assert out.subscription_summary.subscription_started_at is None

    async def test_no_anomaly_events_returns_empty_list(self):
        user = _make_user(user_id=3)
        user_res = MagicMock()
        user_res.scalar_one_or_none = MagicMock(return_value=user)
        billing_res = MagicMock()
        billing_res.all = MagicMock(return_value=[])
        sub_res = MagicMock()
        sub_res.scalar_one_or_none = MagicMock(return_value=None)
        qa_res = MagicMock()
        qa_res.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[]))
        )
        anomaly_res = MagicMock()
        anomaly_res.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[]))
        )

        db = _stub_db_execute(
            [user_res, billing_res, sub_res, qa_res, anomaly_res]
        )
        out = await admin_user_service.get_user_detail(db, 3)
        assert out.recent_anomaly_events == []
