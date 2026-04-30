/** useBillingPlans 훅 단위 테스트 — Story 3.1. */

import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement } from "react";
import type { BillingPlansResponse } from "../types";

// fetchBillingPlans mock
vi.mock("../api", () => ({
  fetchBillingPlans: vi.fn(),
}));

import { fetchBillingPlans } from "../api";
import { useBillingPlans } from "../hooks/useBillingPlans";

const mockFetch = fetchBillingPlans as ReturnType<typeof vi.fn>;

function makeWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client }, children);
}

afterEach(() => {
  vi.clearAllMocks();
});

const mockPlansData: BillingPlansResponse = {
  plans: [
    {
      tier: "free",
      name: "Basic",
      price_krw: 0,
      period: null,
      features: ["하루 3회 Q&A"],
      cta_label: "현재 이용 중",
      is_recommended: false,
    },
    {
      tier: "pro",
      name: "Pro",
      price_krw: 9900,
      period: "/ 월",
      features: ["무제한 Q&A"],
      cta_label: "Pro 시작하기",
      is_recommended: true,
    },
  ],
};

describe("useBillingPlans", () => {
  it("성공 시 plans 데이터를 반환한다", async () => {
    mockFetch.mockResolvedValueOnce(mockPlansData);
    const wrapper = makeWrapper();
    const { result } = renderHook(() => useBillingPlans(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.plans).toHaveLength(2);
  });

  it("초기에는 isLoading=true 상태다", () => {
    mockFetch.mockReturnValue(new Promise(() => undefined)); // never resolves
    const wrapper = makeWrapper();
    const { result } = renderHook(() => useBillingPlans(), { wrapper });

    expect(result.current.isLoading).toBe(true);
  });

  it("API 오류 시 isError=true가 된다", async () => {
    mockFetch.mockRejectedValueOnce(new Error("API 오류"));
    const wrapper = makeWrapper();
    const { result } = renderHook(() => useBillingPlans(), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });

  it("queryKey가 ['billing', 'plans']다", async () => {
    mockFetch.mockResolvedValueOnce(mockPlansData);
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const wrapper = ({ children }: { children: React.ReactNode }) =>
      createElement(QueryClientProvider, { client }, children);

    renderHook(() => useBillingPlans(), { wrapper });
    await waitFor(() =>
      expect(client.getQueryState(["billing", "plans"])?.status).toBeDefined()
    );
  });

  it("fetchBillingPlans API 함수가 정확히 1번 호출된다", async () => {
    mockFetch.mockResolvedValueOnce(mockPlansData);
    const wrapper = makeWrapper();
    renderHook(() => useBillingPlans(), { wrapper });

    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(1));
  });
});
