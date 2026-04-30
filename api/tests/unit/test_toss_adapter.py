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
