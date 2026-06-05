/** 관리자 — 토스 PG 설정 (모드 토글 + 4개 키) API 클라이언트.
 *
 * 서버 SSOT 는 Redis. 응답의 키는 항상 마스킹된 형태로 내려오며, 수정 시에는
 * 빈 입력창에 새 값을 그대로 보낸다(빈 문자열/공백은 서버에서 무시).
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type TossMode = "test" | "live";

export interface TossPgKeyView {
  masked: string;
  has_value: boolean;
}

export interface TossPgConfig {
  mode: TossMode;
  test_client: TossPgKeyView;
  test_secret: TossPgKeyView;
  live_client: TossPgKeyView;
  live_secret: TossPgKeyView;
}

export interface TossPgConfigUpdatePayload {
  mode?: TossMode;
  test_client_key?: string;
  test_secret_key?: string;
  live_client_key?: string;
  live_secret_key?: string;
}

async function parseError(res: Response, fallback: string): Promise<Error> {
  let detail = `${fallback} (HTTP ${res.status})`;
  try {
    const body = (await res.json()) as { detail?: unknown; message?: unknown };
    if (typeof body?.detail === "string") detail = body.detail;
    else if (typeof body?.message === "string") detail = body.message;
  } catch {
    // ignore
  }
  return new Error(detail);
}

export async function fetchTossPgConfig(): Promise<TossPgConfig> {
  const res = await fetch(`${API_BASE}/api/v1/admin/runtime-config/toss-pg`, {
    credentials: "include",
  });
  if (!res.ok) throw await parseError(res, "토스 PG 설정을 불러오지 못했습니다");
  return (await res.json()) as TossPgConfig;
}

export async function updateTossPgConfig(
  payload: TossPgConfigUpdatePayload,
): Promise<TossPgConfig> {
  const res = await fetch(`${API_BASE}/api/v1/admin/runtime-config/toss-pg`, {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw await parseError(res, "토스 PG 설정 저장에 실패했습니다");
  return (await res.json()) as TossPgConfig;
}
