"""메시징 포트 — 공급자-agnostic MessagingProvider Protocol 및 반환 타입 정의 (AR10)."""

from typing import Protocol, TypedDict, runtime_checkable


class AlimtalkResult(TypedDict):
    """알림톡 발송 결과."""

    success: bool
    provider_response_code: str
    message_id: str | None


@runtime_checkable
class MessagingProvider(Protocol):
    """알림톡·SMS 발송 어댑터 인터페이스 — 공급자에 무관한 추상 포트."""

    async def send_sms_otp(self, phone: str, code: str) -> None:
        """OTP 인증번호를 SMS로 발송한다 (Redis DB 1에 저장은 서비스 레이어 책임)."""
        ...

    async def send_sms(self, phone: str, body: str) -> None:
        """LMS 형식으로 SMS를 발송한다 (알림톡 폴백 경로)."""
        ...

    async def send_alimtalk(
        self,
        recipient_phone: str,
        template_code: str,
        variables: dict[str, str],
    ) -> AlimtalkResult:
        """카카오 알림톡을 발송한다.

        Args:
            recipient_phone: 수신자 휴대폰 번호 (010-XXXX-XXXX 형식)
            template_code: TEMPLATE_CATALOG 키 (예: "billing.first_charge_success")
            variables: 템플릿 변수 딕셔너리 (예: {"amount_krw": "9,900", "next_charge_at": "2026-05-23"})
        """
        ...
