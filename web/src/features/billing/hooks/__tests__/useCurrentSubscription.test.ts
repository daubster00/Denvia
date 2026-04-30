/** useCurrentSubscription 단위 테스트 — Story 3.5. */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";

const mockFetchCurrentSubscription = vi.fn();

vi.mock("../../api", () => ({
  fetchCurrentSubscription: () => mockFetchCurrentSubscription(),
}));

import { useCurrentSubscription } from "../useCurrentSubscription";

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: qc }, children);
}

describe("useCurrentSubscription", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("enabled=false → fetch 미호출", async () => {
    renderHook(() => useCurrentSubscription({ enabled: false }), {
      wrapper: makeWrapper(),
    });

    await new Promise((r) => setTimeout(r, 20));
    expect(mockFetchCurrentSubscription).not.toHaveBeenCalled();
  });

  it("enabled=true (default) → fetch 호출, 응답 반환", async () => {
    const data = {
      status: "active",
      started_at: "2026-04-01T00:00:00+00:00",
      current_period_end: "2026-05-01T00:00:00+00:00",
      next_charge_at: "2026-05-01T00:00:00+00:00",
      canceled_at: null,
      cancel_reason: null,
    };
    mockFetchCurrentSubscription.mockResolvedValue(data);

    const { result } = renderHook(() => useCurrentSubscription(), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(data);
  });

  it("응답 status='cancel_pending' 도 정상 통과", async () => {
    mockFetchCurrentSubscription.mockResolvedValue({
      status: "cancel_pending",
      started_at: "2026-04-01T00:00:00+00:00",
      current_period_end: "2026-05-01T00:00:00+00:00",
      next_charge_at: "2026-05-01T00:00:00+00:00",
      canceled_at: "2026-04-15T00:00:00+00:00",
      cancel_reason: "test",
    });

    const { result } = renderHook(() => useCurrentSubscription(), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.status).toBe("cancel_pending");
  });

  it("응답 status='none' 통과", async () => {
    mockFetchCurrentSubscription.mockResolvedValue({
      status: "none",
      started_at: null,
      current_period_end: null,
      next_charge_at: null,
      canceled_at: null,
      cancel_reason: null,
    });

    const { result } = renderHook(() => useCurrentSubscription(), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.status).toBe("none");
  });
});
