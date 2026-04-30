"use client";

/** 팝업 X/ESC 클릭 시 seen 처리 mutation — Story 4.5. */

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { markPopupSeen } from "../api";

export function usePopupSeen() {
  const qc = useQueryClient();
  return useMutation<void, Error, number>({
    mutationFn: (popupId) => markPopupSeen(popupId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["me", "popups", "active"] });
      qc.invalidateQueries({ queryKey: ["me", "inbox"] });
      qc.invalidateQueries({ queryKey: ["me", "inbox", "unread-count"] });
    },
  });
}
