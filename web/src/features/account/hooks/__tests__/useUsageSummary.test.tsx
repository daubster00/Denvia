import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { useUsageSummary } from "../useUsageSummary";

vi.mock("../../api", () => ({
  fetchUsageSummary: vi.fn(),
}));

const { fetchUsageSummary } = await import("../../api");

function makeWrapper() {
  return function wrapper({ children }: { children: ReactNode }) {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

beforeEach(() => {
  vi.mocked(fetchUsageSummary).mockReset();
});

describe("useUsageSummary — Story 4.3", () => {
  it("성공 시 응답을 그대로 노출", async () => {
    const payload = {
      month_question_count: 7,
      daily_used: 1,
      daily_limit: 10,
      daily_remaining: 9,
      daily_reset_at: "2026-05-01T00:00:00+09:00",
      subscription_status: "free" as const,
      segment: "doctor" as const,
      years_of_experience: 5,
      show_subscribe_button: true,
    };
    vi.mocked(fetchUsageSummary).mockResolvedValue(payload);

    const { result } = renderHook(() => useUsageSummary(), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(payload);
  });

  it("실패 시 isError=true (retry: 1 — 1회 재시도 후 실패)", async () => {
    vi.mocked(fetchUsageSummary).mockRejectedValue(new Error("boom"));

    const { result } = renderHook(() => useUsageSummary(), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isError).toBe(true), {
      timeout: 3000,
    });
    expect(result.current.data).toBeUndefined();
  });
});
