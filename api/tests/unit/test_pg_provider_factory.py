"""PG 어댑터 팩토리 단위 테스트 — Story 3.1/3.2.

PG_PROVIDER 환경변수에 따른 어댑터 분기 + Protocol 만족 검증.
Story 3.2에서 TossAdapter가 실 구현으로 교체됨에 따라 관련 테스트 업데이트.
"""

import pytest
from unittest.mock import patch

from api.src.integrations.payment.port import PGProvider


def test_default_returns_toss_adapter():
    """PG_PROVIDER 기본값이 toss이면 TossAdapter가 반환된다."""
    from api.src.integrations.payment import get_pg_provider
    from api.src.integrations.payment.adapters.toss import TossAdapter

    provider = get_pg_provider()
    assert isinstance(provider, TossAdapter)


def test_pg_provider_toss_returns_toss_adapter():
    """settings.pg_provider='toss' 시 TossAdapter가 반환된다."""
    from api.src.integrations.payment import get_pg_provider
    from api.src.integrations.payment.adapters.toss import TossAdapter

    with patch("api.src.settings.settings") as mock_settings:
        mock_settings.pg_provider = "toss"
        mock_settings.toss_secret_key = "test_sk"
        provider = get_pg_provider()
    assert isinstance(provider, TossAdapter)


def test_pg_provider_nicepay_returns_nicepay_adapter():
    """settings.pg_provider='nicepay' 시 NicepayAdapter가 반환된다."""
    from api.src.integrations.payment import get_pg_provider
    from api.src.integrations.payment.adapters.nicepay import NicepayAdapter

    with patch("api.src.settings.settings") as mock_settings:
        mock_settings.pg_provider = "nicepay"
        provider = get_pg_provider()
    assert isinstance(provider, NicepayAdapter)


def test_toss_adapter_satisfies_pg_provider_protocol():
    """TossAdapter가 PGProvider Protocol을 만족해야 한다."""
    from api.src.integrations.payment.adapters.toss import TossAdapter

    adapter = TossAdapter(secret_key="test_sk_key")
    assert isinstance(adapter, PGProvider)


def test_nicepay_adapter_satisfies_pg_provider_protocol():
    """NicepayAdapter가 PGProvider Protocol을 만족해야 한다."""
    from api.src.integrations.payment.adapters.nicepay import NicepayAdapter

    adapter = NicepayAdapter()
    assert isinstance(adapter, PGProvider)


@pytest.mark.asyncio
async def test_toss_adapter_issue_billing_key_requires_customer_key():
    """Story 3.2: TossAdapter.issue_billing_key는 customer_key를 인수로 받는다."""
    import inspect
    from api.src.integrations.payment.adapters.toss import TossAdapter

    sig = inspect.signature(TossAdapter.issue_billing_key)
    assert "customer_key" in sig.parameters


@pytest.mark.asyncio
async def test_toss_adapter_charge_requires_customer_key():
    """Story 3.2: TossAdapter.charge는 customer_key를 인수로 받는다."""
    import inspect
    from api.src.integrations.payment.adapters.toss import TossAdapter

    sig = inspect.signature(TossAdapter.charge)
    assert "customer_key" in sig.parameters
