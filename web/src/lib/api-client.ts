/**
 * API 클라이언트 — credentials:include, 401/429 인터셉터, ApiError 정규화.
 * TraceMiddleware가 주입한 X-Trace-Id를 에러 객체에 부착.
 */

import { ApiError } from "@/types/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// /api/v1/me 경로는 401 인터셉터 제외 (비로그인 랜딩 정상 경로)
const ME_PATH = "/api/v1/me";

async function handleErrorResponse(res: Response, path: string): Promise<never> {
  const traceId = res.headers.get("X-Trace-Id") ?? "";
  let body: Record<string, unknown> = {};
  try {
    body = await res.json();
  } catch {
    // JSON 파싱 실패 시 빈 객체 유지
  }

  const code = (body["code"] as string | undefined) ?? "UNKNOWN_ERROR";
  const message = (body["message"] as string | undefined) ?? res.statusText;

  if (res.status === 401 && path !== ME_PATH) {
    // 401 감지: 세션 클리어 + 로그인 팝업 오픈 (동적 import로 서버 컴포넌트 안전 처리)
    if (typeof window !== "undefined") {
      const { useSessionStore } = await import("@/stores/session-store");
      useSessionStore.getState().clearSession();
      useSessionStore.getState().openPopup("email");
    }
  }

  if (res.status === 429) {
    // 429: RATE_LIMITED 에러로 throw (프론트에서 Toast 처리)
    throw new ApiError({ code: "RATE_LIMITED", message: "잠시 후 다시 시도해주세요.", trace_id: traceId });
  }

  throw new ApiError({ code, message, trace_id: traceId, details: body["details"] as Record<string, unknown> | undefined });
}

export async function apiFetch<T>(
  path: string,
  init?: RequestInit
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    credentials: "include",
    ...init,
  });

  if (!res.ok) {
    await handleErrorResponse(res, path);
  }

  // 204 No Content 또는 빈 body는 undefined로 반환 (void 응답 지원)
  if (res.status === 204 || res.headers.get("content-length") === "0") {
    return undefined as T;
  }

  return res.json() as Promise<T>;
}
