"use client";

import { useQuery } from "@tanstack/react-query";
import {
  fetchSupportCounts,
  type SupportCountsResponse,
} from "@/features/admin-support/api/inquiries";

export function useSupportCounts() {
  return useQuery<SupportCountsResponse>({
    queryKey: ["admin", "support", "counts"],
    queryFn: fetchSupportCounts,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });
}
