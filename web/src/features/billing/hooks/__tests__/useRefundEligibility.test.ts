/** useRefundEligibility 단위 테스트 — Story 3.6 v1.1. */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";

const mockCheckRefundEligibility = vi.fn();

vi.mock("../../api", () => ({
  checkRefundEligibility: () => mockCheckRefundEligibility(),
}));

import { useRefundEligibility } from "../useRefundEligibility";

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: qc }, children);
}

describe("useRefundEligibility", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("enabled=true (default) → API 호출 후 데이터 반환", async () => {
    mockCheckRefundEligibility.mockResolvedValue({
      eligible: true,
      payment_id: 1,
      amount_krw: 9900,
      charged_at: "2026-05-10T05:23:11+00:00",
      days_since_charge: 3,
      qa_count_during_period: 0,
      reason_code: "ok",
    });

    const { result } = renderHook(() => useRefundEligibility(), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockCheckRefundEligibility).toHaveBeenCalledOnce();
    expect(result.current.data?.eligible).toBe(true);
  });

  it("enabled=false → API 미호출", async () => {
    const { result } = renderHook(
      () => useRefundEligibility({ enabled: false }),
      { wrapper: makeWrapper() }
    );

    // useQuery는 enabled=false면 idle 상태 유지
    expect(result.current.fetchStatus).toBe("idle");
    expect(mockCheckRefundEligibility).not.toHaveBeenCalled();
  });
});
