/** usePaymentHistory 단위 테스트 — Story 4.4. */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";

const mockFetchPaymentHistory = vi.fn();

vi.mock("../../api", () => ({
  fetchPaymentHistory: (...args: unknown[]) => mockFetchPaymentHistory(...args),
}));

import { usePaymentHistory } from "../usePaymentHistory";

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: qc }, children);
}

describe("usePaymentHistory", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("fetch 호출 + 응답 반환 (page=1, perPage=20)", async () => {
    const data = {
      items: [],
      page: 1,
      per_page: 20,
      total: 0,
    };
    mockFetchPaymentHistory.mockResolvedValue(data);

    const { result } = renderHook(() => usePaymentHistory(1, 20), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockFetchPaymentHistory).toHaveBeenCalledWith(1, 20);
    expect(result.current.data).toEqual(data);
  });

  it("queryKey가 page/perPage별로 분리된다", async () => {
    mockFetchPaymentHistory.mockResolvedValue({
      items: [],
      page: 2,
      per_page: 10,
      total: 0,
    });

    const { result } = renderHook(() => usePaymentHistory(2, 10), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    // page=2, perPage=10 호출 인자 정합
    expect(mockFetchPaymentHistory).toHaveBeenCalledWith(2, 10);
  });

  it("fetch 실패 시 isError=true (retry=1 후)", async () => {
    mockFetchPaymentHistory.mockRejectedValue(new Error("network"));

    const { result } = renderHook(() => usePaymentHistory(1, 20), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isError).toBe(true), {
      timeout: 2000,
    });
  });
});
