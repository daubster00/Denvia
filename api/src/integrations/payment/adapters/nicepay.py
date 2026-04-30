"""나이스페이먼츠 PG 어댑터 스텁 — HOLD-PG 해제 후 실 구현 예정."""

from api.src.integrations.payment.port import BillingKeyResult, ChargeResult, RefundResult


class NicepayAdapter:
    """나이스페이먼츠 어댑터. Protocol 구조를 충족하지만 실 API 호출은 별도 스토리에서 완성."""

    async def issue_billing_key(
        self, user_id: int, pg_token: str, customer_key: str
    ) -> BillingKeyResult:
        raise NotImplementedError("나이스페이먼츠 어댑터 미구현")

    async def charge(
        self,
        billing_key_plain: str,
        customer_key: str,
        amount_krw: int,
        order_id: str,
    ) -> ChargeResult:
        raise NotImplementedError("나이스페이먼츠 어댑터 미구현")

    async def cancel_billing_key(self, billing_key_plain: str) -> None:
        raise NotImplementedError("나이스페이먼츠 어댑터 미구현")

    async def refund(
        self, provider_order_id: str, amount_krw: int, reason: str
    ) -> RefundResult:
        raise NotImplementedError("나이스페이먼츠 어댑터 미구현")
