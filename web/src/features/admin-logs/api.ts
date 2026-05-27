/**
 * Story 10.4 — `/admin/admins/logs` API 클라이언트.
 *
 * 백엔드 `/api/v1/admin/accounts/logs*` 와 1:1.
 * - 401/403 에 대해 페이지가 자체적으로 토스트로 노출 (자동 리다이렉트 안 함).
 * - AdminAccounts 와 동일 패턴 (Story 10.3 `admin-accounts/api.ts`).
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface AdminLogItem {
  id: number;
  created_at: string; // ISO 8601 UTC
  actor_user_id: number;
  actor_email: string;
  action: string;
  target_type: string | null;
  target_id: number | null;
  target_preview: string | null;
  ip: string | null;
  has_diff: boolean;
}

export interface AdminLogListResponse {
  items: AdminLogItem[];
  next_cursor: string | null;
}

export interface AdminLogDiffResponse {
  id: number;
  diff_json: unknown;
}

export interface AdminLogFilters {
  actor_id?: number | "system" | null;
  action_in?: string[];
  from_at?: string | null; // ISO 8601
  to_at?: string | null;
  target_id?: number | null;
  cursor?: string | null;
  limit?: number;
}

export class AdminLogsApiError extends Error {
  status: number;
  code: string;
  traceId?: string;

  constructor(status: number, code: string, message: string, traceId?: string) {
    super(message);
    this.name = "AdminLogsApiError";
    this.status = status;
    this.code = code;
    this.traceId = traceId;
  }
}

async function _throwFromResponse(
  res: Response,
  fallback: string,
): Promise<never> {
  let code = "UNKNOWN_ERROR";
  let message = fallback;
  let traceId: string | undefined;
  try {
    const body = (await res.json()) as {
      code?: string;
      message?: string;
      detail?: { code?: string; message?: string };
      trace_id?: string;
    };
    if (body.detail?.code) code = body.detail.code;
    else if (body.code) code = body.code;
    if (body.detail?.message) message = body.detail.message;
    else if (body.message) message = body.message;
    if (body.trace_id) traceId = body.trace_id;
  } catch {
    /* fall through */
  }
  throw new AdminLogsApiError(res.status, code, message, traceId);
}

function _buildQuery(filters: AdminLogFilters): string {
  const qs = new URLSearchParams();
  if (filters.actor_id !== undefined && filters.actor_id !== null) {
    qs.set("actor_id", String(filters.actor_id));
  }
  if (filters.action_in && filters.action_in.length > 0) {
    qs.set("action_in", filters.action_in.join(","));
  }
  if (filters.from_at) qs.set("from_at", filters.from_at);
  if (filters.to_at) qs.set("to_at", filters.to_at);
  if (filters.target_id !== undefined && filters.target_id !== null) {
    qs.set("target_id", String(filters.target_id));
  }
  if (filters.cursor) qs.set("cursor", filters.cursor);
  if (filters.limit !== undefined) qs.set("limit", String(filters.limit));
  return qs.toString();
}

export async function fetchLogs(
  filters: AdminLogFilters,
): Promise<AdminLogListResponse> {
  const qs = _buildQuery(filters);
  const url = `${API_BASE}/api/v1/admin/accounts/logs${qs ? `?${qs}` : ""}`;
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) await _throwFromResponse(res, "로그를 불러오지 못했습니다.");
  return res.json() as Promise<AdminLogListResponse>;
}

export async function fetchLogDiff(
  logId: number,
): Promise<AdminLogDiffResponse> {
  const url = `${API_BASE}/api/v1/admin/accounts/logs/${logId}/diff`;
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) await _throwFromResponse(res, "변경 내역을 불러오지 못했습니다.");
  return res.json() as Promise<AdminLogDiffResponse>;
}

export function buildExportUrl(filters: AdminLogFilters): string {
  const qs = _buildQuery({ ...filters, cursor: null, limit: undefined });
  return `${API_BASE}/api/v1/admin/accounts/logs/export.xlsx${qs ? `?${qs}` : ""}`;
}

export async function triggerExport(filters: AdminLogFilters): Promise<{
  truncated: boolean;
  filename: string;
}> {
  const url = buildExportUrl(filters);
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) await _throwFromResponse(res, "엑셀 다운로드에 실패했습니다.");

  const truncated = res.headers.get("x-truncated") === "true";
  const disposition = res.headers.get("content-disposition") ?? "";
  const match = disposition.match(/filename="([^"]+)"/);
  const filename = match ? match[1] : "admin_logs.xlsx";

  // 브라우저 다운로드 트리거
  const blob = await res.blob();
  const blobUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = blobUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(blobUrl);

  return { truncated, filename };
}
