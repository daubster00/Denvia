"""GET /api/v1/me/payments 핸들러 단위 테스트 — Story 4.4 (AC-3, AC-4, AC-9).

라우터 핸들러를 직접 호출해 응답 분기 + 페이지네이션 + status 매핑 + JOIN 매칭을
검증한다. SQLAlchemy 통합은 통합 테스트(test_me_payments_endpoint.py)로 보완.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from api.src.routers.me import get_my_payments


def _make_user(user_id: int = 1, email: str = "user@example.com") -> MagicMock:
    u = MagicMock()
    u.id = user_id
    u.email = email
    return u


def _row(
    payment_id: int,
    *,
    charged_at: datetime | None,
    amount_krw: int = 9900,
    provider_order_id: str = "sub-1-2026-04-30",
    status: str = "success",
    sub_started_at: datetime | None = None,
    sub_period_end: datetime | None = None,
    bk_card_last4: str | None = "1234",
    bk_card_company: str | None = "현대",
):
    """get_my_payments SELECT 결과 row 모킹."""
    r = MagicMock()
    r.id = payment_id
    r.charged_at = charged_at
    r.amount_krw = amount_krw
    r.provider_order_id = provider_order_id
    r.status = status
    r.sub_started_at = sub_started_at
    r.sub_period_end = sub_period_end
    r.bk_card_last4 = bk_card_last4
    r.bk_card_company = bk_card_company
    return r


def _make_db(*, total: int = 0, rows: list | None = None) -> AsyncMock:
    """COUNT 응답 + SELECT all() 응답을 순차적으로 반환하는 세션."""
    rows = rows or []

    count_result = MagicMock()
    count_result.scalar_one = MagicMock(return_value=total)

    select_result = MagicMock()
    select_result.all = MagicMock(return_value=rows)

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[count_result, select_result])
    return db


@pytest.mark.asyncio
class TestGetMyPaymentsHandler:
    async def test_per_page_invalid_raises_422(self):
        """per_page가 [10,20,50] 외 → 422 INVALID_PARAM."""
        user = _make_user()
        db = _make_db()

        with pytest.raises(HTTPException) as exc:
            await get_my_payments(current_user=user, db=db, page=1, per_page=15)

        assert exc.value.status_code == 422
        assert exc.value.detail["code"] == "INVALID_PARAM"
        # COUNT/SELECT는 검증 실패 직후 호출되지 않음
        db.execute.assert_not_called()

    async def test_empty_returns_zero_items(self):
        """결제 내역 0건 → items=[], total=0."""
        user = _make_user()
        db = _make_db(total=0, rows=[])

        res = await get_my_payments(current_user=user, db=db, page=1, per_page=20)

        assert res.items == []
        assert res.page == 1
        assert res.per_page == 20
        assert res.total == 0

    async def test_single_row_full_payload(self):
        """1건 — 9필드 정합 (buyer_email은 current_user.email로 채워짐)."""
        user = _make_user(user_id=42, email="hyungwoo@example.com")
        charged = datetime(2026, 4, 30, 5, 23, 11, tzinfo=timezone.utc)
        sub_start = datetime(2026, 4, 30, 0, 0, 0, tzinfo=timezone.utc)
        sub_end = datetime(2026, 5, 29, 23, 59, 59, tzinfo=timezone.utc)
        db = _make_db(
            total=1,
            rows=[
                _row(
                    123,
                    charged_at=charged,
                    sub_started_at=sub_start,
                    sub_period_end=sub_end,
                    provider_order_id="sub-42-2026-04-30",
                )
            ],
        )

        res = await get_my_payments(current_user=user, db=db, page=1, per_page=20)

        assert res.total == 1
        assert len(res.items) == 1
        item = res.items[0]
        assert item.payment_id == 123
        assert item.charged_at == charged.isoformat()
        assert item.subscription_period_start == sub_start.isoformat()
        assert item.subscription_period_end == sub_end.isoformat()
        assert item.buyer_email == "hyungwoo@example.com"
        assert item.card_last4 == "1234"
        assert item.card_company == "현대"
        assert item.amount_krw == 9900
        assert item.provider_order_id == "sub-42-2026-04-30"
        assert item.status == "success"

    async def test_pagination_page_2_per_page_10(self):
        """page=2, per_page=10 — 응답 메타에 정확히 반영."""
        user = _make_user()
        rows = [
            _row(i, charged_at=datetime(2026, 4, 1, tzinfo=timezone.utc))
            for i in range(11, 21)
        ]
        db = _make_db(total=47, rows=rows)

        res = await get_my_payments(current_user=user, db=db, page=2, per_page=10)

        assert res.page == 2
        assert res.per_page == 10
        assert res.total == 47
        assert len(res.items) == 10

    async def test_card_join_miss_returns_null(self):
        """LEFT JOIN 매치 실패 시 card_last4/card_company=None."""
        user = _make_user()
        db = _make_db(
            total=1,
            rows=[
                _row(
                    1,
                    charged_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
                    bk_card_last4=None,
                    bk_card_company=None,
                )
            ],
        )

        res = await get_my_payments(current_user=user, db=db, page=1, per_page=20)

        assert res.items[0].card_last4 is None
        assert res.items[0].card_company is None

    async def test_charged_at_null_for_pending(self):
        """status='pending' 시 charged_at NULL → 응답도 None."""
        user = _make_user()
        db = _make_db(
            total=1,
            rows=[_row(1, charged_at=None, status="pending")],
        )

        res = await get_my_payments(current_user=user, db=db, page=1, per_page=20)

        assert res.items[0].charged_at is None
        assert res.items[0].status == "pending"

    async def test_status_five_variants_mapping(self):
        """status 5종 모두 응답에 그대로 전파."""
        user = _make_user()
        statuses = ["pending", "success", "failed", "refunded", "refund_pending"]
        rows = [
            _row(
                i + 1,
                charged_at=(
                    None if s == "pending" else datetime(2026, 4, 1, tzinfo=timezone.utc)
                ),
                status=s,
            )
            for i, s in enumerate(statuses)
        ]
        db = _make_db(total=5, rows=rows)

        res = await get_my_payments(current_user=user, db=db, page=1, per_page=20)

        assert [item.status for item in res.items] == statuses

    async def test_missing_subscription_returns_null_periods(self):
        """subscription_id가 NULL인 경우(LEFT JOIN miss) period 컬럼 None."""
        user = _make_user()
        db = _make_db(
            total=1,
            rows=[
                _row(
                    1,
                    charged_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
                    sub_started_at=None,
                    sub_period_end=None,
                )
            ],
        )

        res = await get_my_payments(current_user=user, db=db, page=1, per_page=20)

        assert res.items[0].subscription_period_start is None
        assert res.items[0].subscription_period_end is None

    async def test_period_uses_payment_snapshot_not_current_subscription(self):
        """과거 결제 row의 회차 표시는 결제 당시 박제된 값이어야 한다.

        회귀 시나리오: subscription.current_period_end가 자동 갱신으로 미래로
        이동한 뒤에도, 1차 결제 row의 응답 subscription_period_end는 1차 회차
        만료일을 그대로 보여야 한다. (라우터 SQL이 Payment.subscription_period_*
        컬럼을 읽도록 변경되었으므로 sub_started_at/sub_period_end 라벨에 들어
        오는 값은 이미 결제별 스냅샷이다.)
        """
        user = _make_user()
        first_charge = datetime(2026, 1, 1, tzinfo=timezone.utc)
        first_period_end = datetime(2026, 1, 31, tzinfo=timezone.utc)
        second_charge = datetime(2026, 1, 31, tzinfo=timezone.utc)
        second_period_end = datetime(2026, 3, 2, tzinfo=timezone.utc)

        rows = [
            _row(
                payment_id=2,
                charged_at=second_charge,
                sub_started_at=second_charge,
                sub_period_end=second_period_end,
            ),
            _row(
                payment_id=1,
                charged_at=first_charge,
                sub_started_at=first_charge,
                sub_period_end=first_period_end,
            ),
        ]
        db = _make_db(total=2, rows=rows)

        res = await get_my_payments(current_user=user, db=db, page=1, per_page=20)

        assert len(res.items) == 2
        # 응답은 charged_at desc — second가 먼저
        assert res.items[0].payment_id == 2
        assert res.items[0].subscription_period_end == second_period_end.isoformat()
        # 1차 결제 row가 최신 만료일로 오염되지 않음
        assert res.items[1].payment_id == 1
        assert res.items[1].subscription_period_end == first_period_end.isoformat()
        assert res.items[1].subscription_period_end != second_period_end.isoformat()

    async def test_logger_emits_pii_safe_event(self, monkeypatch):
        """me.payments.viewed 로그 — user_id/page/per_page/total_returned만 포함."""
        captured: dict = {}

        def _capture(event: str, **kwargs):
            captured["event"] = event
            captured["kwargs"] = kwargs

        from api.src.routers import me as me_module

        monkeypatch.setattr(me_module.logger, "info", _capture)

        user = _make_user(user_id=99, email="secret@example.com")
        db = _make_db(
            total=1,
            rows=[_row(1, charged_at=datetime(2026, 4, 1, tzinfo=timezone.utc))],
        )

        await get_my_payments(current_user=user, db=db, page=3, per_page=50)

        assert captured["event"] == "me.payments.viewed"
        assert captured["kwargs"]["user_id"] == 99
        assert captured["kwargs"]["page"] == 3
        assert captured["kwargs"]["per_page"] == 50
        assert captured["kwargs"]["total_returned"] == 1
        # PII 비포함
        assert "email" not in captured["kwargs"]
        assert "card_last4" not in captured["kwargs"]
        assert "provider_order_id" not in captured["kwargs"]
