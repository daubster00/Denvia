/** useCancelWithRefund 단위 테스트 — Story 3.6 v1.1. */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";

const mockCancelSubscriptionWithRefund = vi.fn();

vi.mock("../../api", () => ({
  cancelSubscriptionWithRefund: () => mockCancelSubscriptionWithRefund(),
}));

import { useCancelWithRefund } from "../useCancelWithRefund";

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: qc }, children);
  return { wrapper, invalidateSpy };
}

describe("useCancelWithRefund", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("성공 시 관련 캐시 invalidate 호출", async () => {
    mockCancelSubscriptionWithRefund.mockResolvedValue({
      status: "refunded",
      refund_kind: "cooling_off",
      amount_krw: 9900,
      refunded_at: "2026-05-13T10:00:00+00:00",
      subscription_status: "canceled",
    });

    const { wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useCancelWithRefund(), { wrapper });

    result.current.mutate();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockCancelSubscriptionWithRefund).toHaveBeenCalledOnce();
    const invalidatedKeys = invalidateSpy.mock.calls.map(
      (c) => (c[0] as { queryKey: unknown[] }).queryKey
    );
    expect(invalidatedKeys).toContainEqual(["billing", "current-subscription"]);
    expect(invalidatedKeys).toContainEqual(["billing", "refund-eligibility"]);
    expect(invalidatedKeys).toContainEqual(["me", "payments"]);
    expect(invalidatedKeys).toContainEqual(["session"]);
    expect(invalidatedKeys).toContainEqual(["me", "usage-summary"]);
  });

  it("실패 시 invalidateQueries 미호출", async () => {
    mockCancelSubscriptionWithRefund.mockRejectedValue(new Error("boom"));

    const { wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useCancelWithRefund(), { wrapper });

    result.current.mutate();

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(invalidateSpy).not.toHaveBeenCalled();
  });
});
