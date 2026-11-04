"use client";

import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { logout } from "@/features/auth/api";
import { resetClientSession } from "@/features/auth/lib/session-reset";

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

  return async function handleLogout() {
    try {
      await logout();
    } catch {
      // 서버 실패해도 클라이언트 세션은 정리 — finally 블록에서 처리
    } finally {
      // 검수 P0-4 / 재수정 P0-2 — 로그인 세션과 QA 대화를 **함께** 비운다.
      // 서버 실패로 강제 로그아웃이 되는 경우까지 포함해야 한다. 안 비우면 같은 탭의
      // 다음 사용자가 이전 사용자의 대화를 그대로 이어받아 질문하게 된다.
      // 정리 지점은 session-reset.ts 한 곳으로 모았다(한 길만 빠뜨리는 실수 방지).
      resetClientSession("logout");
      qc.invalidateQueries({ queryKey: ["session"] });
      router.replace("/");
    }
  };
}
