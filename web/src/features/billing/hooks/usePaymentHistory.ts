"use client";

/** 결제 내역 페이지네이션 조회 훅 — Story 4.4. */

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { fetchPaymentHistory } from "../api";

export function usePaymentHistory(page: number, perPage: number) {
  return useQuery({
    queryKey: ["me", "payments", { page, perPage }],
    queryFn: () => fetchPaymentHistory(page, perPage),
    staleTime: 30_000,
    placeholderData: keepPreviousData,
    retry: 1,
  });
}
