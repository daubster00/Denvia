"""AligoMessagingAdapter 유닛 테스트.

httpx.MockTransport 로 외부 호출을 차단하고, 알리고 API 응답 규약과
form 페이로드를 검증한다.
"""

from __future__ import annotations

import json
from urllib.parse import parse_qsl

import httpx
import pytest

from api.src.integrations.messaging.adapters.aligo import (
    AligoConfigError,
    AligoMessagingAdapter,
)
from api.src.integrations.messaging.port import MessagingProvider


def _make_handler(responses: list[tuple[int, dict]]):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if not responses:
            return httpx.Response(500, json={"result_code": "-999", "message": "no mock"})
        status, payload = responses.pop(0)
        return httpx.Response(status, json=payload)

    handler.calls = calls  # type: ignore[attr-defined]
    return handler


def _form(request: httpx.Request) -> dict[str, str]:
    """application/x-www-form-urlencoded 본문을 dict로 파싱."""
    return dict(parse_qsl(request.content.decode("utf-8"), keep_blank_values=True))


@pytest.fixture(autouse=True)
def _set_aligo_env(monkeypatch):
    from api.src.settings import settings

    monkeypatch.setattr(settings, "aligo_api_key", "TESTKEY")
    monkeypatch.setattr(settings, "aligo_user_id", "denvia")
    monkeypatch.setattr(settings, "aligo_sender", "01012345678")
    monkeypatch.setattr(settings, "aligo_sender_key", "SENDERKEY-001")
    monkeypatch.setattr(settings, "aligo_test_mode", True)
    monkeypatch.setattr(
        settings,
        "alimtalk_template_map_json",
        json.dumps(
            {
                "billing.first_charge_success": "TX_001",
                "notice.generic": "TX_010",
                "admin.anomaly_detected": "TX_049",
            }
        ),
    )


class TestProtocolConformance:
    def test_satisfies_messaging_provider_protocol(self):
        adapter = AligoMessagingAdapter()
        assert isinstance(adapter, MessagingProvider)


class TestSendSms:
    @pytest.mark.asyncio
    async def test_short_body_uses_sms_and_strips_dashes(self):
        handler = _make_handler(
            [(200, {"result_code": "1", "message": "success", "msg_id": 1})]
        )
        adapter = AligoMessagingAdapter(transport=httpx.MockTransport(handler))

        await adapter.send_sms("010-1234-5678", "짧은 본문")

        assert len(handler.calls) == 1
        form = _form(handler.calls[0])
        assert form["msg_type"] == "SMS"
        assert form["receiver"] == "01012345678"
        assert form["msg"] == "짧은 본문"
        assert form["testmode_yn"] == "Y"
        assert form["key"] == "TESTKEY"
        assert form["user_id"] == "denvia"
        assert form["sender"] == "01012345678"

    @pytest.mark.asyncio
    async def test_long_body_uses_lms(self):
        handler = _make_handler([(200, {"result_code": "1", "message": "success"})])
        adapter = AligoMessagingAdapter(transport=httpx.MockTransport(handler))
        long_body = "한글" * 50  # ~300 bytes UTF-8

        await adapter.send_sms("01012345678", long_body)

        assert _form(handler.calls[0])["msg_type"] == "LMS"

    @pytest.mark.asyncio
    async def test_negative_result_code_raises(self):
        handler = _make_handler(
            [(200, {"result_code": "-101", "message": "잔액부족"})]
        )
        adapter = AligoMessagingAdapter(transport=httpx.MockTransport(handler))

        with pytest.raises(RuntimeError, match="잔액부족"):
            await adapter.send_sms("01012345678", "본문")

    @pytest.mark.asyncio
    async def test_http_500_raises(self):
        handler = _make_handler(
            [(500, {"result_code": "1", "message": "success"})]
        )
        adapter = AligoMessagingAdapter(transport=httpx.MockTransport(handler))

        with pytest.raises(RuntimeError):
            await adapter.send_sms("01012345678", "본문")

    @pytest.mark.asyncio
    async def test_test_mode_off_sends_n_flag(self, monkeypatch):
        from api.src.settings import settings

        monkeypatch.setattr(settings, "aligo_test_mode", False)
        handler = _make_handler([(200, {"result_code": "1", "message": "success"})])
        adapter = AligoMessagingAdapter(transport=httpx.MockTransport(handler))

        await adapter.send_sms("01012345678", "본문")

        assert _form(handler.calls[0])["testmode_yn"] == "N"

    @pytest.mark.asyncio
    async def test_missing_keys_raises_config_error(self, monkeypatch):
        from api.src.settings import settings

        monkeypatch.setattr(settings, "aligo_api_key", "")
        adapter = AligoMessagingAdapter()

        with pytest.raises(AligoConfigError):
            await adapter.send_sms("01012345678", "본문")


class TestSendSmsOtp:
    @pytest.mark.asyncio
    async def test_otp_body_includes_code_and_brand(self):
        handler = _make_handler([(200, {"result_code": "1", "message": "success"})])
        adapter = AligoMessagingAdapter(transport=httpx.MockTransport(handler))

        await adapter.send_sms_otp("01012345678", "482917")

        form = _form(handler.calls[0])
        assert "482917" in form["msg"]
        assert "[Denvia]" in form["msg"]
        assert form["msg_type"] == "SMS"


class TestSendAlimtalk:
    @pytest.mark.asyncio
    async def test_success_returns_alimtalk_result(self):
        handler = _make_handler(
            [
                (
                    200,
                    {
                        "code": 0,
                        "message": "success",
                        "info": {
                            "type": "AT",
                            "mid": "BIZ-2026-001",
                            "scnt": "1",
                            "fcnt": "0",
                        },
                    },
                )
            ]
        )
        adapter = AligoMessagingAdapter(transport=httpx.MockTransport(handler))

        # 2026-05-18 — 알리고 등록본 SSOT 정렬: `billing.first_charge_success`는
        # 알리고 v1(변수 2개: amount_krw, next_charge_at)로 복원됨.
        result = await adapter.send_alimtalk(
            recipient_phone="010-1234-5678",
            template_code="billing.first_charge_success",
            variables={"amount_krw": "9,900", "next_charge_at": "2026년 7월 15일"},
        )

        assert result["success"] is True
        assert result["provider_response_code"] == "0"
        assert result["message_id"] == "BIZ-2026-001"

        form = _form(handler.calls[0])
        assert form["tpl_code"] == "TX_001"
        assert form["senderkey"] == "SENDERKEY-001"
        assert form["receiver_1"] == "01012345678"
        # 강조표기 미사용(기본형) 템플릿이므로 subject_1을 보내면 안 된다.
        assert "subject_1" not in form
        assert "Pro 구독이 시작되었습니다" in form["message_1"]
        assert "결제 금액: 9,900원" in form["message_1"]
        assert "다음 결제일: 2026년 7월 15일" in form["message_1"]
        assert "감사합니다" in form["message_1"]
        assert form["testmode_yn"] == "Y"

    @pytest.mark.asyncio
    async def test_negative_code_returns_unsuccess(self):
        handler = _make_handler(
            [(200, {"code": -99, "message": "템플릿 미일치"})]
        )
        adapter = AligoMessagingAdapter(transport=httpx.MockTransport(handler))

        result = await adapter.send_alimtalk(
            recipient_phone="01012345678",
            template_code="billing.first_charge_success",
            variables={"amount_krw": "9,900", "next_charge_at": "2026-06-07"},
        )

        assert result["success"] is False
        assert result["provider_response_code"] == "-99"
        assert result["message_id"] is None

    @pytest.mark.asyncio
    async def test_http_500_returns_unsuccess(self):
        handler = _make_handler(
            [(500, {"code": 0, "message": "success"})]
        )
        adapter = AligoMessagingAdapter(transport=httpx.MockTransport(handler))

        result = await adapter.send_alimtalk(
            recipient_phone="01012345678",
            template_code="billing.first_charge_success",
            variables={"amount_krw": "9,900", "next_charge_at": "2026-06-07"},
        )

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_missing_template_map_raises(self, monkeypatch):
        from api.src.settings import settings

        monkeypatch.setattr(settings, "alimtalk_template_map_json", "{}")
        adapter = AligoMessagingAdapter()

        with pytest.raises(AligoConfigError, match="매핑이 없습니다"):
            await adapter.send_alimtalk(
                recipient_phone="01012345678",
                template_code="billing.first_charge_success",
                variables={"amount_krw": "9,900", "next_charge_at": "2026-06-07"},
            )

    @pytest.mark.asyncio
    async def test_invalid_template_map_json_raises(self, monkeypatch):
        from api.src.settings import settings

        monkeypatch.setattr(settings, "alimtalk_template_map_json", "not-json")
        adapter = AligoMessagingAdapter()

        with pytest.raises(AligoConfigError, match="파싱 실패"):
            await adapter.send_alimtalk(
                recipient_phone="01012345678",
                template_code="billing.first_charge_success",
                variables={"amount_krw": "9,900", "next_charge_at": "2026-06-07"},
            )

    @pytest.mark.asyncio
    async def test_missing_sender_key_raises(self, monkeypatch):
        from api.src.settings import settings

        monkeypatch.setattr(settings, "aligo_sender_key", "")
        adapter = AligoMessagingAdapter()

        with pytest.raises(AligoConfigError, match="ALIGO_SENDER_KEY"):
            await adapter.send_alimtalk(
                recipient_phone="01012345678",
                template_code="billing.first_charge_success",
                variables={"amount_krw": "9,900", "next_charge_at": "2026-06-07"},
            )

    @pytest.mark.asyncio
    async def test_unknown_template_code_raises(self):
        handler = _make_handler([(200, {"code": 0, "message": "success"})])
        adapter = AligoMessagingAdapter(transport=httpx.MockTransport(handler))

        with pytest.raises(ValueError, match="알 수 없는 template_code"):
            await adapter.send_alimtalk(
                recipient_phone="01012345678",
                template_code="bogus.template",
                variables={},
            )

    @pytest.mark.asyncio
    async def test_button_1_attached_when_template_has_buttons(self):
        """등록 버튼이 있는 템플릿(UH_9849)은 발송 form에 button_1이 포함되어야 한다."""
        handler = _make_handler(
            [(200, {"code": 0, "message": "success", "info": {"mid": "BIZ-9849"}})]
        )
        adapter = AligoMessagingAdapter(transport=httpx.MockTransport(handler))

        await adapter.send_alimtalk(
            recipient_phone="01012345678",
            template_code="admin.anomaly_detected",
            variables={
                "anomaly_type": "비밀번호 3회 오류",
                "user_identifier": "test@example.com",
            },
        )

        form = _form(handler.calls[0])
        assert "button_1" in form, "button_1 form 필드가 누락됐다 (카카오 검증 거부 원인)"
        payload = json.loads(form["button_1"])
        assert payload["button"][0]["name"] == "확인하기"
        assert payload["button"][0]["linkType"] == "WL"
        assert payload["button"][0]["linkMo"].startswith("https://denvia.ai.kr/")

    @pytest.mark.asyncio
    async def test_button_1_absent_when_template_has_no_buttons(self):
        """버튼이 없는 템플릿은 button_1 필드를 보내지 않는다 (불필요 노이즈 방지)."""
        handler = _make_handler(
            [(200, {"code": 0, "message": "success"})]
        )
        adapter = AligoMessagingAdapter(transport=httpx.MockTransport(handler))

        await adapter.send_alimtalk(
            recipient_phone="01012345678",
            template_code="billing.first_charge_success",  # buttons=[] 기본값
            variables={"amount_krw": "9,900", "next_charge_at": "2026-06-07"},
        )

        assert "button_1" not in _form(handler.calls[0])
