"use client";

/** 쪽지 읽음 처리 mutation — Story 4.5. */

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { markInboxRead } from "../api";

export function useMarkRead() {
  const qc = useQueryClient();
  return useMutation<void, Error, number>({
    mutationFn: (messageId) => markInboxRead(messageId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["me", "inbox"] });
      qc.invalidateQueries({ queryKey: ["me", "inbox", "unread-count"] });
    },
  });
}
