"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  postInquiryReply,
  type InquiryReplyPayload,
  type InquiryReplyResponse,
} from "@/features/admin-support/api/inquiries";

export function usePostInquiryReply(inquiryId: number | null) {
  const queryClient = useQueryClient();
  return useMutation<InquiryReplyResponse, Error, InquiryReplyPayload>({
    mutationFn: (payload) => {
      if (inquiryId === null) {
        return Promise.reject(new Error("inquiryId is null"));
      }
      return postInquiryReply(inquiryId, payload);
    },
    onSuccess: ({ inquiry }) => {
      queryClient.setQueryData(
        ["admin", "support", "inquiry", inquiry.id],
        inquiry,
      );
      queryClient.invalidateQueries({ queryKey: ["admin", "support", "inquiries"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "support", "counts"] });
    },
  });
}
