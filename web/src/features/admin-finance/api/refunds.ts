// Story 9.1 v1.1 — Admin operational refund (partial/full) API client.
// ADR-0001 편차 #5 환불 정책 v1.1.

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type RefundReasonCategory =
  | "customer_complaint"
  | "duplicate_payment"
  | "system_error"
  | "special_mid_cancel"
  | "other";

export const REFUND_REASON_LABELS: Record<RefundReasonCategory, string> = {
  customer_complaint: "고객 불만",
  duplicate_payment: "중복 결제",
  system_error: "시스템 오류",
  special_mid_cancel: "예외적 중도 해지",
  other: "기타",
};

export interface RefundQuoteResponse {
  payment_id: number;
  user_id: number;
  payment_amount: number;
  refunded_total: number;
  refundable_balance: number;
  full_refund_amount: number;
  prorated_amount: number;
  prorated_days_remaining: number;
  prorated_total_days: number;
  is_within_cooling_off: boolean;
  cooling_off_days_since_charge: number;
  cooling_off_qa_count: number;
  next_refund_sequence: number;
  existing_refunds_count: number;
  subscription_period_start: string | null;
  subscription_period_end: string | null;
}

export interface RefundCreateRequest {
  cancel_amount: number;
  reason_category: RefundReasonCategory;
  memo?: string | null;
}

export interface RefundCreateResponse {
  refund_id: number;
  refund_sequence: number;
  cancel_amount: number;
  refunded_at: string;
}

export interface RefundListItem {
  id: number;
  refund_sequence: number;
  cancel_amount: number;
  reason_category: RefundReasonCategory;
  memo: string | null;
  admin_email_masked: string;
  created_at: string;
}

export interface RefundListResponse {
  items: RefundListItem[];
  total: number;
}

/**
 * Backend `HTTPException`을 표준 `{code, message, trace_id, details?}` 형태로 변환.
 * 본 화면은 409/502 코드별로 사용자 안내 문구가 달라지므로 code를 보존해야 한다.
 */
export class RefundApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details?: Record<string, unknown>;

  constructor(
    status: number,
    code: string,
    message: string,
    details?: Record<string, unknown>,
  ) {
    super(message);
    this.name = "RefundApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

async function parseError(res: Response): Promise<RefundApiError> {
  let code = "UNKNOWN_ERROR";
  let message = `요청 실패 (status=${res.status})`;
  let details: Record<string, unknown> | undefined;
  try {
    const body = await res.json();
    if (body && typeof body === "object") {
      code = typeof body.code === "string" ? body.code : code;
      message = typeof body.message === "string" ? body.message : message;
      if (body.details && typeof body.details === "object") {
        details = body.details as Record<string, unknown>;
      }
    }
  } catch {
    // body가 JSON이 아니면 기본 메시지 유지.
  }
  return new RefundApiError(res.status, code, message, details);
}

export async function fetchRefundQuote(
  paymentId: number,
): Promise<RefundQuoteResponse> {
  const res = await fetch(
    `${API_BASE}/api/v1/admin/payments/${paymentId}/refund-quote`,
    { credentials: "include", cache: "no-store" },
  );
  if (!res.ok) throw await parseError(res);
  return res.json();
}

export async function fetchRefundList(
  paymentId: number,
): Promise<RefundListResponse> {
  const res = await fetch(
    `${API_BASE}/api/v1/admin/payments/${paymentId}/refunds`,
    { credentials: "include", cache: "no-store" },
  );
  if (!res.ok) throw await parseError(res);
  return res.json();
}

export async function createRefund(
  paymentId: number,
  payload: RefundCreateRequest,
): Promise<RefundCreateResponse> {
  const res = await fetch(
    `${API_BASE}/api/v1/admin/payments/${paymentId}/refunds`,
    {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!res.ok) throw await parseError(res);
  return res.json();
}
