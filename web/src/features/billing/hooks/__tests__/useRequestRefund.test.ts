/** useRequestRefund 단위 테스트 — Story 3.6. */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";

const mockRequestRefund = vi.fn();

vi.mock("../../api", () => ({
  requestRefund: (paymentId: number, reason?: string) =>
    mockRequestRefund(paymentId, reason),
}));

import { useRequestRefund } from "../useRequestRefund";

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: qc }, children);
  return { wrapper, invalidateSpy };
}

describe("useRequestRefund", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("자동 환불 성공 시 invalidateQueries 호출", async () => {
    mockRequestRefund.mockResolvedValue({
      status: "refunded",
      amount_krw: 9900,
      refunded_at: "2026-04-29T12:00:00+00:00",
    });

    const { wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useRequestRefund(), { wrapper });

    result.current.mutate({ paymentId: 200, reason: "사용 안 함" });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockRequestRefund).toHaveBeenCalledWith(200, "사용 안 함");
    const invalidatedKeys = invalidateSpy.mock.calls.map(
      (c) => (c[0] as { queryKey: unknown[] }).queryKey
    );
    expect(invalidatedKeys).toContainEqual([
      "billing",
      "current-subscription",
    ]);
    expect(invalidatedKeys).toContainEqual(["session"]);
  });

  it("실패 시 invalidateQueries 미호출", async () => {
    mockRequestRefund.mockRejectedValue(new Error("boom"));

    const { wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useRequestRefund(), { wrapper });

    result.current.mutate({ paymentId: 200 });

    await waitFor(() => expect(result.current.isError).toBe(true));

    const invalidatedKeys = invalidateSpy.mock.calls.map(
      (c) => (c[0] as { queryKey: unknown[] }).queryKey
    );
    expect(invalidatedKeys).not.toContainEqual([
      "billing",
      "current-subscription",
    ]);
  });
});
