/** useUnreadCount/useActivePopup enabled 가드 테스트 — Story 4.5. */

import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { useUnreadCount } from "../hooks/useUnreadCount";
import { useActivePopup } from "../hooks/useActivePopup";
import { useSessionStore } from "@/stores/session-store";

vi.mock("../api", () => ({
  fetchUnreadCount: vi.fn(),
  fetchActivePopup: vi.fn(),
}));

const { fetchUnreadCount, fetchActivePopup } = await import("../api");

function makeWrapper() {
  return function wrapper({ children }: { children: ReactNode }) {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

beforeEach(() => {
  vi.mocked(fetchUnreadCount).mockReset();
  vi.mocked(fetchActivePopup).mockReset();
  useSessionStore.setState({ user: null });
});

describe("useUnreadCount — enabled 가드", () => {
  it("user=null → fetch 호출 안 함", async () => {
    useSessionStore.setState({ user: null });
    vi.mocked(fetchUnreadCount).mockResolvedValue({ unread_count: 5 });

    renderHook(() => useUnreadCount(), { wrapper: makeWrapper() });
    await new Promise((r) => setTimeout(r, 10));
    expect(fetchUnreadCount).not.toHaveBeenCalled();
  });

  it("user!=null → fetch 호출 + 응답 노출", async () => {
    useSessionStore.setState({
      user: {
        user_id: 1,
        email: "u@e.com",
        role: "user",
        subscription_status: "free",
        segment: null,
        years_of_experience: null,
        must_reset_password: false,
      },
    });
    vi.mocked(fetchUnreadCount).mockResolvedValue({ unread_count: 3 });

    const { result } = renderHook(() => useUnreadCount(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.unread_count).toBe(3);
  });
});

describe("useActivePopup — enabled 가드", () => {
  it("user=null → fetch 호출 안 함", async () => {
    useSessionStore.setState({ user: null });
    vi.mocked(fetchActivePopup).mockResolvedValue(null);

    renderHook(() => useActivePopup(), { wrapper: makeWrapper() });
    await new Promise((r) => setTimeout(r, 10));
    expect(fetchActivePopup).not.toHaveBeenCalled();
  });
});
