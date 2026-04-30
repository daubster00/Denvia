"use client";

/** 환불 요청 mutation 훅 — Story 3.6. */

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { requestRefund } from "../api";
import type { RefundResult } from "../types";

export function useRequestRefund() {
  const qc = useQueryClient();
  return useMutation<
    RefundResult,
    Error,
    { paymentId: number; reason?: string }
  >({
    mutationFn: ({ paymentId, reason }) => requestRefund(paymentId, reason),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["billing", "current-subscription"] });
      qc.invalidateQueries({ queryKey: ["session"] });
    },
  });
}
