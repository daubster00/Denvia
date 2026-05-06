"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  markAnomalyReviewed,
  type AnomalyEventItem,
} from "@/features/admin-anomaly/api/anomaly";

/**
 * Story 6.5 — 이상 이벤트 검토 완료 mutation.
 * 성공 시 ['admin','anomaly'] 쿼리 invalidate.
 */
export function useMarkReviewed() {
  const queryClient = useQueryClient();
  return useMutation<AnomalyEventItem, Error, number>({
    mutationFn: (anomalyId) => markAnomalyReviewed(anomalyId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "anomaly"] });
    },
  });
}
