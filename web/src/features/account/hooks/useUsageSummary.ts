"use client";

/** 마이페이지 통합 응답 조회 훅 — Story 4.3. */

import { useQuery } from "@tanstack/react-query";

import { fetchUsageSummary } from "../api";

export function useUsageSummary() {
  return useQuery({
    queryKey: ["me", "usage-summary"],
    queryFn: fetchUsageSummary,
    staleTime: 30_000,
    retry: 1,
  });
}
