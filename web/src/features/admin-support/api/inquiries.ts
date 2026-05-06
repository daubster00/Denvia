/**
 * Admin 고객문의 관리 API 클라이언트.
 *
 * 백엔드:
 *   GET   /api/v1/admin/support/inquiries
 *   GET   /api/v1/admin/support/inquiries/{id}
 *   PATCH /api/v1/admin/support/inquiries/{id}
 *
 * 패턴은 features/admin-users/api/users.ts 와 동일하게 NEXT_PUBLIC_API_URL,
 * credentials:'include', CSRF 헤더(PATCH 시) 사용.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type InquiryStatus = "open" | "in_progress" | "resolved";

export interface InquiryListItem {
  id: number;
  user_id: number;
  user_email: string;
  subject: string;
  status: InquiryStatus;
  created_at: string;
  resolved_at: string | null;
}

export interface InquiryListResponse {
  items: InquiryListItem[];
  page: number;
  per_page: number;
  total: number;
}

export interface InquiryDetailResponse {
  id: number;
  user_id: number;
  user_email: string;
  user_phone: string | null;
  subject: string;
  body: string;
  status: InquiryStatus;
  created_at: string;
  resolved_at: string | null;
}

export interface FetchInquiriesParams {
  status?: InquiryStatus;
  page?: number;
  per_page?: number;
}

export interface InquiryUpdatePayload {
  status?: InquiryStatus;
  reply_message?: string;
}

export class InquiryUpdateError extends Error {
  status: number;
  code: string;
  traceId?: string;

  constructor(status: number, code: string, message: string, traceId?: string) {
    super(message);
    this.name = "InquiryUpdateError";
    this.status = status;
    this.code = code;
    this.traceId = traceId;
  }
}

function _readCookie(name: string): string | undefined {
  if (typeof document === "undefined") return undefined;
  const match = document.cookie.match(
    new RegExp("(?:^|; )" + name.replace(/[-]/g, "\\$&") + "=([^;]*)"),
  );
  return match ? decodeURIComponent(match[1]) : undefined;
}

export async function fetchInquiries(
  params: FetchInquiriesParams = {},
): Promise<InquiryListResponse> {
  const query = new URLSearchParams();
  if (params.status) query.set("status", params.status);
  if (params.page) query.set("page", String(params.page));
  if (params.per_page) query.set("per_page", String(params.per_page));

  const res = await fetch(
    `${API_BASE}/api/v1/admin/support/inquiries?${query.toString()}`,
    { credentials: "include" },
  );
  if (!res.ok) {
    throw new Error(`admin support inquiries fetch failed: ${res.status}`);
  }
  return res.json() as Promise<InquiryListResponse>;
}

export async function fetchInquiryDetail(
  inquiryId: number,
): Promise<InquiryDetailResponse> {
  const res = await fetch(
    `${API_BASE}/api/v1/admin/support/inquiries/${inquiryId}`,
    { credentials: "include" },
  );
  if (!res.ok) {
    throw new Error(`admin support inquiry detail fetch failed: ${res.status}`);
  }
  return res.json() as Promise<InquiryDetailResponse>;
}

export async function updateInquiry(
  inquiryId: number,
  payload: InquiryUpdatePayload,
): Promise<InquiryDetailResponse> {
  const csrf = _readCookie("denvia_admin_csrf");
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (csrf) headers["X-CSRF-Token"] = csrf;

  const res = await fetch(
    `${API_BASE}/api/v1/admin/support/inquiries/${inquiryId}`,
    {
      method: "PATCH",
      credentials: "include",
      headers,
      body: JSON.stringify(payload),
    },
  );
  if (!res.ok) {
    let code = "UNKNOWN_ERROR";
    let message = "문의 처리에 실패했습니다.";
    let traceId: string | undefined;
    try {
      const body = (await res.json()) as {
        code?: string;
        message?: string;
        trace_id?: string;
      };
      if (body.code) code = body.code;
      if (body.message) message = body.message;
      if (body.trace_id) traceId = body.trace_id;
    } catch {
      /* fallthrough */
    }
    throw new InquiryUpdateError(res.status, code, message, traceId);
  }
  return res.json() as Promise<InquiryDetailResponse>;
}
