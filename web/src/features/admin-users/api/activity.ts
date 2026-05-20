/**
 * Admin 사용자 활동 로그 API 클라이언트.
 *
 * 백엔드 GET /api/v1/admin/users/{user_id}/{qa-logs|inquiries|anomaly-events} fetcher.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface UserQALogItem {
  qa_log_id: number;
  question_excerpt: string;
  answer_excerpt: string;
  input_tokens: number | null;
  output_tokens: number | null;
  cost_usd: string | null;
  latency_ms: number | null;
  status: string | null;
  rule_matched: boolean;
  created_at: string;
}

export interface RetrievedDocItem {
  page_content: string;
  metadata: Record<string, unknown>;
}

export interface UserQALogDetail {
  qa_log_id: number;
  question_text: string;
  normalized_query: string | null;
  retrieved_docs: RetrievedDocItem[];
  answer_text: string | null;
  rule_matched: boolean;
  status: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  cost_usd: string | null;
  latency_ms: number | null;
  created_at: string;
}

export interface UserInquiryItem {
  id: number;
  subject: string;
  body_preview: string;
  status: string;
  created_at: string;
  resolved_at: string | null;
}

export interface UserAnomalyEventItem {
  id: number;
  type: string;
  ip: string | null;
  ua: string | null;
  status: string;
  created_at: string;
}

export interface PagedResponse<T> {
  items: T[];
  page: number;
  per_page: number;
  total: number;
}

export interface ActivityFetchParams {
  userId: number;
  page?: number;
  perPage?: number;
}

function buildQuery(params: ActivityFetchParams): string {
  const q = new URLSearchParams();
  if (params.page) q.set("page", String(params.page));
  if (params.perPage) q.set("per_page", String(params.perPage));
  return q.toString();
}

async function fetchJSON<T>(url: string): Promise<T> {
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) {
    throw new Error(`admin user activity fetch failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export async function fetchUserQALogs(
  params: ActivityFetchParams,
): Promise<PagedResponse<UserQALogItem>> {
  const qs = buildQuery(params);
  return fetchJSON(
    `${API_BASE}/api/v1/admin/users/${params.userId}/qa-logs?${qs}`,
  );
}

export async function fetchUserQALogDetail(
  params: { userId: number; qaLogId: number },
): Promise<UserQALogDetail> {
  return fetchJSON(
    `${API_BASE}/api/v1/admin/users/${params.userId}/qa-logs/${params.qaLogId}`,
  );
}

export async function fetchUserInquiries(
  params: ActivityFetchParams,
): Promise<PagedResponse<UserInquiryItem>> {
  const qs = buildQuery(params);
  return fetchJSON(
    `${API_BASE}/api/v1/admin/users/${params.userId}/inquiries?${qs}`,
  );
}

export async function fetchUserAnomalyEvents(
  params: ActivityFetchParams,
): Promise<PagedResponse<UserAnomalyEventItem>> {
  const qs = buildQuery(params);
  return fetchJSON(
    `${API_BASE}/api/v1/admin/users/${params.userId}/anomaly-events?${qs}`,
  );
}
