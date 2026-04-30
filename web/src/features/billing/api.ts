/** 빌링 API 클라이언트 — Story 3.1/3.2/3.5. */

import { apiFetch } from "@/lib/api-client";
import type {
  BillingPlansResponse,
  CancelSubscriptionResponse,
  CurrentSubscription,
  IssueBillingKeyResponse,
  PaymentHistoryResponse,
  RefundResult,
  ResumeSubscriptionResponse,
  SubscriptionResponse,
} from "./types";

/** GET /api/v1/billing/plans — 구독 플랜 목록 조회. 인증 필수. */
export async function fetchBillingPlans(): Promise<BillingPlansResponse> {
  return apiFetch<BillingPlansResponse>("/api/v1/billing/plans");
}

/** POST /api/v1/billing/billing-key — 토스 authKey로 빌링키 발급. */
export async function issueBillingKey(
  pgToken: string,
  customerKey: string
): Promise<IssueBillingKeyResponse> {
  return apiFetch<IssueBillingKeyResponse>("/api/v1/billing/billing-key", {
    method: "POST",
    body: JSON.stringify({ pg_token: pgToken, customer_key: customerKey }),
  });
}

/** POST /api/v1/billing/subscriptions — 활성 빌링키로 최초 결제 + Pro 구독 시작. */
export async function startSubscription(): Promise<SubscriptionResponse> {
  return apiFetch<SubscriptionResponse>("/api/v1/billing/subscriptions", {
    method: "POST",
    body: JSON.stringify({}),
  });
}

// ── Story 3.5 ────────────────────────────────────────────────────────────────

/** POST /api/v1/billing/subscriptions/cancel — 구독 해지(다음 결제일부터 적용). */
export async function cancelSubscription(
  reason: string
): Promise<CancelSubscriptionResponse> {
  return apiFetch<CancelSubscriptionResponse>(
    "/api/v1/billing/subscriptions/cancel",
    {
      method: "POST",
      body: JSON.stringify({ reason }),
    }
  );
}

/** POST /api/v1/billing/subscriptions/resume — 해지 철회. */
export async function resumeSubscription(): Promise<ResumeSubscriptionResponse> {
  return apiFetch<ResumeSubscriptionResponse>(
    "/api/v1/billing/subscriptions/resume",
    {
      method: "POST",
      body: JSON.stringify({}),
    }
  );
}

/** GET /api/v1/billing/subscriptions/current — 현재 구독 상태 조회. */
export async function fetchCurrentSubscription(): Promise<CurrentSubscription> {
  return apiFetch<CurrentSubscription>("/api/v1/billing/subscriptions/current");
}

// ── Story 3.6 ────────────────────────────────────────────────────────────────

/** POST /api/v1/billing/payments/{paymentId}/refund — 환불 요청(자동/수동 분기). */
export async function requestRefund(
  paymentId: number,
  reason?: string
): Promise<RefundResult> {
  return apiFetch<RefundResult>(
    `/api/v1/billing/payments/${paymentId}/refund`,
    {
      method: "POST",
      body: JSON.stringify({ reason: reason ?? null }),
    }
  );
}

// ── Story 4.4 ────────────────────────────────────────────────────────────────

/** GET /api/v1/me/payments — 본인 결제 내역 페이지네이션 (Story 4.4 / FR27). */
export async function fetchPaymentHistory(
  page: number,
  perPage: number
): Promise<PaymentHistoryResponse> {
  return apiFetch<PaymentHistoryResponse>(
    `/api/v1/me/payments?page=${page}&per_page=${perPage}`
  );
}
