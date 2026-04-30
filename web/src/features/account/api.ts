/** features/account API 클라이언트 — Story 4.3. */

import { apiFetch } from "@/lib/api-client";
import type { UsageSummary } from "./types";

/** GET /api/v1/me/usage-summary — 마이페이지 통합 응답 (FR26·FR28·FR48). */
export async function fetchUsageSummary(): Promise<UsageSummary> {
  return apiFetch<UsageSummary>("/api/v1/me/usage-summary");
}
