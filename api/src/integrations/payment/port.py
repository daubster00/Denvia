"""결제 포트 — PGProvider Protocol (AR10). PG_PROVIDER 환경변수로 어댑터 선택."""

from typing import Protocol, TypedDict, runtime_checkable


class BillingKeyResult(TypedDict):
    """빌링키 발급 결과."""

    billing_key: str
    card_last4: str | None
    card_company: str | None


class ChargeResult(TypedDict):
    """결제 시도 결과."""

    success: bool
    provider_order_id: str
    failure_reason: str | None
    raw_response: dict


class RefundResult(TypedDict):
    """환불 결과."""

    success: bool
    raw_response: dict


@runtime_checkable
class PGProvider(Protocol):
    """PG 어댑터 인터페이스 — 공급자에 무관한 추상 포트 (MessagingProvider와 동일 패턴)."""

    async def issue_billing_key(
        self, user_id: int, pg_token: str, customer_key: str
    ) -> BillingKeyResult:
        """PG 토큰으로 빌링키를 발급한다."""
        ...

    async def charge(
        self,
        billing_key_plain: str,
        customer_key: str,
        amount_krw: int,
        order_id: str,
    ) -> ChargeResult:
        """빌링키로 정기결제를 시도한다. billing_key_plain은 복호화된 평문이어야 한다."""
        ...

    async def cancel_billing_key(self, billing_key_plain: str) -> None:
        """빌링키를 삭제/해지한다."""
        ...

    async def refund(
        self, provider_order_id: str, cancel_amount: int, reason: str
    ) -> RefundResult:
        """결제를 환불한다.

        cancel_amount는 부분/전액 모두 지원한다. 청약철회(Story 3.6 v1.1)는
        전액(`payment.amount_krw`), 운영 환불(Story 9.1 v1.1)은 관리자 입력 금액을 전달한다.
        """
        ...
