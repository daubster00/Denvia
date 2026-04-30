"use client";

/** TopNav 미읽음 뱃지용 카운트 훅 — Story 4.5. */

import { useQuery } from "@tanstack/react-query";

import { useSessionStore } from "@/stores/session-store";
import { fetchUnreadCount } from "../api";

export function useUnreadCount() {
  const user = useSessionStore((s) => s.user);
  return useQuery({
    queryKey: ["me", "inbox", "unread-count"],
    queryFn: fetchUnreadCount,
    enabled: user !== null,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}
