/**
 * Story 10.5 — 등급 × 페이지 권한 매트릭스 API 클라이언트.
 *
 * 백엔드 /api/v1/admin/grade-permissions 와 1:1 매핑.
 * - 401 발생 시 페이지 측이 토스트로 노출하도록 상세 에러 코드를 throw.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// 0057 이후 동적 코드(VARCHAR) — 내장 operator/sub_operator + 커스텀(g_<hex>).
export type ConfigurableGrade = string;

export interface GradePermissionRow {
  admin_grade: ConfigurableGrade;
  page_route: string;
  allowed: boolean;
}

export interface PageMeta {
  page_route: string;
  label: string;
}

export interface GradeMeta {
  code: string;
  label: string;
  is_builtin: boolean;
}

export interface GradePermissionMatrixResponse {
  pages: PageMeta[];
  grades: ConfigurableGrade[];
  grade_meta: GradeMeta[];
  rows: GradePermissionRow[];
}

export class GradePermissionsApiError extends Error {
  status: number;
  code: string;
  traceId?: string;

  constructor(status: number, code: string, message: string, traceId?: string) {
    super(message);
    this.name = "GradePermissionsApiError";
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
  throw new GradePermissionsApiError(res.status, code, message, traceId);
}

function _writeHeaders(): Record<string, string> {
  const csrf = _readCookie("denvia_admin_csrf");
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (csrf) headers["X-CSRF-Token"] = csrf;
  return headers;
}

export async function fetchGradePermissionMatrix(): Promise<GradePermissionMatrixResponse> {
  const res = await fetch(`${API_BASE}/api/v1/admin/grade-permissions`, {
    credentials: "include",
  });
  if (!res.ok) {
    await _throwFromResponse(res, "권한 매트릭스를 불러오지 못했습니다.");
  }
  return res.json() as Promise<GradePermissionMatrixResponse>;
}

export async function patchGradePermission(payload: {
  admin_grade: string;
  page_route: string;
  allowed: boolean;
}): Promise<GradePermissionRow> {
  const res = await fetch(`${API_BASE}/api/v1/admin/grade-permissions`, {
    method: "PATCH",
    credentials: "include",
    headers: _writeHeaders(),
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    await _throwFromResponse(res, "권한 변경에 실패했습니다.");
  }
  return res.json() as Promise<GradePermissionRow>;
}
