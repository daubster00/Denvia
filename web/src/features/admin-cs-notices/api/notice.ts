/** 관리자 쪽지(공지) API 클라이언트 — Story 7.1. */

import { z } from "zod";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type NoticeTargetSegment =
  | "all"
  | "doctor"
  | "hygienist"
  | "student_other";

export type NoticeItemType = "notice" | "admin_dm";

export type NoticeTargetFilter = "all" | "broadcast" | "dm";

export const noticeFormSchema = z.object({
  title: z
    .string()
    .min(1, "제목을 입력해주세요")
    .max(200, "제목은 200자 이내"),
  body_html: z
    .string()
    .min(1, "본문을 입력해주세요")
    .max(20000, "본문이 너무 깁니다"),
  target_segment: z.enum(["all", "doctor", "hygienist", "student_other"]),
});

export type NoticeFormInput = z.infer<typeof noticeFormSchema>;

export interface NoticeListItem {
  item_type: NoticeItemType;
  /** notice 행: notices.id / admin_dm 행: inbox_messages.id */
  id: number;
  title: string;
  /** notice 행에만 채워짐 */
  target_segment: NoticeTargetSegment | null;
  /** admin_dm 행에만 채워짐 */
  target_user_id: number | null;
  target_user_email: string | null;
  published_at: string | null;
  created_by_admin_id: number | null;
  created_at: string;
  delivered_user_count: number;
}

export interface NoticeListResponse {
  items: NoticeListItem[];
  page: number;
  per_page: number;
  total: number;
}

export interface NoticeDetail {
  id: number;
  title: string;
  target_segment: NoticeTargetSegment;
  published_at: string | null;
  created_by_admin_id: number;
  created_at: string;
  delivered_user_count: number;
  body_html: string;
}

export interface AdminDMDetail {
  item_type: "admin_dm";
  id: number;
  title: string;
  body_html: string;
  target_user_id: number;
  target_user_email: string;
  target_user_name: string | null;
  is_read: boolean;
  created_by_admin_id: number | null;
  created_at: string;
  deleted_at: string | null;
}

export type NoticeRecipientStatus = "read" | "unread";

export interface NoticeRecipient {
  user_id: number;
  email: string;
  name: string | null;
  segment: NoticeTargetSegment | string | null;
  is_read: boolean;
  delivered_at: string;
}

export interface NoticeRecipientsResponse {
  items: NoticeRecipient[];
  page: number;
  per_page: number;
  total: number;
  read_count: number;
  unread_count: number;
  status: NoticeRecipientStatus;
}

export interface InboxPreviewConfig {
  max_count: number;
}

class NoticeApiError extends Error {
  code?: string;
  status: number;
  constructor(message: string, status: number, code?: string) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

async function parseError(res: Response): Promise<NoticeApiError> {
  let body: { code?: string; message?: string; detail?: { code?: string; message?: string } } = {};
  try {
    body = await res.json();
  } catch {
    // ignore
  }
  const code = body.code ?? body.detail?.code;
  const message =
    body.message ?? body.detail?.message ?? `요청에 실패했습니다 (${res.status})`;
  return new NoticeApiError(message, res.status, code);
}

export async function fetchNotices(
  page = 1,
  perPage = 20,
  targetFilter: NoticeTargetFilter = "all",
): Promise<NoticeListResponse> {
  const url =
    `${API_BASE}/api/v1/admin/notices?page=${page}&per_page=${perPage}` +
    `&target_filter=${targetFilter}`;
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) throw await parseError(res);
  return res.json();
}

export async function fetchAdminDmDetail(
  messageId: number,
): Promise<AdminDMDetail> {
  const url = `${API_BASE}/api/v1/admin/notices/dm/${messageId}`;
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) throw await parseError(res);
  return res.json();
}

export async function deleteAdminDm(messageId: number): Promise<void> {
  const res = await fetch(
    `${API_BASE}/api/v1/admin/notices/dm/${messageId}`,
    { method: "DELETE", credentials: "include" },
  );
  if (!res.ok) throw await parseError(res);
}

export async function fetchNoticeDetail(id: number): Promise<NoticeDetail> {
  const url = `${API_BASE}/api/v1/admin/notices/${id}`;
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) throw await parseError(res);
  return res.json();
}

export async function fetchNoticeRecipients(
  id: number,
  status: NoticeRecipientStatus,
  page = 1,
  perPage = 20,
): Promise<NoticeRecipientsResponse> {
  const url =
    `${API_BASE}/api/v1/admin/notices/${id}/recipients` +
    `?status=${status}&page=${page}&per_page=${perPage}`;
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) throw await parseError(res);
  return res.json();
}

export async function createNotice(
  input: NoticeFormInput,
): Promise<NoticeDetail> {
  const res = await fetch(`${API_BASE}/api/v1/admin/notices`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) throw await parseError(res);
  return res.json();
}

export async function deleteNotice(id: number): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/admin/notices/${id}`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!res.ok) throw await parseError(res);
}

export async function fetchInboxPreviewConfig(): Promise<InboxPreviewConfig> {
  const res = await fetch(
    `${API_BASE}/api/v1/admin/inbox/preview-config`,
    { credentials: "include" },
  );
  if (!res.ok) throw await parseError(res);
  return res.json();
}

export async function updateInboxPreviewConfig(
  maxCount: number,
): Promise<InboxPreviewConfig> {
  const res = await fetch(
    `${API_BASE}/api/v1/admin/inbox/preview-config`,
    {
      method: "PUT",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ max_count: maxCount }),
    },
  );
  if (!res.ok) throw await parseError(res);
  return res.json();
}

export { NoticeApiError };
