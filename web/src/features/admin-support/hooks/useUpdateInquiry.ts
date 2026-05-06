"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  updateInquiry,
  type InquiryDetailResponse,
  type InquiryUpdatePayload,
} from "@/features/admin-support/api/inquiries";

export function useUpdateInquiry(inquiryId: number | null) {
  const queryClient = useQueryClient();
  return useMutation<InquiryDetailResponse, Error, InquiryUpdatePayload>({
    mutationFn: (payload) => {
      if (inquiryId === null) {
        return Promise.reject(new Error("inquiryId is null"));
      }
      return updateInquiry(inquiryId, payload);
    },
    onSuccess: (data) => {
      queryClient.setQueryData(
        ["admin", "support", "inquiry", data.id],
        data,
      );
      queryClient.invalidateQueries({
        queryKey: ["admin", "support", "inquiries"],
      });
    },
  });
}
