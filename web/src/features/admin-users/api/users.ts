/**
 * Story 6.1 — Admin 사용자 통합 검색 API 클라이언트.
 *
 * 백엔드 GET /api/v1/admin/users 와 GET /api/v1/admin/users/{user_id} 의 fetcher.
 * 5.3 features/admin-dashboard/api/analytics.ts 의 패턴을 그대로 차용.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type SubscriptionStatus = "free" | "pro" | "blocked";
export type Segment = "doctor" | "hygienist" | "student_other";

export interface UserSearchItem {
  user_id: number;
  email: string;
  phone: string | null;
  segment: Segment | null;
  years_of_experience: number | null;
  subscription_status: SubscriptionStatus;
  is_blocked: boolean;
  block_until: string | null;
  daily_quota_override: number | null;
  free_delay_override?: number | null;
  /** 이상 질문 패턴 자동 throttle 적용 시각. null=미적용. */
  anomaly_throttled_at?: string | null;
  created_at: string;
  last_login_at: string | null;
  withdrawn_at: string | null;
  pro_since: string | null;
  card_last4: string | null;
  card_company: string | null;
}

export interface UserSearchListResponse {
  items: UserSearchItem[];
  page: number;
  per_page: number;
  total: number;
}

export interface FetchUsersParams {
  q?: string;
  segment?: Segment;
  subscription_status?: SubscriptionStatus;
  blocked?: boolean;
  /**
   * 탈퇴 여부. true=탈퇴자만, false=탈퇴자 제외, undefined=무관.
   * 대시보드 구독 현황(무료/Pro/차단)에서 진입 시 false 를 함께 전달해야
   * 대시보드 카운트와 사용자 페이지 카운트가 일치한다.
   */
  withdrawn?: boolean;
  /** 가입일 시작 (YYYY-MM-DD, KST 기준 해당일 포함) */
  created_from?: string;
  /** 가입일 종료 (YYYY-MM-DD, KST 기준 해당일 포함) */
  created_to?: string;
  page?: number;
  per_page?: number;
}

export interface SubscriptionSummary {
  current_status: SubscriptionStatus;
  billing_key_active: boolean;
  card_last4: string | null;
  card_company: string | null;
  subscription_started_at: string | null;
  next_charge_at: string | null;
}

export interface RecentQALog {
  qa_log_id: number;
  question_excerpt: string;
  answer_excerpt: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  cost_usd: string | null;
  status: string | null;
  created_at: string;
}

export interface RecentAnomalyEvent {
  id: number;
  type: string;
  ip: string | null;
  status: string;
  created_at: string;
}

export interface UserDetailResponse {
  user: UserSearchItem;
  subscription_summary: SubscriptionSummary;
  recent_qa: RecentQALog[];
  recent_anomaly_events: RecentAnomalyEvent[];
}

export async function fetchUsers(
  params: FetchUsersParams = {},
): Promise<UserSearchListResponse> {
  const query = new URLSearchParams();
  const trimmedQ = params.q?.trim();
  if (trimmedQ) query.set("q", trimmedQ);
  if (params.segment) query.set("segment", params.segment);
  if (params.subscription_status)
    query.set("subscription_status", params.subscription_status);
  if (params.blocked !== undefined) query.set("blocked", String(params.blocked));
  if (params.withdrawn !== undefined)
    query.set("withdrawn", String(params.withdrawn));
  if (params.created_from) query.set("created_from", params.created_from);
  if (params.created_to) query.set("created_to", params.created_to);
  if (params.page) query.set("page", String(params.page));
  if (params.per_page) query.set("per_page", String(params.per_page));

  const res = await fetch(
    `${API_BASE}/api/v1/admin/users?${query.toString()}`,
    { credentials: "include" },
  );
  if (!res.ok) {
    throw new Error(`admin users fetch failed: ${res.status}`);
  }
  return res.json() as Promise<UserSearchListResponse>;
}

export async function fetchUserDetail(
  userId: number,
): Promise<UserDetailResponse> {
  const res = await fetch(`${API_BASE}/api/v1/admin/users/${userId}`, {
    credentials: "include",
  });
  if (!res.ok) {
    throw new Error(`admin user detail fetch failed: ${res.status}`);
  }
  return res.json() as Promise<UserDetailResponse>;
}

// Story 6.2 — PATCH /api/v1/admin/users/{user_id}
export interface BlockActionPayload {
  duration_hours: number | null;
  reason: string;
  /** 이상탐지 UI에서 차단 시 해당 anomaly_event.id. 백엔드가 status='actioned'로 전이. */
  anomaly_id?: number;
}

export interface UserPermissionUpdatePayload {
  subscription_status?: SubscriptionStatus;
  segment?: Segment;
  daily_quota_override?: number;
  daily_quota_override_clear?: boolean;
  block_action?: BlockActionPayload;
  unblock?: true;
  pro_granted_by_admin?: true;
}

export class UserPermissionUpdateError extends Error {
  status: number;
  code: string;
  traceId?: string;

  constructor(status: number, code: string, message: string, traceId?: string) {
    super(message);
    this.name = "UserPermissionUpdateError";
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

export async function clearAnomalyThrottle(userId: number): Promise<void> {
  const csrf = _readCookie("denvia_admin_csrf");
  const headers: Record<string, string> = {};
  if (csrf) headers["X-CSRF-Token"] = csrf;
  const res = await fetch(
    `${API_BASE}/api/v1/admin/users/${userId}/anomaly-throttle`,
    {
      method: "DELETE",
      credentials: "include",
      headers,
    },
  );
  if (!res.ok) {
    let code = "UNKNOWN_ERROR";
    let message = "throttle 해제에 실패했습니다.";
    try {
      const body = (await res.json()) as {
        code?: string;
        message?: string;
      };
      if (body.code) code = body.code;
      if (body.message) message = body.message;
    } catch {
      /* fallthrough */
    }
    throw new UserPermissionUpdateError(res.status, code, message);
  }
}

/**
 * 관리자 → 특정 사용자 1:1 안내 쪽지 발송.
 * POST /api/v1/admin/users/{user_id}/inbox-messages
 */
export interface AdminDMSendPayload {
  title: string;
  body_html: string;
}

export interface AdminDMSendResponse {
  message_id: number;
  target_user_id: number;
  created_at: string;
}

export async function sendAdminDM(
  userId: number,
  payload: AdminDMSendPayload,
): Promise<AdminDMSendResponse> {
  const csrf = _readCookie("denvia_admin_csrf");
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (csrf) headers["X-CSRF-Token"] = csrf;

  const res = await fetch(
    `${API_BASE}/api/v1/admin/users/${userId}/inbox-messages`,
    {
      method: "POST",
      credentials: "include",
      headers,
      body: JSON.stringify(payload),
    },
  );
  if (!res.ok) {
    let code = "UNKNOWN_ERROR";
    let message = "쪽지 발송에 실패했습니다.";
    try {
      const body = (await res.json()) as { code?: string; message?: string };
      if (body.code) code = body.code;
      if (body.message) message = body.message;
    } catch {
      /* fallthrough */
    }
    throw new UserPermissionUpdateError(res.status, code, message);
  }
  return res.json() as Promise<AdminDMSendResponse>;
}

export async function updateUserPermission(
  userId: number,
  payload: UserPermissionUpdatePayload,
): Promise<UserSearchItem> {
  const csrf = _readCookie("denvia_admin_csrf");
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (csrf) headers["X-CSRF-Token"] = csrf;

  const res = await fetch(`${API_BASE}/api/v1/admin/users/${userId}`, {
    method: "PATCH",
    credentials: "include",
    headers,
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    let code = "UNKNOWN_ERROR";
    let message = "권한 수정에 실패했습니다.";
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
    throw new UserPermissionUpdateError(res.status, code, message, traceId);
  }
  return res.json() as Promise<UserSearchItem>;
}
