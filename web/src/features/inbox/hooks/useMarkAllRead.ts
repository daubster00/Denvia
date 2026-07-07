"use client";

/** 쪽지 전체읽음 mutation — #118.

 * 성공 시 목록·미읽음 카운트·아이콘 밑 미리보기를 모두 invalidate해
 * 뱃지와 미리보기가 즉시 사라지게 한다.
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { markAllInboxRead } from "../api";
import type { InboxReadAllResponse } from "../types";

export function useMarkAllRead() {
  const qc = useQueryClient();
  return useMutation<InboxReadAllResponse, Error, void>({
    mutationFn: () => markAllInboxRead(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["me", "inbox"] });
      qc.invalidateQueries({ queryKey: ["me", "inbox", "unread-count"] });
      qc.invalidateQueries({ queryKey: ["me", "inbox", "preview"] });
    },
  });
}
