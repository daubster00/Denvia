"use client";

/** 쪽지함 페이지네이션 조회 훅 — Story 4.5. */

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { fetchInbox } from "../api";
import type { InboxFilter } from "../types";

export function useInbox(page: number, perPage: number, filter: InboxFilter) {
  return useQuery({
    queryKey: ["me", "inbox", { page, perPage, filter }],
    queryFn: () => fetchInbox(page, perPage, filter),
    staleTime: 30_000,
    placeholderData: keepPreviousData,
    retry: 1,
  });
}
