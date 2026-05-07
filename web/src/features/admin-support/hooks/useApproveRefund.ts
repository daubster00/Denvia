"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  approveRefund,
  type RefundActionResponse,
} from "@/features/admin-support/api/refunds";

interface ApprovePayload {
  queueId: number;
  note: string;
}

export function useApproveRefund() {
  const queryClient = useQueryClient();
  return useMutation<RefundActionResponse, Error, ApprovePayload>({
    mutationFn: ({ queueId, note }) => approveRefund(queueId, note),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "support", "refunds"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "support", "counts"] });
    },
  });
}
