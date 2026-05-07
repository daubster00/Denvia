"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  fetchInquiries,
  type FetchInquiriesParams,
  type InquiryListResponse,
} from "@/features/admin-support/api/inquiries";

export function useInquiriesSearch(params: FetchInquiriesParams) {
  return useQuery<InquiryListResponse>({
    queryKey: [
      "admin",
      "support",
      "inquiries",
      {
        status: params.status ?? null,
        status_in: params.status_in ? [...params.status_in].sort() : null,
        q: params.q ?? null,
        from: params.from ?? null,
        to: params.to ?? null,
        page: params.page ?? 1,
        per_page: params.per_page ?? 50,
      },
    ],
    queryFn: () => fetchInquiries(params),
    placeholderData: keepPreviousData,
    staleTime: 10_000,
    refetchOnWindowFocus: false,
  });
}
