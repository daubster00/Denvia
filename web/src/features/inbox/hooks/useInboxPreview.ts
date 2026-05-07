"use client";

/** 쪽지함 미리보기 드롭다운용 데이터 훅 — Story 7.1.
 *
 * 서버가 동시 노출 최대 개수를 강제하므로 클라이언트는 limit를 보내지 않는다.
 * 로그인 상태에서만 활성화되며, 새 쪽지가 도착하면 inbox/unread-count invalidation에
 * 맞춰 자동으로 리프레시된다.
 */

import { useQuery } from "@tanstack/react-query";

import { useSessionStore } from "@/stores/session-store";
import { fetchInboxPreview } from "../api";

export function useInboxPreview() {
  const user = useSessionStore((s) => s.user);
  return useQuery({
    queryKey: ["me", "inbox", "preview"],
    queryFn: fetchInboxPreview,
    enabled: user !== null,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}
