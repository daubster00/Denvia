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

  // 단일 세션(later wins) — 다른 곳에서 같은 계정으로 로그인되어 이 세션이 무효화된 케이스.
  // /api/v1/me 호출의 결과로 잡혀도 모달을 띄워야 하므로 ME_PATH 예외에 포함시키지 않는다.
  if (res.status === 401 && code === "AUTH_SESSION_SUPERSEDED") {
    if (typeof window !== "undefined") {
      const { useSessionStore } = await import("@/stores/session-store");
      useSessionStore.getState().clearSession();
      // 이미 /?login=superseded 위에 있으면 재진입을 막아 무한 모달을 피한다.
      const url = new URL(window.location.href);
      if (url.searchParams.get("login") !== "superseded") {
        window.location.replace("/?login=superseded");
      }
      throw new ApiError({ code, message, trace_id: traceId });
    }
  }

  if (res.status === 401 && path !== ME_PATH) {
    // 401 감지: 세션 클리어 + 메인(/)으로 이동 후 로그인 팝업 자동 오픈.
    // 이미 메인이면 페이지 이동 없이 팝업만 띄움. /admin/* 경로는 이 핸들러를 타지 않음(별도 admin-auth/api.ts).
    if (typeof window !== "undefined") {
      const { useSessionStore } = await import("@/stores/session-store");
      useSessionStore.getState().clearSession();
      const onHome = window.location.pathname === "/";
      if (!onHome) {
        // /?login=required 로 보내면 SessionBootstrap 마운트 후 OAuthErrorBanner 영역의 쿼리스트링은
        // 그대로 두고, 아래 openPopup이 페이지 이동 다음 tick에서 팝업을 띄운다.
        window.location.replace("/?login=required");
        return Promise.reject(
          new ApiError({ code: "AUTH_SESSION_EXPIRED", message: "세션이 만료되었습니다. 다시 로그인해주세요.", trace_id: traceId })
        );
      }
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
