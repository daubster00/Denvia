"""NHN Cloud 알림톡·SMS 어댑터 — HOLD-MSG 해제 후 구현 예정 (AR35)."""

from api.src.integrations.messaging.port import AlimtalkResult

_HOLD_MSG = "NHN Cloud 어댑터: HOLD-MSG 해제 후 구현. AR35(공급자 확정) 참조."


class NHNCloudMessagingAdapter:
    """NHN Cloud 알림톡·SMS 어댑터.

    HOLD-MSG 해제 시 구현 방법:
    1. httpx async 클라이언트 + tenacity 지수 백오프(min=2, max=30, 3회)
    2. NHN Cloud Notification API: https://docs.toast.com/ko/Notification/
    3. MESSAGING_PROVIDER=nhn_cloud 로 전환
    """

    async def send_sms_otp(self, phone: str, code: str) -> None:
        raise NotImplementedError(_HOLD_MSG)

    async def send_sms(self, phone: str, body: str) -> None:
        raise NotImplementedError(_HOLD_MSG)

    async def send_alimtalk(
        self,
        recipient_phone: str,
        template_code: str,
        variables: dict[str, str],
    ) -> AlimtalkResult:
        raise NotImplementedError(_HOLD_MSG)
