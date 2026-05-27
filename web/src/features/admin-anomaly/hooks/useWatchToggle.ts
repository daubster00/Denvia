"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  addAnomalyWatch,
  removeAnomalyWatch,
  type WatchToggleResponse,
} from "@/features/admin-anomaly/api/anomaly";

interface AddArgs {
  anomalyId: number;
}
interface RemoveArgs {
  userId: number;
}

/**
 * 별 모양 버튼 — 주의 계정 등록 (이상 이벤트의 target_user 기준).
 */
export function useAddWatch() {
  const queryClient = useQueryClient();
  return useMutation<WatchToggleResponse, Error, AddArgs>({
    mutationFn: ({ anomalyId }) => addAnomalyWatch(anomalyId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "anomaly"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "anomaly", "watched"] });
    },
  });
}

/**
 * 별 모양 버튼 — 주의 계정 해제.
 */
export function useRemoveWatch() {
  const queryClient = useQueryClient();
  return useMutation<WatchToggleResponse, Error, RemoveArgs>({
    mutationFn: ({ userId }) => removeAnomalyWatch(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "anomaly"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "anomaly", "watched"] });
    },
  });
}
