/**
 * Admin 고객문의 관리 API 클라이언트 — Story 4.5 + Story 9.3 확장.
 *
 * 백엔드:
 *   GET   /api/v1/admin/support/inquiries              (status_in/q/from/to 추가)
 *   GET   /api/v1/admin/support/inquiries/{id}         (recent_qa + replies 추가)
 *   PATCH /api/v1/admin/support/inquiries/{id}         (force 추가)
 *   POST  /api/v1/admin/support/inquiries/{id}/reply   (Tiptap reply_html, 신규)
 *
 * 모든 mutate 호출에 X-CSRF-Token 헤더 부착.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type InquiryStatus = "open" | "in_progress" | "resolved";
export type InquiryType =
  | "billing"
  | "account"
  | "usage"
  | "bug"
  | "suggestion"
  | "other";
export type UserSegment = "doctor" | "hygienist" | "student_other";
export type UserSubscriptionStatus = "free" | "pro" | "blocked";

export interface InquiryAttachmentItem {
  id: number;
  file_url: string;
  file_name: string;
  mime_type: string;
  size_bytes: number;
}

export interface InquiryListItem {
  id: number;
  user_id: number;
  user_email: string;
  subject: string;
  body_preview: string;
  inquiry_type: InquiryType;
  segment: UserSegment | null;
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

export interface RecentQAExcerpt {
  qa_log_id: number;
  question_excerpt: string;
  created_at: string;
}

export interface InquiryReplyItem {
  reply_id: number;
  admin_id: number;
  admin_email_masked: string;
  reply_html_safe: string;
  created_at: string;
}

export interface InquiryDetailResponse {
  id: number;
  user_id: number;
  user_email: string;
  user_phone: string | null;
  subject: string;
  body: string;
  inquiry_type: InquiryType;
  status: InquiryStatus;
  created_at: string;
  resolved_at: string | null;
  user_segment: UserSegment | null;
  user_subscription_status: UserSubscriptionStatus;
  user_created_at: string;
  recent_qa: RecentQAExcerpt[];
  replies: InquiryReplyItem[];
  attachments: InquiryAttachmentItem[];
}

export interface FetchInquiriesParams {
  status?: InquiryStatus;
  status_in?: InquiryStatus[];
  q?: string;
  from?: string;
  to?: string;
  page?: number;
  per_page?: number;
}

export interface InquiryUpdatePayload {
  status?: InquiryStatus;
  reply_message?: string;
  force?: boolean;
}

export interface InquiryReplyPayload {
  reply_html: string;
  new_status?: "in_progress" | "resolved" | null;
}

export interface InquiryReplyEditPayload {
  reply_html: string;
}

export interface InquiryReplyResponse {
  inquiry: InquiryDetailResponse;
}

export interface SupportCountsResponse {
  open_inquiries: number;
}

export class InquiryUpdateError extends Error {
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
    this.name = "InquiryUpdateError";
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

async function _toError(res: Response, fallback: string): Promise<InquiryUpdateError> {
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
  return new InquiryUpdateError(res.status, code, message, traceId, details);
}

export async function fetchInquiries(
  params: FetchInquiriesParams = {},
): Promise<InquiryListResponse> {
  const query = new URLSearchParams();
  if (params.status) query.set("status", params.status);
  if (params.status_in && params.status_in.length > 0) {
    query.set("status_in", params.status_in.join(","));
  }
  if (params.q) query.set("q", params.q);
  if (params.from) query.set("from", params.from);
  if (params.to) query.set("to", params.to);
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

export async function fetchSupportCounts(): Promise<SupportCountsResponse> {
  const res = await fetch(`${API_BASE}/api/v1/admin/support/counts`, {
    credentials: "include",
  });
  if (!res.ok) {
    throw new Error(`admin support counts fetch failed: ${res.status}`);
  }
  return res.json() as Promise<SupportCountsResponse>;
}

export async function updateInquiry(
  inquiryId: number,
  payload: InquiryUpdatePayload,
): Promise<InquiryDetailResponse> {
  const headers = _withCsrf({ "Content-Type": "application/json" });
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
    throw await _toError(res, "문의 처리에 실패했습니다.");
  }
  return res.json() as Promise<InquiryDetailResponse>;
}

export async function postInquiryReply(
  inquiryId: number,
  payload: InquiryReplyPayload,
): Promise<InquiryReplyResponse> {
  const headers = _withCsrf({ "Content-Type": "application/json" });
  const res = await fetch(
    `${API_BASE}/api/v1/admin/support/inquiries/${inquiryId}/reply`,
    {
      method: "POST",
      credentials: "include",
      headers,
      body: JSON.stringify(payload),
    },
  );
  if (!res.ok) {
    throw await _toError(res, "답변 등록에 실패했습니다.");
  }
  return res.json() as Promise<InquiryReplyResponse>;
}

export async function editInquiryReply(
  inquiryId: number,
  replyId: number,
  payload: InquiryReplyEditPayload,
): Promise<InquiryDetailResponse> {
  const headers = _withCsrf({ "Content-Type": "application/json" });
  const res = await fetch(
    `${API_BASE}/api/v1/admin/support/inquiries/${inquiryId}/replies/${replyId}`,
    {
      method: "PATCH",
      credentials: "include",
      headers,
      body: JSON.stringify(payload),
    },
  );
  if (!res.ok) {
    throw await _toError(res, "답변 수정에 실패했습니다.");
  }
  return res.json() as Promise<InquiryDetailResponse>;
}

export async function deleteInquiryReply(
  inquiryId: number,
  replyId: number,
): Promise<InquiryDetailResponse> {
  const headers = _withCsrf({});
  const res = await fetch(
    `${API_BASE}/api/v1/admin/support/inquiries/${inquiryId}/replies/${replyId}`,
    {
      method: "DELETE",
      credentials: "include",
      headers,
    },
  );
  if (!res.ok) {
    throw await _toError(res, "답변 삭제에 실패했습니다.");
  }
  return res.json() as Promise<InquiryDetailResponse>;
}

export interface ReplyImageUploadResponse {
  image_url: string;
  size_bytes: number;
  mime_type: string;
}

/**
 * CS 답변 본문 에디터에서 로컬 컴퓨터 이미지를 골라 서버에 업로드한다.
 * 응답의 image_url 을 Tiptap 본문 <img src="..."> 에 삽입한다.
 */
export async function uploadReplyImage(
  file: File,
): Promise<ReplyImageUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const headers = _withCsrf({});
  const res = await fetch(
    `${API_BASE}/api/v1/admin/support/reply-image-upload`,
    {
      method: "POST",
      credentials: "include",
      headers,
      body: formData,
    },
  );
  if (!res.ok) {
    throw await _toError(res, "이미지 업로드에 실패했습니다.");
  }
  return res.json() as Promise<ReplyImageUploadResponse>;
}
