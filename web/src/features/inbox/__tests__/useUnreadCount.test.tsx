/** useUnreadCount / useActivePopups enabled 가드 — Story 4.5 + 7.2 v2. */

import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { useUnreadCount } from "../hooks/useUnreadCount";
import { useActivePopups } from "../hooks/useActivePopup";
import { useSessionStore } from "@/stores/session-store";

vi.mock("../api", () => ({
  fetchUnreadCount: vi.fn(),
  fetchActivePopups: vi.fn(),
}));

const { fetchUnreadCount, fetchActivePopups } = await import("../api");

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
  vi.mocked(fetchActivePopups).mockReset();
  useSessionStore.setState({ user: null });
  // useActivePopups가 마운트 직후 detectDevice() → matchMedia를 호출하므로 jsdom에 stub.
  window.matchMedia = vi.fn().mockImplementation((q: string) => ({
    matches: false,
    media: q,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }));
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
        is_social: false,
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

describe("useActivePopups — enabled 가드", () => {
  it("user=null → fetch 호출 안 함", async () => {
    useSessionStore.setState({ user: null });
    vi.mocked(fetchActivePopups).mockResolvedValue([]);

    renderHook(() => useActivePopups(), { wrapper: makeWrapper() });
    await new Promise((r) => setTimeout(r, 10));
    expect(fetchActivePopups).not.toHaveBeenCalled();
  });
});
