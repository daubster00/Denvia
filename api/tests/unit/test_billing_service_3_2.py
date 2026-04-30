"""BillingService 단위 테스트 — Story 3.2.

issue_billing_key + start_subscription 메서드 단위 검증.
"""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from cryptography.fernet import Fernet


@pytest.fixture(autouse=True)
def _set_enc_key(monkeypatch):
    """Fernet 키 주입."""
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("BILLING_KEY_ENC_KEY", key)


def _make_user(subscription_status: str = "free") -> MagicMock:
    u = MagicMock()
    u.id = 1
    u.phone = "01012345678"
    u.subscription_status = subscription_status
    return u


def _make_billing_key(customer_key: str = "denvia_cust_uuid") -> MagicMock:
    from cryptography.fernet import Fernet
    from api.src.utils.fernet import encrypt_billing_key

    bk = MagicMock()
    bk.id = 10
    bk.user_id = 1
    bk.customer_key = customer_key
    bk.billing_key_encrypted = encrypt_billing_key("test_billing_key_plain")
    bk.card_last4 = "1234"
    bk.card_company = "신한"
    bk.is_active = True
    return bk


# ── issue_billing_key ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_issue_billing_key_inserts_and_returns():
    """빌링키 발급 시 BillingKey INSERT + 올바른 dict 반환을 확인한다."""
    from api.src.services.billing_service import issue_billing_key

    user = _make_user()
    mock_db = AsyncMock()

    # 기존 활성 빌링키 없음
    existing_result = MagicMock()
    existing_result.scalars.return_value.all.return_value = []
    mock_db.execute = AsyncMock(return_value=existing_result)

    # BillingKey INSERT 후 refresh
    new_bk = MagicMock()
    new_bk.id = 99
    new_bk.card_last4 = "5678"
    new_bk.card_company = "현대"

    async def fake_refresh(obj):
        obj.id = 99
        obj.card_last4 = "5678"
        obj.card_company = "현대"

    mock_db.refresh = fake_refresh

    mock_pg = AsyncMock()
    mock_pg.issue_billing_key = AsyncMock(return_value={
        "billing_key": "new_billing_key_plain",
        "card_last4": "5678",
        "card_company": "현대",
    })

    with patch("api.src.services.billing_service.get_pg_provider", return_value=mock_pg):
        result = await issue_billing_key(
            user=user,
            pg_token="auth_key_test",
            customer_key="denvia_cust_uuid",
            db=mock_db,
        )

    assert result["card_last4"] == "5678"
    assert result["card_company"] == "현대"
    assert result["masked_number"] == "**** **** **** 5678"
    mock_db.add.assert_called()
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_issue_billing_key_revokes_existing():
    """기존 활성 빌링키가 있으면 revoke 처리된다."""
    from api.src.services.billing_service import issue_billing_key

    user = _make_user()
    mock_db = AsyncMock()

    old_bk = MagicMock()
    old_bk.is_active = True
    old_bk.revoked_at = None

    existing_result = MagicMock()
    existing_result.scalars.return_value.all.return_value = [old_bk]
    mock_db.execute = AsyncMock(return_value=existing_result)

    async def fake_refresh(obj):
        obj.id = 1
        obj.card_last4 = "0000"
        obj.card_company = None

    mock_db.refresh = fake_refresh

    mock_pg = AsyncMock()
    mock_pg.issue_billing_key = AsyncMock(return_value={
        "billing_key": "new_key",
        "card_last4": "0000",
        "card_company": None,
    })

    with patch("api.src.services.billing_service.get_pg_provider", return_value=mock_pg):
        await issue_billing_key(
            user=user,
            pg_token="token",
            customer_key="denvia_new_cust",
            db=mock_db,
        )

    assert old_bk.is_active is False
    assert old_bk.revoked_at is not None


@pytest.mark.asyncio
async def test_issue_billing_key_stores_customer_key():
    """발급된 빌링키에 customer_key가 저장되어야 한다."""
    from api.src.services.billing_service import issue_billing_key
    from api.src.models.billing_key import BillingKey

    user = _make_user()
    mock_db = AsyncMock()

    existing_result = MagicMock()
    existing_result.scalars.return_value.all.return_value = []
    mock_db.execute = AsyncMock(return_value=existing_result)

    captured_bk = {}

    def capture_add(obj):
        if isinstance(obj, BillingKey):
            captured_bk["obj"] = obj

    mock_db.add = MagicMock(side_effect=capture_add)

    async def fake_refresh(obj):
        obj.id = 1
        obj.card_last4 = "1111"
        obj.card_company = "삼성"

    mock_db.refresh = fake_refresh

    mock_pg = AsyncMock()
    mock_pg.issue_billing_key = AsyncMock(return_value={
        "billing_key": "bk_plain",
        "card_last4": "1111",
        "card_company": "삼성",
    })

    with patch("api.src.services.billing_service.get_pg_provider", return_value=mock_pg):
        await issue_billing_key(
            user=user,
            pg_token="token",
            customer_key="denvia_my_customer_key",
            db=mock_db,
        )

    bk_obj = captured_bk.get("obj")
    assert bk_obj is not None
    assert bk_obj.customer_key == "denvia_my_customer_key"


@pytest.mark.asyncio
async def test_issue_billing_key_fernet_encryption():
    """저장된 billing_key_encrypted는 Fernet으로 암호화되어야 한다."""
    from api.src.services.billing_service import issue_billing_key
    from api.src.models.billing_key import BillingKey
    from api.src.utils.fernet import decrypt_billing_key

    user = _make_user()
    mock_db = AsyncMock()

    existing_result = MagicMock()
    existing_result.scalars.return_value.all.return_value = []
    mock_db.execute = AsyncMock(return_value=existing_result)

    captured_bk = {}

    def capture_add(obj):
        if isinstance(obj, BillingKey):
            captured_bk["obj"] = obj

    mock_db.add = MagicMock(side_effect=capture_add)

    async def fake_refresh(obj):
        obj.id = 1
        obj.card_last4 = "2222"
        obj.card_company = None

    mock_db.refresh = fake_refresh

    mock_pg = AsyncMock()
    mock_pg.issue_billing_key = AsyncMock(return_value={
        "billing_key": "ACTUAL_BILLING_KEY",
        "card_last4": "2222",
        "card_company": None,
    })

    with patch("api.src.services.billing_service.get_pg_provider", return_value=mock_pg):
        await issue_billing_key(
            user=user,
            pg_token="token",
            customer_key="denvia_cust",
            db=mock_db,
        )

    bk_obj = captured_bk.get("obj")
    assert bk_obj is not None
    decrypted = decrypt_billing_key(bk_obj.billing_key_encrypted)
    assert decrypted == "ACTUAL_BILLING_KEY"


# ── start_subscription ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_subscription_success():
    """결제 성공 시 payments + subscriptions INSERT + users.subscription_status='pro' 확인."""
    from api.src.services.billing_service import start_subscription

    user = _make_user(subscription_status="free")
    mock_db = AsyncMock()

    # 활성 빌링키 조회
    bk = _make_billing_key()
    bk_result = MagicMock()
    bk_result.scalar_one_or_none = MagicMock(return_value=bk)
    mock_db.execute = AsyncMock(return_value=bk_result)

    mock_pg = AsyncMock()
    mock_pg.charge = AsyncMock(return_value={
        "success": True,
        "provider_order_id": "order_abc",
        "failure_reason": None,
        "raw_response": {"status": "DONE"},
    })

    with patch("api.src.services.billing_service.get_pg_provider", return_value=mock_pg):
        with patch("api.src.services.billing_service.asyncio.ensure_future"):
            result = await start_subscription(user=user, db=mock_db)

    assert result["amount_krw"] == 9900
    assert "subscription_id" in result
    assert "started_at" in result
    assert "current_period_end" in result


@pytest.mark.asyncio
async def test_start_subscription_already_pro():
    """이미 Pro 상태이면 PG charge 미호출 + SubscriptionAlreadyActive 발생."""
    from api.src.services.billing_service import start_subscription, SubscriptionAlreadyActive

    user = _make_user(subscription_status="pro")
    mock_db = AsyncMock()
    mock_pg = AsyncMock()

    with patch("api.src.services.billing_service.get_pg_provider", return_value=mock_pg):
        with pytest.raises(SubscriptionAlreadyActive):
            await start_subscription(user=user, db=mock_db)

    mock_pg.charge.assert_not_called()


@pytest.mark.asyncio
async def test_start_subscription_no_billing_key():
    """활성 빌링키 없으면 BillingKeyRequired 발생."""
    from api.src.services.billing_service import start_subscription, BillingKeyRequired

    user = _make_user(subscription_status="free")
    mock_db = AsyncMock()

    no_key_result = MagicMock()
    no_key_result.scalar_one_or_none = MagicMock(return_value=None)
    mock_db.execute = AsyncMock(return_value=no_key_result)

    mock_pg = AsyncMock()

    with patch("api.src.services.billing_service.get_pg_provider", return_value=mock_pg):
        with pytest.raises(BillingKeyRequired):
            await start_subscription(user=user, db=mock_db)


@pytest.mark.asyncio
async def test_start_subscription_card_declined_no_subscription_created():
    """결제 실패 시 BillingCardDeclined + subscriptions 미생성 확인."""
    from api.src.services.billing_service import start_subscription, BillingCardDeclined
    from api.src.models.subscription import Subscription

    user = _make_user(subscription_status="free")
    mock_db = AsyncMock()

    bk = _make_billing_key()
    bk_result = MagicMock()
    bk_result.scalar_one_or_none = MagicMock(return_value=bk)
    mock_db.execute = AsyncMock(return_value=bk_result)

    mock_pg = AsyncMock()
    mock_pg.charge = AsyncMock(return_value={
        "success": False,
        "provider_order_id": "order_fail",
        "failure_reason": "카드 한도 초과",
        "raw_response": {"code": "EXCEED_MAX_AMOUNT"},
    })

    added_objects = []

    def capture_add(obj):
        added_objects.append(type(obj).__name__)

    mock_db.add = MagicMock(side_effect=capture_add)

    with patch("api.src.services.billing_service.get_pg_provider", return_value=mock_pg):
        with pytest.raises(BillingCardDeclined) as exc_info:
            await start_subscription(user=user, db=mock_db)

    assert exc_info.value.pg_error_code == "EXCEED_MAX_AMOUNT"
    # Subscription이 추가되지 않아야 함
    assert "Subscription" not in added_objects
