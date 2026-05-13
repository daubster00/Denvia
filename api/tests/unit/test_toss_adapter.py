"""TossAdapter 단위 테스트 — Story 3.2.

httpx AsyncClient를 mock하여 실 API 미호출.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from api.src.integrations.payment.adapters.toss import TossAdapter, TossApiError


@pytest.fixture
def adapter():
    return TossAdapter(secret_key="test_sk_key")


@pytest.fixture
def _toss_success_resp():
    mock = MagicMock()
    mock.is_success = True
    mock.status_code = 200
    mock.json.return_value = {
        "billingKey": "BILLING_KEY_PLAIN",
        "card": {"cardCompany": "신한", "number": "****1234"},
    }
    return mock


@pytest.fixture
def _toss_fail_resp():
    mock = MagicMock()
    mock.is_success = False
    mock.status_code = 400
    mock.json.return_value = {"code": "INVALID_AUTH_KEY", "message": "유효하지 않은 authKey입니다"}
    return mock


# ── issue_billing_key ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_issue_billing_key_success(adapter, _toss_success_resp):
    """성공 응답 시 BillingKeyResult를 올바르게 파싱한다."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=_toss_success_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await adapter.issue_billing_key(
            user_id=1,
            pg_token="test_auth_key",
            customer_key="denvia_550e8400-e29b-41d4-a716-446655440000",
        )

    assert result["billing_key"] == "BILLING_KEY_PLAIN"
    assert result["card_last4"] == "1234"
    assert result["card_company"] == "신한"


@pytest.mark.asyncio
async def test_issue_billing_key_4xx_raises_toss_api_error(adapter, _toss_fail_resp):
    """4xx 응답 시 TossApiError를 발생시킨다."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=_toss_fail_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(TossApiError) as exc_info:
            await adapter.issue_billing_key(
                user_id=1, pg_token="bad_token", customer_key="denvia_cust_key"
            )

    assert exc_info.value.code == "INVALID_AUTH_KEY"


@pytest.mark.asyncio
async def test_issue_billing_key_no_card_number(adapter):
    """card.number가 없으면 card_last4=None으로 반환한다."""
    mock_resp = MagicMock()
    mock_resp.is_success = True
    mock_resp.json.return_value = {
        "billingKey": "BK_NO_CARD",
        "card": {"cardCompany": "국민"},
    }

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await adapter.issue_billing_key(
            user_id=1, pg_token="token", customer_key="denvia_cust_key"
        )

    assert result["card_last4"] is None
    assert result["card_company"] == "국민"


# ── charge ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_charge_success(adapter):
    """성공 응답 시 ChargeResult(success=True)를 반환한다."""
    mock_resp = MagicMock()
    mock_resp.is_success = True
    mock_resp.json.return_value = {"paymentKey": "PK_123", "orderId": "order_abc"}

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await adapter.charge(
            billing_key_plain="BK_PLAIN",
            customer_key="denvia_cust",
            amount_krw=9900,
            order_id="order_abc",
        )

    assert result["success"] is True
    assert result["provider_order_id"] == "order_abc"
    assert result["failure_reason"] is None


@pytest.mark.asyncio
async def test_charge_failure(adapter):
    """실패 응답 시 ChargeResult(success=False, failure_reason)를 반환한다."""
    mock_resp = MagicMock()
    mock_resp.is_success = False
    mock_resp.json.return_value = {
        "code": "CARD_DECLINED",
        "message": "카드 한도 초과",
    }

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await adapter.charge(
            billing_key_plain="BK_PLAIN",
            customer_key="denvia_cust",
            amount_krw=9900,
            order_id="order_fail",
        )

    assert result["success"] is False
    assert result["failure_reason"] == "카드 한도 초과"
    assert result["raw_response"]["code"] == "CARD_DECLINED"


@pytest.mark.asyncio
async def test_charge_transport_error_retries(adapter):
    """TransportError 발생 시 tenacity가 3회 재시도한 후 최종 실패로 예외를 올린다."""
    import httpx
    from tenacity import RetryError

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=httpx.TransportError("네트워크 오류"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises((httpx.TransportError, RetryError)):
            await adapter.charge(
                billing_key_plain="BK_PLAIN",
                customer_key="denvia_cust",
                amount_krw=9900,
                order_id="order_retry",
            )

    # tenacity 3회 재시도 확인
    assert mock_client.post.call_count == 3


@pytest.mark.asyncio
async def test_billing_key_plain_not_in_log(adapter, _toss_success_resp, capfd):
    """issue_billing_key 실행 시 평문 빌링키가 stdout에 출력되지 않아야 한다."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=_toss_success_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        await adapter.issue_billing_key(
            user_id=1, pg_token="auth_key", customer_key="denvia_cust"
        )

    captured = capfd.readouterr()
    assert "BILLING_KEY_PLAIN" not in captured.out
    assert "BILLING_KEY_PLAIN" not in captured.err


# ── refund (Story 3.6 v1.1 + 9.1 v1.1 공용) ───────────────────────────────────


def _toss_order_resp(payment_key: str = "test_payment_key_xyz") -> MagicMock:
    mock = MagicMock()
    mock.is_success = True
    mock.status_code = 200
    mock.json.return_value = {"paymentKey": payment_key, "status": "DONE"}
    return mock


def _toss_cancel_resp(success: bool = True, code: str | None = None) -> MagicMock:
    mock = MagicMock()
    mock.is_success = success
    mock.status_code = 200 if success else 400
    if success:
        mock.json.return_value = {"status": "CANCELED", "cancels": [{"cancelAmount": 19800}]}
    else:
        mock.json.return_value = {
            "code": code or "INVALID_CANCEL_AMOUNT",
            "message": "잘못된 환불 금액",
        }
    return mock


@pytest.mark.asyncio
async def test_refund_full_amount_sends_cancel_amount_field(adapter):
    """전액 환불: 토스 cancel body의 cancelAmount=전액 + reason 전달."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=_toss_order_resp())
    mock_client.post = AsyncMock(return_value=_toss_cancel_resp(success=True))

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await adapter.refund(
            provider_order_id="denvia-pro-200",
            cancel_amount=19800,
            reason="cooling_off",
        )

    assert result["success"] is True
    # POST body 검증
    posted_kwargs = mock_client.post.await_args.kwargs
    assert posted_kwargs["json"]["cancelAmount"] == 19800
    assert posted_kwargs["json"]["cancelReason"] == "cooling_off"


@pytest.mark.asyncio
async def test_refund_partial_amount_passes_through(adapter):
    """부분 환불: 호출자가 지정한 cancel_amount(부분)가 그대로 토스 body로 전달."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=_toss_order_resp())
    mock_client.post = AsyncMock(return_value=_toss_cancel_resp(success=True))

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await adapter.refund(
            provider_order_id="denvia-pro-200",
            cancel_amount=5000,  # 19800원 결제 중 5000원만 부분 환불
            reason="manual_partial",
        )

    assert result["success"] is True
    posted_kwargs = mock_client.post.await_args.kwargs
    assert posted_kwargs["json"]["cancelAmount"] == 5000
    assert posted_kwargs["json"]["cancelReason"] == "manual_partial"


@pytest.mark.asyncio
async def test_refund_partial_amounts_accumulate_across_two_calls(adapter):
    """동일 paymentKey에 부분 환불 2회 누적 — 어댑터는 각 호출 독립적으로 처리."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=_toss_order_resp())
    mock_client.post = AsyncMock(return_value=_toss_cancel_resp(success=True))

    with patch("httpx.AsyncClient", return_value=mock_client):
        first = await adapter.refund("denvia-pro-200", 3000, "manual_partial")
        second = await adapter.refund("denvia-pro-200", 5000, "manual_partial")

    assert first["success"] is True
    assert second["success"] is True
    # 2회의 POST 모두 cancelAmount 인수 전달
    cancel_amounts = [
        call.kwargs["json"]["cancelAmount"] for call in mock_client.post.await_args_list
    ]
    assert cancel_amounts == [3000, 5000]


@pytest.mark.asyncio
async def test_refund_order_lookup_failure_returns_failure(adapter):
    """orderId → paymentKey 조회 실패 시 RefundResult(success=False)."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    order_fail = MagicMock()
    order_fail.is_success = False
    order_fail.status_code = 404
    order_fail.json.return_value = {"code": "NOT_FOUND", "message": "주문 없음"}
    mock_client.get = AsyncMock(return_value=order_fail)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await adapter.refund("denvia-pro-missing", 19800, "cooling_off")

    assert result["success"] is False
    # post 단계는 건너뛰어야 함
    mock_client.post.assert_not_awaited()


@pytest.mark.asyncio
async def test_refund_cancel_4xx_returns_failure_without_retry(adapter):
    """cancel 단계 4xx → RefundResult(success=False) — 재시도 없음."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=_toss_order_resp())
    mock_client.post = AsyncMock(
        return_value=_toss_cancel_resp(success=False, code="ALREADY_CANCELED_PAYMENT")
    )

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await adapter.refund("denvia-pro-200", 19800, "cooling_off")

    assert result["success"] is False
    assert result["raw_response"]["code"] == "ALREADY_CANCELED_PAYMENT"
    # 4xx는 재시도 없음 — 정확히 1회 호출
    assert mock_client.post.await_count == 1
