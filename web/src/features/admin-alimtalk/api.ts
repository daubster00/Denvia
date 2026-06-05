/**
 * Story 4.6 — `/admin/alimtalk` API 클라이언트.
 *
 * 백엔드 `/api/v1/admin/alimtalk/*` 와 1:1.
 * - 401/403 은 페이지가 토스트로 노출 (자동 리다이렉트 안 함).
 * - Story 10.4 `admin-logs/api.ts` 패턴 답습.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// 🚫 "notice" 카테고리는 백엔드 admin_catalog가 자동 제외하므로 실제로 응답에 오지 않는다.
// 사용자가 또 등장시키지 말 것 — feedback_no_notice_alimtalk_in_admin_ui.
export type AlimtalkCategory =
  | "billing"
  | "subscription"
  | "system"
  | "support"
  | "sms";

export type MessagingChannel = "alimtalk" | "sms";
export type RecipientKind = "user" | "admin";

export interface AlimtalkTemplateStat {
  template_code: string;
  title: string;
  category: AlimtalkCategory;
  channel: MessagingChannel;
  aligo_tpl_code: string | null;
  recipient_kind: RecipientKind;
  trigger_situation: string;
  body_example: string;
  today_sent: number;
  today_failed: number;
  month_sent: number;
  month_failed: number;
}

export interface AlimtalkSummaryTotals {
  today_sent: number;
  today_failed: number;
  month_sent: number;
  month_failed: number;
}

export interface AlimtalkSummary {
  totals: AlimtalkSummaryTotals;
  templates: AlimtalkTemplateStat[];
}

export interface AlimtalkLogItem {
  id: number;
  created_at: string;
  sent_at: string | null;
  user_id: number | null;
  phone_masked: string | null;
  channel: string;
  status: string;
  attempts: number;
  last_error: string | null;
  /** 관리자가 직접 "테스트 발송"을 누른 row. idempotency_key가 "test:" 로 시작. */
  is_test: boolean;
}

export interface AlimtalkLogList {
  items: AlimtalkLogItem[];
  next_cursor: string | null;
  total: number | null;
  page: number | null;
  per_page: number | null;
  total_pages: number | null;
}

export interface TestRecipient {
  phone_masked: string | null;
  is_set: boolean;
}

export interface TestSendResult {
  success: boolean;
  template_code: string;
  phone_masked: string | null;
  aligo_response_code: string;
  error_message: string | null;
  message_id?: string | null;
}

export class AdminAlimtalkApiError extends Error {
  status: number;
  code: string;
  traceId?: string;

  constructor(status: number, code: string, message: string, traceId?: string) {
    super(message);
    this.name = "AdminAlimtalkApiError";
    this.status = status;
    this.code = code;
    this.traceId = traceId;
  }
}

async function _throwFromResponse(res: Response, fallback: string): Promise<never> {
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
  throw new AdminAlimtalkApiError(res.status, code, message, traceId);
}

// ── GET /summary ─────────────────────────────────────────────────────────

export async function fetchSummary(signal?: AbortSignal): Promise<AlimtalkSummary> {
  const res = await fetch(`${API_BASE}/api/v1/admin/alimtalk/summary`, {
    credentials: "include",
    cache: "no-store",
    signal,
  });
  if (!res.ok) await _throwFromResponse(res, "요약을 불러오지 못했습니다.");
  return (await res.json()) as AlimtalkSummary;
}

// ── GET /logs ────────────────────────────────────────────────────────────

export interface FetchLogsParams {
  template_code: string;
  status?: "sent" | "failed" | "all";
  /** Cursor pagination (legacy) — page/per_page를 쓰면 무시된다. */
  cursor?: string | null;
  /** Cursor pagination 전용. page 모드에서는 의미 없음. */
  limit?: number;
  /** 1-based page number. 지정 시 page-number pagination 모드. */
  page?: number;
  /** Page size (1..100). 기본 20. */
  per_page?: number;
}

export async function fetchLogs(
  params: FetchLogsParams,
  signal?: AbortSignal,
): Promise<AlimtalkLogList> {
  const qs = new URLSearchParams();
  qs.set("template_code", params.template_code);
  qs.set("status", params.status ?? "all");
  if (params.page !== undefined) {
    qs.set("page", String(params.page));
    qs.set("per_page", String(params.per_page ?? 20));
  } else {
    if (params.cursor) qs.set("cursor", params.cursor);
    qs.set("limit", String(params.limit ?? 100));
  }
  const res = await fetch(`${API_BASE}/api/v1/admin/alimtalk/logs?${qs.toString()}`, {
    credentials: "include",
    cache: "no-store",
    signal,
  });
  if (!res.ok) await _throwFromResponse(res, "로그를 불러오지 못했습니다.");
  return (await res.json()) as AlimtalkLogList;
}

// ── GET/PUT/DELETE /test-recipient ──────────────────────────────────────

export async function getTestRecipient(signal?: AbortSignal): Promise<TestRecipient> {
  const res = await fetch(`${API_BASE}/api/v1/admin/alimtalk/test-recipient`, {
    credentials: "include",
    cache: "no-store",
    signal,
  });
  if (!res.ok) await _throwFromResponse(res, "수신 번호 조회에 실패했습니다.");
  return (await res.json()) as TestRecipient;
}

export async function setTestRecipient(phone: string): Promise<TestRecipient> {
  const res = await fetch(`${API_BASE}/api/v1/admin/alimtalk/test-recipient`, {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phone }),
  });
  if (!res.ok) await _throwFromResponse(res, "수신 번호 저장에 실패했습니다.");
  return (await res.json()) as TestRecipient;
}

export async function clearTestRecipient(): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/admin/alimtalk/test-recipient`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!res.ok) await _throwFromResponse(res, "수신 번호 해제에 실패했습니다.");
}

// ── POST /test-send ──────────────────────────────────────────────────────

export async function dispatchTestSend(template_code: string): Promise<TestSendResult> {
  const res = await fetch(`${API_BASE}/api/v1/admin/alimtalk/test-send`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ template_code }),
  });
  if (!res.ok) await _throwFromResponse(res, "테스트 발송에 실패했습니다.");
  return (await res.json()) as TestSendResult;
}
