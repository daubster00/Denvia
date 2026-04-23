"""MessagingProvider 포트 + StubMessagingAdapter 유닛 테스트."""

import pytest

from api.src.integrations.messaging.port import AlimtalkResult, MessagingProvider
from api.src.integrations.messaging.adapters.stub import StubMessagingAdapter


class TestMessagingProviderProtocol:
    def test_stub_adapter_satisfies_protocol(self):
        """StubMessagingAdapter가 MessagingProvider Protocol을 만족하는지 확인."""
        adapter = StubMessagingAdapter()
        assert isinstance(adapter, MessagingProvider)

    def test_alimtalk_result_structure(self):
        """AlimtalkResult TypedDict 키 구조 검증."""
        result: AlimtalkResult = {
            "success": True,
            "provider_response_code": "OK",
            "message_id": "msg-123",
        }
        assert result["success"] is True
        assert result["provider_response_code"] == "OK"
        assert result["message_id"] == "msg-123"

    def test_alimtalk_result_allows_none_message_id(self):
        """AlimtalkResult.message_id는 None을 허용한다."""
        result: AlimtalkResult = {
            "success": False,
            "provider_response_code": "FAILED",
            "message_id": None,
        }
        assert result["message_id"] is None


class TestStubMessagingAdapter:
    @pytest.mark.asyncio
    async def test_send_sms_otp_succeeds(self):
        """send_sms_otp가 예외 없이 완료된다."""
        adapter = StubMessagingAdapter()
        await adapter.send_sms_otp("01012345678", "123456")

    @pytest.mark.asyncio
    async def test_send_sms_succeeds(self):
        """send_sms가 예외 없이 완료된다."""
        adapter = StubMessagingAdapter()
        await adapter.send_sms("01012345678", "테스트 메시지입니다.")

    @pytest.mark.asyncio
    async def test_send_alimtalk_returns_success_result(self):
        """send_alimtalk가 success=True AlimtalkResult를 반환한다."""
        adapter = StubMessagingAdapter()
        result = await adapter.send_alimtalk(
            recipient_phone="01012345678",
            template_code="billing.first_charge_success",
            variables={"amount_krw": "9,900", "next_charge_at": "2026-05-23"},
        )
        assert result["success"] is True
        assert result["provider_response_code"] == "STUB_OK"
        assert result["message_id"] is not None

    @pytest.mark.asyncio
    async def test_send_alimtalk_message_id_contains_template_code(self):
        """stub message_id에 template_code가 포함된다."""
        adapter = StubMessagingAdapter()
        result = await adapter.send_alimtalk(
            recipient_phone="01012345678",
            template_code="notice.generic",
            variables={"title": "공지", "body": "내용"},
        )
        assert "notice.generic" in result["message_id"]
