"use client";

/** 청약철회(즉시 해지 + 전액 환불) mutation 훅 — Story 3.6 v1.1 AC2~6. */

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { cancelSubscriptionWithRefund } from "../api";

export function useCancelWithRefund() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => cancelSubscriptionWithRefund(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["billing", "current-subscription"] });
      qc.invalidateQueries({ queryKey: ["billing", "refund-eligibility"] });
      qc.invalidateQueries({ queryKey: ["me", "payments"] });
      qc.invalidateQueries({ queryKey: ["session"] });
      qc.invalidateQueries({ queryKey: ["me", "usage-summary"] });
    },
  });
}
