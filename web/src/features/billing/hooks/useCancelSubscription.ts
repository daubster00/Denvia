"use client";

/** 구독 해지 mutation 훅 — Story 3.5. */

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { cancelSubscription } from "../api";

export function useCancelSubscription() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (reason: string) => cancelSubscription(reason),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["billing", "current-subscription"] });
      qc.invalidateQueries({ queryKey: ["session"] });
    },
  });
}
