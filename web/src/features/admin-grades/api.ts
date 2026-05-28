/**
 * 관리자 등급 CRUD API (백엔드 /api/v1/admin/grades 와 1:1).
 *
 * 등급 SSOT — 내장 4종(master/operator/sub_operator/pending) + 커스텀(g_<hex>).
 * 등급 변경 모달 / 권한 매트릭스 / 등급 관리 페이지에서 공통으로 사용.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface AdminGradeItem {
  code: string;
  label: string;
  is_builtin: boolean;
  user_count: number;
  created_at: string;
}

export interface AdminGradeListResponse {
  items: AdminGradeItem[];
}

export class AdminGradesApiError extends Error {
  status: number;
  code: string;
  traceId?: string;

  constructor(status: number, code: string, message: string, traceId?: string) {
    super(message);
    this.name = "AdminGradesApiError";
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
    /* noop */
  }
  throw new AdminGradesApiError(res.status, code, message, traceId);
}

function _writeHeaders(): Record<string, string> {
  const csrf = _readCookie("denvia_admin_csrf");
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (csrf) headers["X-CSRF-Token"] = csrf;
  return headers;
}

export async function fetchAdminGrades(): Promise<AdminGradeListResponse> {
  const res = await fetch(`${API_BASE}/api/v1/admin/grades`, {
    credentials: "include",
  });
  if (!res.ok) await _throwFromResponse(res, "등급 목록을 불러오지 못했습니다.");
  return res.json() as Promise<AdminGradeListResponse>;
}

export async function createAdminGrade(label: string): Promise<AdminGradeItem> {
  const res = await fetch(`${API_BASE}/api/v1/admin/grades`, {
    method: "POST",
    credentials: "include",
    headers: _writeHeaders(),
    body: JSON.stringify({ label }),
  });
  if (!res.ok) await _throwFromResponse(res, "등급 추가에 실패했습니다.");
  return res.json() as Promise<AdminGradeItem>;
}

export async function deleteAdminGrade(code: string): Promise<void> {
  const res = await fetch(
    `${API_BASE}/api/v1/admin/grades/${encodeURIComponent(code)}`,
    {
      method: "DELETE",
      credentials: "include",
      headers: _writeHeaders(),
    },
  );
  if (!res.ok) await _throwFromResponse(res, "등급 삭제에 실패했습니다.");
}
