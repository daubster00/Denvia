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
        page: params.page ?? 1,
        per_page: params.per_page ?? 20,
      },
    ],
    queryFn: () => fetchInquiries(params),
    placeholderData: keepPreviousData,
    staleTime: 10_000,
    refetchOnWindowFocus: false,
  });
}
