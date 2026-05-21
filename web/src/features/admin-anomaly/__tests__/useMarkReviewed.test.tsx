import { describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useMarkReviewed } from "../hooks/useMarkReviewed";

vi.mock("@/features/admin-anomaly/api/anomaly", async () => {
  const actual = await vi.importActual<
    typeof import("@/features/admin-anomaly/api/anomaly")
  >("@/features/admin-anomaly/api/anomaly");
  return {
    ...actual,
    markAnomalyReviewed: vi.fn(),
  };
});

import { markAnomalyReviewed } from "@/features/admin-anomaly/api/anomaly";

function makeWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return {
    client,
    Wrapper: ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    ),
  };
}

describe("useMarkReviewed", () => {
  it("invokes markAnomalyReviewed and invalidates list query on success", async () => {
    const fakeResult = {
      id: 1,
      type: "rapid_followup_questions" as const,
      target_user_id: 7,
      target_user_email_masked: null,
      ip: null,
      ua: null,
      details: {},
      status: "reviewed" as const,
      reviewed_by_admin_id: 99,
      reviewed_at: "2026-05-01T03:00:00Z",
      created_at: "2026-05-01T03:00:00Z",
    };
    (markAnomalyReviewed as ReturnType<typeof vi.fn>).mockResolvedValue(
      fakeResult,
    );

    const { client, Wrapper } = makeWrapper();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");

    const { result } = renderHook(() => useMarkReviewed(), { wrapper: Wrapper });

    await act(async () => {
      await result.current.mutateAsync(1);
    });

    await waitFor(() => {
      expect(markAnomalyReviewed).toHaveBeenCalledWith(1);
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["admin", "anomaly"],
    });
  });
});
