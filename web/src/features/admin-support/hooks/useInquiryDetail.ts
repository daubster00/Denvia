"use client";

import { useQuery } from "@tanstack/react-query";
import {
  fetchInquiryDetail,
  type InquiryDetailResponse,
} from "@/features/admin-support/api/inquiries";

export function useInquiryDetail(inquiryId: number | null) {
  return useQuery<InquiryDetailResponse>({
    queryKey: ["admin", "support", "inquiry", inquiryId],
    queryFn: () => fetchInquiryDetail(inquiryId as number),
    enabled: inquiryId !== null,
    staleTime: 10_000,
    refetchOnWindowFocus: false,
  });
}
