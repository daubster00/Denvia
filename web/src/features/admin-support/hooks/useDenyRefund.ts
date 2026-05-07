"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  denyRefund,
  type RefundActionResponse,
} from "@/features/admin-support/api/refunds";

interface DenyPayload {
  queueId: number;
  note: string;
}

export function useDenyRefund() {
  const queryClient = useQueryClient();
  return useMutation<RefundActionResponse, Error, DenyPayload>({
    mutationFn: ({ queueId, note }) => denyRefund(queueId, note),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "support", "refunds"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "support", "counts"] });
    },
  });
}
