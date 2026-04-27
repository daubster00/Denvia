"use client";

import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { logout } from "@/features/auth/api";
import { useSessionStore } from "@/stores/session-store";

/**
 * Story 2.7 — 로그아웃 훅.
 *
 * 흐름: POST /api/v1/auth/logout → useSessionStore.clearSession → react-query ['session'] invalidate → router.replace('/').
 * 서버 실패(5xx 등)에도 클라이언트 측 세션은 강제 정리한다 (try/finally) — 다음 보호 라우트 진입 시 401 인터셉터가 처리.
 *
 * components/ → features/auth/api 직접 import 금지 (architecture.md §1142-1175). TopNav는 본 훅을 통해서만 호출.
 */
export function useLogout() {
  const router = useRouter();
  const qc = useQueryClient();
  const clearSession = useSessionStore((s) => s.clearSession);

  return async function handleLogout() {
    try {
      await logout();
    } catch {
      // 서버 실패해도 클라이언트 세션은 정리 — finally 블록에서 처리
    } finally {
      clearSession();
      qc.invalidateQueries({ queryKey: ["session"] });
      router.replace("/");
    }
  };
}
