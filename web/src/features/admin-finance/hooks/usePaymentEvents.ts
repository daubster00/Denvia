"use client";

import { useQuery } from "@tanstack/react-query";
import {
  fetchPaymentEvents,
  type FetchPaymentEventsParams,
  type PaymentEventListResponse,
} from "@/features/admin-finance/api/payments";

export function usePaymentEvents(params: FetchPaymentEventsParams) {
  return useQuery<PaymentEventListResponse>({
    queryKey: ["admin", "finance", "payment-events", params] as const,
    queryFn: () => fetchPaymentEvents(params),
    placeholderData: (prev) => prev,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });
}
