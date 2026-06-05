/** CS · 휴지통(쪽지) 관리 API 클라이언트. */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type InboxMessageType =
  | "notice"
  | "system"
  | "billing"
  | "admin_dm";

export interface TrashListItem {
  message_id: number;
  type: InboxMessageType;
  title: string;
  user_id: number;
  user_email: string;
  user_name: string | null;
  created_at: string;
  deleted_at: string;
  permanent_purge_at: string;
}

export interface TrashListResponse {
  items: TrashListItem[];
  page: number;
  per_page: number;
  total: number;
}

export interface TrashDetail {
  message_id: number;
  type: InboxMessageType;
  title: string;
  body_html_safe: string;
  user_id: number;
  user_email: string;
  user_name: string | null;
  is_read: boolean;
  created_at: string;
  deleted_at: string;
  permanent_purge_at: string;
  created_by_admin_id: number | null;
}

export class TrashApiError extends Error {
  code?: string;
  status: number;
  constructor(message: string, status: number, code?: string) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

async function parseError(res: Response): Promise<TrashApiError> {
  let body: {
    code?: string;
    message?: string;
    detail?: { code?: string; message?: string };
  } = {};
  try {
    body = await res.json();
  } catch {
    // ignore
  }
  const code = body.code ?? body.detail?.code;
  const message =
    body.message ??
    body.detail?.message ??
    `요청에 실패했습니다 (${res.status})`;
  return new TrashApiError(message, res.status, code);
}

export async function fetchTrashList(
  page = 1,
  perPage = 20,
): Promise<TrashListResponse> {
  const url = `${API_BASE}/api/v1/admin/inbox/trash?page=${page}&per_page=${perPage}`;
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) throw await parseError(res);
  return res.json();
}

export async function fetchTrashDetail(
  messageId: number,
): Promise<TrashDetail> {
  const url = `${API_BASE}/api/v1/admin/inbox/trash/${messageId}`;
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) throw await parseError(res);
  return res.json();
}

export async function restoreTrashMessage(
  messageId: number,
): Promise<TrashDetail> {
  const url = `${API_BASE}/api/v1/admin/inbox/trash/${messageId}/restore`;
  const res = await fetch(url, { method: "POST", credentials: "include" });
  if (!res.ok) throw await parseError(res);
  return res.json();
}

export async function hardDeleteTrashMessage(
  messageId: number,
): Promise<void> {
  const url = `${API_BASE}/api/v1/admin/inbox/trash/${messageId}`;
  const res = await fetch(url, { method: "DELETE", credentials: "include" });
  if (!res.ok) throw await parseError(res);
}
