/** 빌링 관련 타입 정의 — Story 3.1/3.2. */

export interface PlanItem {
  tier: "free" | "pro";
  name: string;
  price_krw: number;
  period: string | null;
  features: string[];
  cta_label: string;
  is_recommended: boolean;
}

export interface BillingPlansResponse {
  plans: PlanItem[];
}

// ── Story 3.2 ────────────────────────────────────────────────────────────────

export interface IssueBillingKeyRequest {
  pg_token: string;
  customer_key: string;
}

export interface IssueBillingKeyResponse {
  billing_key_id: number;
  card_last4: string | null;
  card_company: string | null;
  masked_number: string | null;
}

export interface SubscriptionResponse {
  subscription_id: number;
  started_at: string;
  current_period_end: string;
  amount_krw: number;
}

// ── Story 3.5 ────────────────────────────────────────────────────────────────

export interface CancelSubscriptionRequest {
  reason: string;
}

export interface CancelSubscriptionResponse {
  status: "cancel_pending";
  effective_at: string;
}

export interface ResumeSubscriptionResponse {
  status: "active";
  next_charge_at: string | null;
}

export interface CurrentSubscription {
  status: "active" | "cancel_pending" | "none";
  started_at: string | null;
  current_period_end: string | null;
  next_charge_at: string | null;
  canceled_at: string | null;
  cancel_reason: string | null;
}

// ── Story 4.4 ────────────────────────────────────────────────────────────────

export type PaymentStatus =
  | "pending"
  | "success"
  | "failed"
  | "refunded"
  | "refund_pending";

export interface PaymentHistoryItem {
  payment_id: number;
  charged_at: string | null;
  subscription_period_start: string | null;
  subscription_period_end: string | null;
  buyer_email: string;
  card_last4: string | null;
  card_company: string | null;
  amount_krw: number;
  provider_order_id: string;
  status: PaymentStatus;
}

export interface PaymentHistoryResponse {
  items: PaymentHistoryItem[];
  page: number;
  per_page: number;
  total: number;
}
