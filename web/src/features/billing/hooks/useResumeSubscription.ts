"use client";

/** 구독 해지 철회 mutation 훅 — Story 3.5. */

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { resumeSubscription } from "../api";

export function useResumeSubscription() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => resumeSubscription(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["billing", "current-subscription"] });
      qc.invalidateQueries({ queryKey: ["session"] });
    },
  });
}
