"use client";

/** 구독 플랜 조회 훅 — Story 3.1. */

import { useQuery } from "@tanstack/react-query";
import { fetchBillingPlans } from "../api";

export function useBillingPlans(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ["billing", "plans"],
    queryFn: fetchBillingPlans,
    staleTime: 5 * 60_000, // 5분 — 플랜 가격은 자주 바뀌지 않음
    enabled: options?.enabled ?? true,
  });
}
