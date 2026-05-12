"""토스페이먼츠 PG 어댑터 — Story 3.2 실 API 구현."""

import base64

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from api.src.integrations.payment.port import BillingKeyResult, ChargeResult, RefundResult

logger = structlog.get_logger(__name__)

_TOSS_BASE = "https://api.tosspayments.com"


def _get_auth_header(secret_key: str) -> str:
    """Basic 인증 헤더 생성 — base64(secretKey:) — 콜론 필수, 뒤 비밀번호 없음."""
    encoded = base64.b64encode(f"{secret_key}:".encode()).decode()
    return f"Basic {encoded}"


class TossAdapter:
    """토스페이먼츠 어댑터 — 정기결제 API v1."""

    def __init__(self, secret_key: str) -> None:
        self._auth = _get_auth_header(secret_key)

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    async def issue_billing_key(
        self, user_id: int, pg_token: str, customer_key: str
    ) -> BillingKeyResult:
        """authKey로 빌링키를 발급한다."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{_TOSS_BASE}/v1/billing/authorizations/issue",
                headers={"Authorization": self._auth, "Content-Type": "application/json"},
                json={"authKey": pg_token, "customerKey": customer_key},
                timeout=10.0,
            )
        if not resp.is_success:
            data = resp.json()
            logger.warning(
                "toss.issue_billing_key.failed",
                status=resp.status_code,
                code=data.get("code"),
            )
            raise TossApiError(data.get("code", "UNKNOWN"), data.get("message", ""))
        data = resp.json()
        # 카드 번호 전체는 DB·로그 금지 — 뒷 4자리만 추출
        card = data.get("card", {})
        number = card.get("number") or ""
        return BillingKeyResult(
            billing_key=data["billingKey"],
            card_last4=number[-4:] if number else None,
            card_company=card.get("cardCompany") or None,
        )

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    async def charge(
        self,
        billing_key_plain: str,
        customer_key: str,
        amount_krw: int,
        order_id: str,
    ) -> ChargeResult:
        """빌링키로 정기결제를 시도한다."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{_TOSS_BASE}/v1/billing/{billing_key_plain}",
                headers={"Authorization": self._auth, "Content-Type": "application/json"},
                json={
                    "customerKey": customer_key,
                    "amount": amount_krw,
                    "orderId": order_id,
                    "orderName": "Denvia Pro 월 구독",
                },
                timeout=70.0,
            )
        raw = resp.json()
        if resp.is_success:
            logger.info("toss.charge.success", order_id=order_id, amount=amount_krw)
            return ChargeResult(
                success=True,
                provider_order_id=order_id,
                failure_reason=None,
                raw_response=raw,
            )
        logger.warning("toss.charge.failed", order_id=order_id, code=raw.get("code"))
        return ChargeResult(
            success=False,
            provider_order_id=order_id,
            failure_reason=raw.get("message"),
            raw_response=raw,
        )

    async def cancel_billing_key(self, billing_key_plain: str) -> None:
        """빌링키를 삭제한다 (Story 3.5용)."""
        async with httpx.AsyncClient() as client:
            await client.delete(
                f"{_TOSS_BASE}/v1/billing/{billing_key_plain}",
                headers={"Authorization": self._auth},
                timeout=10.0,
            )

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    async def refund(
        self, provider_order_id: str, cancel_amount: int, reason: str
    ) -> RefundResult:
        """결제를 환불한다 (Story 3.6 v1.1 + Story 9.1 v1.1 공용).

        토스페이먼츠 결제 취소 API는 paymentKey를 요구한다. 본 프로젝트는
        provider_order_id(=orderId)만 보관하므로 어댑터 내부에서 2-step 호출:
            1) GET /v1/payments/orders/{orderId} → paymentKey 추출
            2) POST /v1/payments/{paymentKey}/cancel → 환불 실행 (`cancelAmount` 지정)

        cancel_amount는 호출자가 전액/부분을 결정하여 전달한다. 어댑터는
        분기 코드를 갖지 않고 토스 body의 `cancelAmount` 필드로 그대로 전달한다.
        토스는 동일 paymentKey에 대해 여러 차례 부분 환불을 누적 처리한다.

        transport 장애는 tenacity 3회 재시도. 4xx 응답은 재시도 없이
        RefundResult(success=False)로 반환(서비스가 502 + 원복 처리).
        """
        async with httpx.AsyncClient() as client:
            # Step 1: orderId → paymentKey 조회
            order_resp = await client.get(
                f"{_TOSS_BASE}/v1/payments/orders/{provider_order_id}",
                headers={"Authorization": self._auth},
                timeout=10.0,
            )
            if not order_resp.is_success:
                data = order_resp.json()
                logger.warning(
                    "toss.refund.order_lookup_failed",
                    order_id=provider_order_id,
                    code=data.get("code"),
                )
                return RefundResult(success=False, raw_response=data)

            order_data = order_resp.json()
            payment_key = order_data.get("paymentKey")
            if not payment_key:
                logger.warning(
                    "toss.refund.payment_key_missing",
                    order_id=provider_order_id,
                )
                return RefundResult(
                    success=False,
                    raw_response={"code": "PAYMENT_KEY_NOT_FOUND", "raw": order_data},
                )

            # Step 2: cancel 호출 (cancel_amount = 전액 또는 부분)
            cancel_resp = await client.post(
                f"{_TOSS_BASE}/v1/payments/{payment_key}/cancel",
                headers={
                    "Authorization": self._auth,
                    "Content-Type": "application/json",
                },
                json={"cancelReason": reason, "cancelAmount": cancel_amount},
                timeout=30.0,
            )
            raw = cancel_resp.json()
            if cancel_resp.is_success:
                logger.info(
                    "toss.refund.success",
                    order_id=provider_order_id,
                    cancel_amount=cancel_amount,
                )
                return RefundResult(success=True, raw_response=raw)
            logger.warning(
                "toss.refund.failed",
                order_id=provider_order_id,
                code=raw.get("code"),
            )
            return RefundResult(success=False, raw_response=raw)


class TossApiError(Exception):
    """토스페이먼츠 API 에러 (4xx 응답)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
