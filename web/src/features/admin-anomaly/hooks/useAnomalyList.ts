"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  fetchAnomalyList,
  type AnomalyListResponse,
  type FetchAnomalyParams,
} from "@/features/admin-anomaly/api/anomaly";

/**
 * Story 6.5 — 이상 이벤트 목록 useQuery 훅.
 * - keepPreviousData 로 page 전환 시 깜빡임 방지.
 * - refetchInterval 60초 — 자동 탐지가 새로 INSERT 한 이벤트를 폴링.
 */
export function useAnomalyList(params: FetchAnomalyParams) {
  return useQuery<AnomalyListResponse>({
    queryKey: [
      "admin",
      "anomaly",
      "list",
      {
        type_in: params.type_in ?? null,
        status_in: params.status_in ?? null,
        target_user_id: params.target_user_id ?? null,
        from: params.from ?? null,
        to: params.to ?? null,
        page: params.page ?? 1,
        per_page: params.per_page ?? 20,
      },
    ],
    queryFn: () => fetchAnomalyList(params),
    placeholderData: keepPreviousData,
    staleTime: 30_000,
    refetchInterval: 60_000,
    refetchOnWindowFocus: false,
  });
}
