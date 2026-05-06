"use client";

import { useQuery } from "@tanstack/react-query";
import {
  fetchUserDetail,
  type UserDetailResponse,
} from "@/features/admin-users/api/users";

/**
 * Story 6.1 — 사용자 상세 useQuery 훅.
 * Drawer가 열리는 시점(`enabled=true`)에만 fetch한다.
 */
export function useUserDetail(userId: number | null) {
  return useQuery<UserDetailResponse>({
    queryKey: ["admin", "users", "detail", userId],
    queryFn: () => fetchUserDetail(userId as number),
    enabled: userId !== null,
    staleTime: 10_000,
    refetchOnWindowFocus: false,
  });
}
