"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  fetchUsers,
  type FetchUsersParams,
  type UserSearchListResponse,
} from "@/features/admin-users/api/users";

/**
 * Story 6.1 — 사용자 통합 검색 useQuery 훅.
 * page 전환 시 빈 화면 깜빡임 방지를 위해 keepPreviousData 사용.
 */
export function useUsersSearch(params: FetchUsersParams) {
  return useQuery<UserSearchListResponse>({
    queryKey: [
      "admin",
      "users",
      {
        q: params.q ?? null,
        segment: params.segment ?? null,
        subscription_status: params.subscription_status ?? null,
        blocked: params.blocked ?? null,
        page: params.page ?? 1,
        per_page: params.per_page ?? 20,
      },
    ],
    queryFn: () => fetchUsers(params),
    placeholderData: keepPreviousData,
    staleTime: 10_000,
    refetchOnWindowFocus: false,
  });
}
