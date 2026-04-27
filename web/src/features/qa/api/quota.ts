import type { QuotaResponse } from "@/types/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function fetchQuota(): Promise<QuotaResponse> {
  const res = await fetch(`${API_BASE}/api/v1/me/quota`, { credentials: "include" });
  if (!res.ok) throw new Error(`quota fetch failed: ${res.status}`);
  return res.json();
}
