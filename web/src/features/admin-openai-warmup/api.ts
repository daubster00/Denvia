/**
 * 마스터 전용 — OpenAI 워밍업 루프 토글 API 클라이언트.
 */

import { ApiError } from "@/types/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface WarmupStatus {
  running: boolean;
  started_at: string | null;
  last_ping_at: string | null;
  last_ping_latency_ms: number | null;
  last_ping_ok: boolean | null;
  last_error: string | null;
  total_pings: number;
  total_failures: number;
  interval_seconds: number;
  model: string;
}

async function call(path: string, method: "GET" | "POST"): Promise<WarmupStatus> {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    credentials: "include",
    headers: { "Content-Type": "application/json" },
  });
  const traceId = res.headers.get("X-Trace-Id") ?? "";
  if (!res.ok) {
    let body: Record<string, unknown> = {};
    try {
      body = await res.json();
    } catch {
      // ignore
    }
    throw new ApiError({
      code: (body["code"] as string) ?? "UNKNOWN_ERROR",
      message: (body["message"] as string) ?? res.statusText,
      trace_id: traceId,
    });
  }
  return res.json() as Promise<WarmupStatus>;
}

export const fetchWarmupStatus = () =>
  call("/api/v1/admin/openai-warmup/status", "GET");

export const startWarmup = () =>
  call("/api/v1/admin/openai-warmup/start", "POST");

export const stopWarmup = () =>
  call("/api/v1/admin/openai-warmup/stop", "POST");
