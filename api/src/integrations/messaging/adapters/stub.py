"""개발·테스트용 Stub 메시징 어댑터 — 실제 발송 없이 structlog만 기록한다."""

import structlog

from api.src.integrations.messaging.port import AlimtalkResult

logger = structlog.get_logger(__name__)

_MASKED = "****"


def _mask_phone(phone: str) -> str:
    """휴대폰 번호 PII 스크러빙 — 마지막 4자리만 노출."""
    if len(phone) >= 4:
        return _MASKED + phone[-4:]
    return _MASKED


class StubMessagingAdapter:
    """Stub 메시징 어댑터 — MESSAGING_PROVIDER=stub (기본값, 개발/CI 환경)."""

    async def send_sms_otp(self, phone: str, code: str) -> None:
        logger.info(
            "messaging.stub.send_sms_otp",
            phone=_mask_phone(phone),
            code_length=len(code),  # OTP 평문 노출 방지
        )

    async def send_sms(self, phone: str, body: str) -> None:
        logger.info(
            "messaging.stub.send_sms",
            phone=_mask_phone(phone),
            body_length=len(body),
        )

    async def send_alimtalk(
        self,
        recipient_phone: str,
        template_code: str,
        variables: dict[str, str],
    ) -> AlimtalkResult:
        logger.info(
            "messaging.stub.send_alimtalk",
            phone=_mask_phone(recipient_phone),
            template_code=template_code,
            variable_keys=list(variables.keys()),
        )
        return AlimtalkResult(
            success=True,
            provider_response_code="STUB_OK",
            message_id=f"stub-{template_code}-ok",
        )
