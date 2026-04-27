"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchQuota } from "@/features/qa/api/quota";

export function useQuota() {
  return useQuery({
    queryKey: ["me", "quota"],
    queryFn: fetchQuota,
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
}
