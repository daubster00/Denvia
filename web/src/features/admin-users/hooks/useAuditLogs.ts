"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  fetchAuditLogs,
  type AuditLogListResponse,
  type FetchAuditLogsParams,
} from "@/features/admin-users/api/audit";

/**
 * Story 6.2 — 감사 로그 목록 useQuery 훅.
 * page 전환 시 빈 화면 깜빡임 방지를 위해 keepPreviousData 사용.
 */
export function useAuditLogs(params: FetchAuditLogsParams) {
  return useQuery<AuditLogListResponse>({
    queryKey: [
      "admin",
      "audit-logs",
      {
        action_in: params.action_in ? [...params.action_in].sort().join(",") : "",
        target_id: params.target_id ?? null,
        actor_filter: params.actor_filter ?? null,
        page: params.page ?? 1,
        per_page: params.per_page ?? 20,
      },
    ],
    queryFn: () => fetchAuditLogs(params),
    placeholderData: keepPreviousData,
    staleTime: 10_000,
    refetchOnWindowFocus: false,
  });
}
