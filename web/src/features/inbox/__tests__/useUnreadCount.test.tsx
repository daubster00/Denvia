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

// #106: 라우트 변경 시 refetch 검증을 위해 usePathname 을 제어 가능하게 모킹.
const mockPathname = vi.fn<() => string | null>(() => "/");
vi.mock("next/navigation", () => ({
  usePathname: () => mockPathname(),
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
  mockPathname.mockReturnValue("/");
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

  it("#106: 페이지 전환(pathname 변경) 시 미읽음 개수를 다시 조회한다", async () => {
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
    vi.mocked(fetchUnreadCount)
      .mockResolvedValueOnce({ unread_count: 0 })
      .mockResolvedValue({ unread_count: 1 });

    const { result, rerender } = renderHook(() => useUnreadCount(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(fetchUnreadCount).toHaveBeenCalledTimes(1);
    expect(result.current.data?.unread_count).toBe(0);

    // 다른 페이지로 이동 → refetch 트리거 → 새 카운트(1) 반영.
    mockPathname.mockReturnValue("/my");
    rerender();
    await waitFor(() => expect(result.current.data?.unread_count).toBe(1));
    expect(fetchUnreadCount).toHaveBeenCalledTimes(2);
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
