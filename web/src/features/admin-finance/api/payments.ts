// Story 9.1 — Admin payment events API client.

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type PaymentEventType =
  | "charge_requested"
  | "charge_success"
  | "charge_failed"
  | "retry_scheduled"
  | "refund_requested"
  | "refund_success"
  | "refund_denied";

export type PaymentStatus =
  | "pending"
  | "success"
  | "failed"
  | "refunded"
  | "refund_pending";

export interface PaymentEventItem {
  event_id: number;
  payment_id: number;
  event_type: PaymentEventType;
  charged_at: string | null;
  amount_krw: number;
  user_id: number;
  user_email_masked: string;
  card_last4: string | null;
  card_company: string | null;
  provider_order_id: string;
  provider_error_code: string | null;
  provider_error_message: string | null;
  status: PaymentStatus;
}

export interface ErrorCodeSummary {
  event_count: number;
  affected_user_count: number;
}

export interface PaymentEventListResponse {
  items: PaymentEventItem[];
  page: number;
  per_page: number;
  total: number;
  error_code_summary: ErrorCodeSummary | null;
}

export interface PaymentEventDetail extends PaymentEventItem {
  raw_response_json: Record<string, unknown> | null;
}

export interface FetchPaymentEventsParams {
  from?: string;
  to?: string;
  status_in?: string;
  user_id?: number;
  provider_error_code?: string;
  page?: number;
  per_page?: number;
}

function buildQuery(p: FetchPaymentEventsParams): URLSearchParams {
  const q = new URLSearchParams();
  if (p.from) q.set("from", p.from);
  if (p.to) q.set("to", p.to);
  if (p.status_in) q.set("status_in", p.status_in);
  if (p.user_id !== undefined && p.user_id !== null) {
    q.set("user_id", String(p.user_id));
  }
  if (p.provider_error_code) q.set("provider_error_code", p.provider_error_code);
  if (p.page) q.set("page", String(p.page));
  if (p.per_page) q.set("per_page", String(p.per_page));
  return q;
}

export async function fetchPaymentEvents(
  p: FetchPaymentEventsParams = {},
): Promise<PaymentEventListResponse> {
  const q = buildQuery(p);
  const res = await fetch(
    `${API_BASE}/api/v1/admin/payments/events?${q.toString()}`,
    { credentials: "include" },
  );
  if (!res.ok) {
    throw new Error(`payment-events fetch failed: ${res.status}`);
  }
  return res.json();
}

export async function fetchPaymentEventDetail(
  eventId: number,
): Promise<PaymentEventDetail> {
  const res = await fetch(
    `${API_BASE}/api/v1/admin/payments/events/${eventId}`,
    { credentials: "include" },
  );
  if (!res.ok) {
    if (res.status === 404) throw new Error("EVENT_NOT_FOUND");
    throw new Error(`payment-event detail fetch failed: ${res.status}`);
  }
  return res.json();
}

export function buildPaymentEventsExportUrl(
  p: FetchPaymentEventsParams,
): string {
  const q = buildQuery({ ...p, page: undefined, per_page: undefined });
  return `${API_BASE}/api/v1/admin/payments/events/export?${q.toString()}`;
}
