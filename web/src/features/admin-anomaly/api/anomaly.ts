/**
 * Story 6.5 — Admin 이상 이벤트 API 클라이언트.
 *
 * 백엔드 GET /api/v1/admin/anomaly 와 PATCH /api/v1/admin/anomaly/{id} 의 fetcher.
 * 6.1 features/admin-users/api/users.ts 패턴 차용.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type AnomalyType =
  | "login_brute_force"
  | "concurrent_ip_login"
  | "repeated_question"
  | "recovery_abuse"
  | "rapid_followup_questions"
  | "sms_abuse";

export type AnomalyStatus = "new" | "reviewed" | "actioned" | "unblocked";

export interface AnomalyEventItem {
  id: number;
  type: AnomalyType;
  target_user_id: number | null;
  target_user_email_masked: string | null;
  ip: string | null;
  ua: string | null;
  details: Record<string, unknown>;
  status: AnomalyStatus;
  reviewed_by_admin_id: number | null;
  reviewed_at: string | null;
  created_at: string;
  occurrence_count: number;
  last_occurred_at: string | null;
  /**
   * 대상 사용자의 "지금" 차단 활성 여부.
   * 24h/7d/영구(subscription_status='blocked') 또는 blocked_until > now 면 true.
   */
  user_blocked_now: boolean;
  /**
   * 대상 사용자의 "지금" 자동제한 활성 여부.
   * users.anomaly_throttled_at IS NOT NULL, 또는 login_brute_force 의 Redis 자동 락아웃 활성.
   */
  user_auto_throttled_now: boolean;
}

export interface AnomalyHistoryItem {
  id: number;
  status: AnomalyStatus;
  ip: string | null;
  ua: string | null;
  details: Record<string, unknown>;
  reviewed_by_admin_id: number | null;
  reviewed_at: string | null;
  created_at: string;
}

export interface AnomalyListResponse {
  items: AnomalyEventItem[];
  page: number;
  per_page: number;
  total: number;
}

export interface FetchAnomalyParams {
  type_in?: AnomalyType[];
  status_in?: AnomalyStatus[];
  target_user_id?: number;
  from?: string;
  to?: string;
  page?: number;
  per_page?: number;
}

export class AnomalyApiError extends Error {
  status: number;
  code: string;
  traceId?: string;

  constructor(status: number, code: string, message: string, traceId?: string) {
    super(message);
    this.name = "AnomalyApiError";
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
    /* fallthrough */
  }
  throw new AnomalyApiError(res.status, code, message, traceId);
}

export async function fetchAnomalyList(
  params: FetchAnomalyParams = {},
): Promise<AnomalyListResponse> {
  const search = new URLSearchParams();
  if (params.type_in?.length) search.set("type_in", params.type_in.join(","));
  if (params.status_in?.length) search.set("status_in", params.status_in.join(","));
  if (params.target_user_id !== undefined) {
    search.set("target_user_id", String(params.target_user_id));
  }
  if (params.from) search.set("from", params.from);
  if (params.to) search.set("to", params.to);
  if (params.page !== undefined) search.set("page", String(params.page));
  if (params.per_page !== undefined) search.set("per_page", String(params.per_page));

  const qs = search.toString();
  const url = `${API_BASE}/api/v1/admin/anomaly${qs ? `?${qs}` : ""}`;
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) {
    await _throwFromResponse(res, "이상 이벤트 목록을 불러오지 못했습니다.");
  }
  return res.json() as Promise<AnomalyListResponse>;
}

export interface AnomalyDetailResponse extends AnomalyEventItem {
  admin_memo: string | null;
  auto_actioned: boolean;
  history: AnomalyHistoryItem[];
  user_subscription_status: "free" | "pro" | "blocked" | null;
  user_blocked_until: string | null;
  user_block_reason: string | null;
  user_anomaly_throttled_at: string | null;
  /**
   * login_brute_force 의 Redis 자동 락아웃 상태(이메일 기반).
   * - login_auto_lockout_until: 1차(10분) 잠금 만료 시각. 없으면 null.
   * - login_hard_locked: 2차(비번찾기 전까지) 잠금 활성 여부.
   */
  login_auto_lockout_until: string | null;
  login_hard_locked: boolean;
}

export async function fetchAnomalyDetail(
  anomalyId: number,
): Promise<AnomalyDetailResponse> {
  const res = await fetch(
    `${API_BASE}/api/v1/admin/anomaly/${anomalyId}`,
    { credentials: "include" },
  );
  if (!res.ok) {
    await _throwFromResponse(res, "이상 이벤트 상세를 불러오지 못했습니다.");
  }
  return res.json() as Promise<AnomalyDetailResponse>;
}

export async function saveAnomalyMemo(
  anomalyId: number,
  memo: string,
): Promise<AnomalyDetailResponse> {
  const csrf = _readCookie("denvia_admin_csrf");
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (csrf) headers["X-CSRF-Token"] = csrf;

  const res = await fetch(
    `${API_BASE}/api/v1/admin/anomaly/${anomalyId}/memo`,
    {
      method: "PATCH",
      credentials: "include",
      headers,
      body: JSON.stringify({ memo }),
    },
  );
  if (!res.ok) {
    await _throwFromResponse(res, "메모 저장에 실패했습니다.");
  }
  return res.json() as Promise<AnomalyDetailResponse>;
}

/**
 * login_brute_force 자동 락아웃(Redis fail/lockout/stage/hard_lock) 수동 해제.
 * 사용자가 즉시 로그인 재시도 가능하게 된다.
 */
export async function clearLoginLockout(userId: number): Promise<void> {
  const csrf = _readCookie("denvia_admin_csrf");
  const headers: Record<string, string> = {};
  if (csrf) headers["X-CSRF-Token"] = csrf;

  const res = await fetch(
    `${API_BASE}/api/v1/admin/users/${userId}/login-lockout`,
    {
      method: "DELETE",
      credentials: "include",
      headers,
    },
  );
  if (!res.ok && res.status !== 204) {
    await _throwFromResponse(res, "로그인 잠금 해제에 실패했습니다.");
  }
}

export async function markAnomalyReviewed(
  anomalyId: number,
): Promise<AnomalyEventItem> {
  const csrf = _readCookie("denvia_csrf");
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (csrf) headers["X-CSRF-Token"] = csrf;

  const res = await fetch(
    `${API_BASE}/api/v1/admin/anomaly/${anomalyId}`,
    {
      method: "PATCH",
      credentials: "include",
      headers,
      body: JSON.stringify({ status: "reviewed" }),
    },
  );
  if (!res.ok) {
    await _throwFromResponse(res, "검토 완료 처리에 실패했습니다.");
  }
  return res.json() as Promise<AnomalyEventItem>;
}
