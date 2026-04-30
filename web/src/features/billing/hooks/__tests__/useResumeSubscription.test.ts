/** useResumeSubscription 단위 테스트 — Story 3.5. */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";

const mockResumeSubscription = vi.fn();

vi.mock("../../api", () => ({
  resumeSubscription: () => mockResumeSubscription(),
}));

import { useResumeSubscription } from "../useResumeSubscription";

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: qc }, children);
  return { wrapper, invalidateSpy };
}

describe("useResumeSubscription", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("성공 시 invalidateQueries(['billing','current-subscription']) + ['session'] 호출", async () => {
    mockResumeSubscription.mockResolvedValue({
      status: "active",
      next_charge_at: "2026-05-29T00:00:00+00:00",
    });

    const { wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useResumeSubscription(), { wrapper });

    result.current.mutate();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockResumeSubscription).toHaveBeenCalledOnce();
    const invalidatedKeys = invalidateSpy.mock.calls.map(
      (c) => (c[0] as { queryKey: unknown[] }).queryKey
    );
    expect(invalidatedKeys).toContainEqual(["billing", "current-subscription"]);
    expect(invalidatedKeys).toContainEqual(["session"]);
  });

  it("실패 시 invalidateQueries 미호출", async () => {
    mockResumeSubscription.mockRejectedValue(new Error("boom"));

    const { wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useResumeSubscription(), { wrapper });

    result.current.mutate();

    await waitFor(() => expect(result.current.isError).toBe(true));

    const invalidatedKeys = invalidateSpy.mock.calls.map(
      (c) => (c[0] as { queryKey: unknown[] }).queryKey
    );
    expect(invalidatedKeys).not.toContainEqual(["billing", "current-subscription"]);
  });
});
