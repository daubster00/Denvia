"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  editInquiryReply,
  type InquiryDetailResponse,
  type InquiryReplyEditPayload,
} from "@/features/admin-support/api/inquiries";

interface EditVariables {
  replyId: number;
  payload: InquiryReplyEditPayload;
}

export function useEditInquiryReply(inquiryId: number | null) {
  const queryClient = useQueryClient();
  return useMutation<InquiryDetailResponse, Error, EditVariables>({
    mutationFn: ({ replyId, payload }) => {
      if (inquiryId === null) {
        return Promise.reject(new Error("inquiryId is null"));
      }
      return editInquiryReply(inquiryId, replyId, payload);
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
