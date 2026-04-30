"use client";

/** 메인 진입 시 자동 노출 후보 팝업 조회 — Story 4.5. */

import { useQuery } from "@tanstack/react-query";

import { useSessionStore } from "@/stores/session-store";
import { fetchActivePopup } from "../api";

export function useActivePopup() {
  const user = useSessionStore((s) => s.user);
  return useQuery({
    queryKey: ["me", "popups", "active"],
    queryFn: fetchActivePopup,
    enabled: user !== null,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
    retry: 0,
  });
}
