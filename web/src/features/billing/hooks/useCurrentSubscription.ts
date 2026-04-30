"use client";

/** 현재 구독 상태 조회 훅 — Story 3.5. */

import { useQuery } from "@tanstack/react-query";

import { fetchCurrentSubscription } from "../api";

export function useCurrentSubscription(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ["billing", "current-subscription"],
    queryFn: fetchCurrentSubscription,
    staleTime: 30_000,
    enabled: options?.enabled ?? true,
    retry: 0,
  });
}
