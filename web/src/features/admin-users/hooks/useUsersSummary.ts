"use client";

import { useQuery } from "@tanstack/react-query";
import {
  fetchUsersSummary,
  type UserSummaryResponse,
} from "@/features/admin-users/api/users";

/**
 * 고객관리 상단 가입자 수 배지 — 검색·필터와 무관한 절대 가입자 수.
 * 목록 검색(useUsersSearch)과 별개 쿼리라 검색·필터를 바꿔도 배지 숫자는 흔들리지 않는다.
 */
export function useUsersSummary() {
  return useQuery<UserSummaryResponse>({
    queryKey: ["admin", "users", "summary"],
    queryFn: () => fetchUsersSummary(),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });
}
