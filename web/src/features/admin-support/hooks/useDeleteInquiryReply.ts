"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  deleteInquiryReply,
  type InquiryDetailResponse,
} from "@/features/admin-support/api/inquiries";

export function useDeleteInquiryReply(inquiryId: number | null) {
  const queryClient = useQueryClient();
  return useMutation<InquiryDetailResponse, Error, number>({
    mutationFn: (replyId) => {
      if (inquiryId === null) {
        return Promise.reject(new Error("inquiryId is null"));
      }
      return deleteInquiryReply(inquiryId, replyId);
    },
    onSuccess: (inquiry) => {
      queryClient.setQueryData(
        ["admin", "support", "inquiry", inquiry.id],
        inquiry,
      );
      queryClient.invalidateQueries({
        queryKey: ["admin", "support", "inquiries"],
      });
    },
  });
}
