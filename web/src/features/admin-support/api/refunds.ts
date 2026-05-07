/**
 * Admin 수동 환불 검토 API 클라이언트 — Story 9.3.
 *
 *   GET   /api/v1/admin/refunds                       (status/from/to/q + 페이지네이션)
 *   POST  /api/v1/admin/refunds/{queue_id}/approve    (note 필수)
 *   POST  /api/v1/admin/refunds/{queue_id}/deny       (note 필수)
 *
 * 모든 mutate 호출에 X-CSRF-Token 헤더 부착.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type RefundQueueStatus = "pending" | "approved" | "denied";
export type RefundReasonCode =
  | "period_exceeded"
  | "qa_count_exceeded"
  | "both"
  | "no_subscription";

export interface RefundQueueItem {
  queue_id: number;
  payment_id: number;
  user_id: number;
  user_email_masked: string;
  amount_krw: number;
  card_last4: string | null;
  card_company: string | null;
  days_since_charge: number;
  qa_count_during_period: number;
  reason_code: RefundReasonCode | null;
  reason_text: string | null;
  requested_at: string;
  status: RefundQueueStatus;
  reviewer_user_email_masked: string | null;
  reviewer_note: string | null;
  reviewed_at: string | null;
}

export interface RefundQueueListResponse {
  items: RefundQueueItem[];
  page: number;
  per_page: number;
  total: number;
}

export interface FetchRefundsParams {
  status?: RefundQueueStatus;
  from?: string;
  to?: string;
  q?: string;
  page?: number;
  per_page?: number;
}

export interface RefundActionResponse {
  queue_id: number;
  payment_id: number;
  status: RefundQueueStatus;
  amount_krw: number;
  refunded_at: string | null;
}

export class RefundActionError extends Error {
  status: number;
  code: string;
  traceId?: string;
  details?: Record<string, unknown>;

  constructor(
    status: number,
    code: string,
    message: string,
    traceId?: string,
    details?: Record<string, unknown>,
  ) {
    super(message);
    this.name = "RefundActionError";
    this.status = status;
    this.code = code;
    this.traceId = traceId;
    this.details = details;
  }
}

function _readCookie(name: string): string | undefined {
  if (typeof document === "undefined") return undefined;
  const match = document.cookie.match(
    new RegExp("(?:^|; )" + name.replace(/[-]/g, "\\$&") + "=([^;]*)"),
  );
  return match ? decodeURIComponent(match[1]) : undefined;
}

function _withCsrf(headers: Record<string, string>): Record<string, string> {
  const csrf = _readCookie("denvia_admin_csrf");
  if (csrf) headers["X-CSRF-Token"] = csrf;
  return headers;
}

async function _toError(res: Response, fallback: string): Promise<RefundActionError> {
  let code = "UNKNOWN_ERROR";
  let message = fallback;
  let traceId: string | undefined;
  let details: Record<string, unknown> | undefined;
  try {
    const body = (await res.json()) as {
      code?: string;
      message?: string;
      trace_id?: string;
      details?: Record<string, unknown>;
    };
    if (body.code) code = body.code;
    if (body.message) message = body.message;
    if (body.trace_id) traceId = body.trace_id;
    if (body.details) details = body.details;
  } catch {
    /* fallthrough */
  }
  return new RefundActionError(res.status, code, message, traceId, details);
}

export async function fetchRefundQueue(
  params: FetchRefundsParams = {},
): Promise<RefundQueueListResponse> {
  const query = new URLSearchParams();
  if (params.status) query.set("status", params.status);
  if (params.from) query.set("from", params.from);
  if (params.to) query.set("to", params.to);
  if (params.q) query.set("q", params.q);
  if (params.page) query.set("page", String(params.page));
  if (params.per_page) query.set("per_page", String(params.per_page));

  const res = await fetch(
    `${API_BASE}/api/v1/admin/refunds?${query.toString()}`,
    { credentials: "include" },
  );
  if (!res.ok) {
    throw new Error(`admin refunds fetch failed: ${res.status}`);
  }
  return res.json() as Promise<RefundQueueListResponse>;
}

export async function approveRefund(
  queueId: number,
  note: string,
): Promise<RefundActionResponse> {
  const headers = _withCsrf({ "Content-Type": "application/json" });
  const res = await fetch(
    `${API_BASE}/api/v1/admin/refunds/${queueId}/approve`,
    {
      method: "POST",
      credentials: "include",
      headers,
      body: JSON.stringify({ note }),
    },
  );
  if (!res.ok) {
    throw await _toError(res, "환불 승인에 실패했습니다.");
  }
  return res.json() as Promise<RefundActionResponse>;
}

export async function denyRefund(
  queueId: number,
  note: string,
): Promise<RefundActionResponse> {
  const headers = _withCsrf({ "Content-Type": "application/json" });
  const res = await fetch(
    `${API_BASE}/api/v1/admin/refunds/${queueId}/deny`,
    {
      method: "POST",
      credentials: "include",
      headers,
      body: JSON.stringify({ note }),
    },
  );
  if (!res.ok) {
    throw await _toError(res, "환불 거부에 실패했습니다.");
  }
  return res.json() as Promise<RefundActionResponse>;
}
