"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  fetchRefundQueue,
  type FetchRefundsParams,
  type RefundQueueListResponse,
} from "@/features/admin-support/api/refunds";

export function useRefundQueue(params: FetchRefundsParams) {
  return useQuery<RefundQueueListResponse>({
    queryKey: [
      "admin",
      "support",
      "refunds",
      {
        status: params.status ?? "pending",
        from: params.from ?? null,
        to: params.to ?? null,
        q: params.q ?? null,
        page: params.page ?? 1,
        per_page: params.per_page ?? 50,
      },
    ],
    queryFn: () => fetchRefundQueue(params),
    placeholderData: keepPreviousData,
    staleTime: 10_000,
    refetchOnWindowFocus: false,
  });
}
