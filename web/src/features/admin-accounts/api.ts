/**
 * Story 10.3 — 관리자 계정 관리 API 클라이언트.
 *
 * 백엔드 /api/v1/admin/accounts/* 와 1:1 매핑.
 * - 401 발생 시 adminApiFetch 처럼 /admin/login 으로 보내지 않고,
 *   상세 에러 코드를 throw 해 페이지 측이 토스트로 노출하게 한다.
 *   (require_admin_grade 403 ADMIN_FORBIDDEN_GRADE 같은 메시지를 그대로 표시)
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type AdminGrade = "master" | "operator" | "sub_operator" | "pending";

export type AdminListFilter = "all" | "pending" | "active" | "blocked";

export interface AdminAccountItem {
  id: number;
  email: string;
  admin_grade: AdminGrade;
  grade_label: string;
  phone_masked: string | null;
  admin_blocked_until: string | null;
  admin_block_reason: string | null;
  admin_signup_at: string | null;
  last_login_at: string | null;
  created_at: string;
}

export interface AdminAccountListResponse {
  items: AdminAccountItem[];
  total: number;
}

export class AdminAccountsApiError extends Error {
  status: number;
  code: string;
  traceId?: string;

  constructor(status: number, code: string, message: string, traceId?: string) {
    super(message);
    this.name = "AdminAccountsApiError";
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
  throw new AdminAccountsApiError(res.status, code, message, traceId);
}

function _writeHeaders(): Record<string, string> {
  const csrf = _readCookie("denvia_admin_csrf");
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (csrf) headers["X-CSRF-Token"] = csrf;
  return headers;
}

export async function fetchAdminAccounts(
  filter: AdminListFilter = "all",
): Promise<AdminAccountListResponse> {
  const url = `${API_BASE}/api/v1/admin/accounts?filter=${encodeURIComponent(filter)}`;
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) {
    await _throwFromResponse(res, "관리자 목록을 불러오지 못했습니다.");
  }
  return res.json() as Promise<AdminAccountListResponse>;
}

export async function approveAdmin(
  userId: number,
  targetGrade: "sub_operator" | "operator",
): Promise<AdminAccountItem> {
  const res = await fetch(
    `${API_BASE}/api/v1/admin/accounts/${userId}/approve`,
    {
      method: "POST",
      credentials: "include",
      headers: _writeHeaders(),
      body: JSON.stringify({ target_grade: targetGrade }),
    },
  );
  if (!res.ok) await _throwFromResponse(res, "승인 처리에 실패했습니다.");
  return res.json() as Promise<AdminAccountItem>;
}

export async function blockAdmin(
  userId: number,
  payload: { blocked_until: string; reason: string },
): Promise<AdminAccountItem> {
  const res = await fetch(
    `${API_BASE}/api/v1/admin/accounts/${userId}/block`,
    {
      method: "POST",
      credentials: "include",
      headers: _writeHeaders(),
      body: JSON.stringify(payload),
    },
  );
  if (!res.ok) await _throwFromResponse(res, "차단 처리에 실패했습니다.");
  return res.json() as Promise<AdminAccountItem>;
}

export async function unblockAdmin(userId: number): Promise<AdminAccountItem> {
  const res = await fetch(
    `${API_BASE}/api/v1/admin/accounts/${userId}/unblock`,
    {
      method: "POST",
      credentials: "include",
      headers: _writeHeaders(),
    },
  );
  if (!res.ok) await _throwFromResponse(res, "차단 해제에 실패했습니다.");
  return res.json() as Promise<AdminAccountItem>;
}

export async function deleteAdmin(userId: number): Promise<void> {
  const res = await fetch(
    `${API_BASE}/api/v1/admin/accounts/${userId}`,
    {
      method: "DELETE",
      credentials: "include",
      headers: _writeHeaders(),
    },
  );
  if (!res.ok) await _throwFromResponse(res, "삭제에 실패했습니다.");
}

export async function patchAdminGrade(
  userId: number,
  newGrade: AdminGrade,
): Promise<AdminAccountItem> {
  const res = await fetch(
    `${API_BASE}/api/v1/admin/accounts/${userId}`,
    {
      method: "PATCH",
      credentials: "include",
      headers: _writeHeaders(),
      body: JSON.stringify({ admin_grade: newGrade }),
    },
  );
  if (!res.ok) await _throwFromResponse(res, "등급 변경에 실패했습니다.");
  return res.json() as Promise<AdminAccountItem>;
}
