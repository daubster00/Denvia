/**
 * 관리자 콘솔 전용 API 클라이언트.
 *
 * 일반 apiFetch와 분리한 이유:
 * - 401 발생 시 사용자 로그인 팝업이 아니라 /admin/login으로 리다이렉트해야 함
 * - 관리자 세션 store는 일반 session-store와 별개
 */

import { ApiError } from "@/types/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// admin /me 조회는 비로그인 시에도 호출되므로 리다이렉트 제외
const ADMIN_ME_PATH = "/api/v1/admin/auth/me";

async function handleAdminError(res: Response, path: string): Promise<never> {
  const traceId = res.headers.get("X-Trace-Id") ?? "";
  let body: Record<string, unknown> = {};
  try {
    body = await res.json();
  } catch {
    // JSON 파싱 실패 시 빈 객체 유지
  }

  const code = (body["code"] as string | undefined) ?? "UNKNOWN_ERROR";
  const message = (body["message"] as string | undefined) ?? res.statusText;

  if (res.status === 401 && path !== ADMIN_ME_PATH) {
    if (typeof window !== "undefined") {
      const { useAdminSessionStore } = await import(
        "@/stores/admin-session-store"
      );
      useAdminSessionStore.getState().clearAdmin();
      // 현재 위치가 관리자 페이지면 /admin/login으로 보냄
      if (window.location.pathname.startsWith("/admin")) {
        window.location.replace("/admin/login");
      }
    }
  }

  if (res.status === 429) {
    throw new ApiError({
      code: "RATE_LIMITED",
      message: "잠시 후 다시 시도해주세요.",
      trace_id: traceId,
    });
  }

  throw new ApiError({
    code,
    message,
    trace_id: traceId,
    details: body["details"] as Record<string, unknown> | undefined,
  });
}

async function adminApiFetch<T>(
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
    await handleAdminError(res, path);
  }

  if (res.status === 204 || res.headers.get("content-length") === "0") {
    return undefined as T;
  }

  return res.json() as Promise<T>;
}

export interface AdminSessionUser {
  user_id: number;
  email: string;
  role: string; // 항상 "admin"
}

export async function adminLogin(payload: {
  email: string;
  password: string;
}): Promise<AdminSessionUser> {
  return adminApiFetch<AdminSessionUser>("/api/v1/admin/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function adminLogout(): Promise<void> {
  return adminApiFetch<void>("/api/v1/admin/auth/logout", { method: "POST" });
}

export async function adminFetchMe(): Promise<AdminSessionUser> {
  return adminApiFetch<AdminSessionUser>("/api/v1/admin/auth/me");
}
