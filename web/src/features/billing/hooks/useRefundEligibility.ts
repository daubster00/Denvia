"use client";

/** 청약철회 가능 여부 조회 훅 — Story 3.6 v1.1 AC1. */

import { useQuery } from "@tanstack/react-query";

import { checkRefundEligibility } from "../api";

export function useRefundEligibility(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ["billing", "refund-eligibility"],
    queryFn: checkRefundEligibility,
    enabled: options?.enabled ?? true,
    staleTime: 30_000,
    retry: 0,
    refetchOnWindowFocus: false,
  });
}
