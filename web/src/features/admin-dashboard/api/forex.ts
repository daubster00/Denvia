const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface ForexConfig {
  rate: number;
  default_rate: number;
  updated_at: string | null;   // ISO8601 UTC
  search_date: string | null;  // YYYY-MM-DD
  source: "auto" | "fallback";
}

async function parseError(res: Response, fallback: string): Promise<Error> {
  let detail = `${fallback} (HTTP ${res.status})`;
  try {
    const body = (await res.json()) as { detail?: string | unknown; message?: string };
    if (typeof body?.detail === "string") {
      detail = body.detail;
    } else if (typeof body?.message === "string") {
      detail = body.message;
    }
  } catch {
    // ignore
  }
  return new Error(detail);
}

export async function fetchForexConfig(): Promise<ForexConfig> {
  const res = await fetch(`${API_BASE}/api/v1/admin/runtime-config/forex`, {
    credentials: "include",
  });
  if (!res.ok) throw await parseError(res, "환율 정보를 불러오지 못했습니다");
  return res.json() as Promise<ForexConfig>;
}
