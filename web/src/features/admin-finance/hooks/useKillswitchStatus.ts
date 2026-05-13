"use client";

// Story 9.2 — Admin kill-switch status query + SSE invalidate.

import { useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchKillswitchStatus, type KillswitchStatusResponse } from "../api/killswitch";
import { useAdminEventsStore } from "@/stores/admin-events-store";

export const KILLSWITCH_STATUS_QUERY_KEY = ["admin", "killswitch", "status"] as const;

export function useKillswitchStatus() {
  const qc = useQueryClient();
  const killswitchStatus = useAdminEventsStore((s) => s.killswitchStatus);

  const query = useQuery<KillswitchStatusResponse>({
    queryKey: KILLSWITCH_STATUS_QUERY_KEY,
    queryFn: fetchKillswitchStatus,
    staleTime: 15_000,
  });

  // SSE killswitch_status 이벤트 발생 시 즉시 재조회.
  useEffect(() => {
    if (killswitchStatus !== null) {
      qc.invalidateQueries({ queryKey: KILLSWITCH_STATUS_QUERY_KEY });
    }
  }, [killswitchStatus, qc]);

  return query;
}
