/** /inbox 페이지 단위 테스트 — Story 4.5. */

import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { useSessionStore } from "@/stores/session-store";

const mockReplace = vi.fn();
const mockPush = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: mockReplace,
    push: mockPush,
  }),
  usePathname: () => "/inbox",
}));

vi.mock("@/components/layout/TopNav", () => ({
  TopNav: () => <header data-testid="topnav-stub" />,
}));

vi.mock("@/features/inbox/api", () => ({
  fetchInbox: vi.fn(() =>
    Promise.resolve({
      items: [],
      page: 1,
      per_page: 20,
      total: 0,
      unread_count: 0,
    }),
  ),
  fetchUnreadCount: vi.fn(() => Promise.resolve({ unread_count: 0 })),
  markInboxRead: vi.fn(),
  fetchActivePopup: vi.fn(),
  markPopupSeen: vi.fn(),
}));

vi.mock("@/features/auth/api", () => ({
  fetchMe: vi.fn(),
}));

const { fetchMe } = await import("@/features/auth/api");

import InboxPage from "../page";

function makeWrapper() {
  return function wrapper({ children }: { children: ReactNode }) {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

beforeEach(() => {
  useSessionStore.setState({ user: null });
  mockReplace.mockReset();
  mockPush.mockReset();
  vi.mocked(fetchMe).mockReset();
  // 기본은 pending — 각 테스트에서 mockResolvedValue/mockRejectedValue로 덮어쓴다.
  vi.mocked(fetchMe).mockImplementation(() => new Promise(() => {}));
});

describe("InboxPage — 인증 가드", () => {
  it("user=null + session query pending → 본문 미렌더 + redirect/openPopup 호출 안 함", async () => {
    useSessionStore.setState({ user: null });
    vi.mocked(fetchMe).mockImplementation(() => new Promise(() => {}));
    const openPopup = vi.fn();
    useSessionStore.setState({ openPopup });

    const { container } = render(<InboxPage />, { wrapper: makeWrapper() });

    expect(container.textContent).toBe("");
    // race fix: pending 동안에는 절대 redirect/popup 발생하면 안 됨
    expect(mockReplace).not.toHaveBeenCalled();
    expect(openPopup).not.toHaveBeenCalled();
  });

  it("user=null + session query 성공 → store sync race 동안 redirect 안 함", async () => {
    useSessionStore.setState({ user: null });
    vi.mocked(fetchMe).mockResolvedValue({
      user_id: 1,
      email: "u@e.com",
      role: "user",
      subscription_status: "free",
      segment: null,
      years_of_experience: null,
      must_reset_password: false,
    } as never);
    const openPopup = vi.fn();
    useSessionStore.setState({ openPopup });

    render(<InboxPage />, { wrapper: makeWrapper() });

    // 쿼리 resolve 후에도 redirect는 isError=true일 때만 일어나야 함
    await waitFor(() =>
      expect(vi.mocked(fetchMe)).toHaveBeenCalled(),
    );
    expect(mockReplace).not.toHaveBeenCalled();
    expect(openPopup).not.toHaveBeenCalled();
  });

  it("user=null + session query 실패 → openPopup + replace 호출", async () => {
    useSessionStore.setState({ user: null });
    vi.mocked(fetchMe).mockRejectedValue(new Error("401"));
    const openPopup = vi.fn();
    useSessionStore.setState({ openPopup });

    render(<InboxPage />, { wrapper: makeWrapper() });

    // 페이지 useQuery는 retry: 1이라 isError 확정까지 ~1s + delay. waitFor timeout 확장.
    await waitFor(() => expect(openPopup).toHaveBeenCalledWith("email"), {
      timeout: 5000,
    });
    expect(mockReplace).toHaveBeenCalledWith("/?login=required");
  });

  it("로그인 시 헤더 + 필터 토글 + InboxList 마운트", async () => {
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
    render(<InboxPage />, { wrapper: makeWrapper() });
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "받은 쪽지함" })).toBeDefined(),
    );
    expect(screen.getByRole("tab", { name: /전체/ })).toBeDefined();
    expect(screen.getByRole("tab", { name: /안 읽음/ })).toBeDefined();
  });

  it("필터 토글 — 클릭 시 aria-selected 갱신", async () => {
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
    render(<InboxPage />, { wrapper: makeWrapper() });
    const unreadTab = await screen.findByRole("tab", { name: /안 읽음/ });
    fireEvent.click(unreadTab);
    expect(unreadTab.getAttribute("aria-selected")).toBe("true");
  });

  it("EmptyState 노출 — total=0", async () => {
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
    render(<InboxPage />, { wrapper: makeWrapper() });
    await waitFor(() =>
      expect(screen.getByText(/아직 받은 쪽지가 없어요/)).toBeDefined(),
    );
  });
});
