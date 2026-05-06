/**
 * Story 6.2 — Admin 감사 로그 조회 API 클라이언트.
 *
 * 백엔드 GET /api/v1/admin/audit-logs (Story 5.1 + 6.2 확장)의 fetcher.
 * 6.2에서 action_in / target_id / actor_email / target_email / diff_json 필드 활용.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface AuditLogItem {
  id: number;
  actor_user_id: number;
  actor_email: string | null;
  action: string;
  target_type: string | null;
  target_id: number | null;
  target_email: string | null;
  diff_json: Record<string, unknown> | null;
  ip: string | null;
  ua: string | null;
  trace_id: string | null;
  created_at: string;
}

export interface AuditLogListResponse {
  items: AuditLogItem[];
  page: number;
  per_page: number;
  total: number;
}

export interface FetchAuditLogsParams {
  action_in?: string[]; // 콤마 직렬화는 fetcher 내부에서 처리
  target_id?: number;
  actor_filter?: number;
  page?: number;
  per_page?: number;
}

export async function fetchAuditLogs(
  params: FetchAuditLogsParams = {},
): Promise<AuditLogListResponse> {
  const query = new URLSearchParams();
  if (params.action_in && params.action_in.length > 0) {
    query.set("action_in", params.action_in.join(","));
  }
  if (params.target_id !== undefined) {
    query.set("target_id", String(params.target_id));
  }
  if (params.actor_filter !== undefined) {
    query.set("actor_filter", String(params.actor_filter));
  }
  if (params.page) query.set("page", String(params.page));
  if (params.per_page) query.set("per_page", String(params.per_page));

  const res = await fetch(
    `${API_BASE}/api/v1/admin/audit-logs?${query.toString()}`,
    { credentials: "include" },
  );
  if (!res.ok) {
    throw new Error(`admin audit-logs fetch failed: ${res.status}`);
  }
  return res.json() as Promise<AuditLogListResponse>;
}
