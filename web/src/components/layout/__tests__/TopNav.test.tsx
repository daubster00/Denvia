import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { TopNav } from "../TopNav";
import { useSessionStore } from "@/stores/session-store";
import { useToastStore } from "@/stores/toast-store";

const mockReplace = vi.fn();
const mockPathname = vi.fn(() => "/");
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mockReplace }),
  usePathname: () => mockPathname(),
}));

vi.mock("@/features/auth/api", () => ({
  logout: vi.fn(),
}));

vi.mock("@/features/inbox/api", () => ({
  fetchUnreadCount: vi.fn(() => Promise.resolve({ unread_count: 0 })),
}));

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const _LOGGED_IN_USER = {
  user_id: 7,
  email: "doc@denvia.com",
  role: "user" as const,
  subscription_status: "free" as const,
  segment: "doctor" as const,
  years_of_experience: 5,
  must_reset_password: false,
  is_social: false,
};

function openAccountMenu() {
  const toggle = screen.getByRole("button", { name: /계정 메뉴/ });
  fireEvent.click(toggle);
}

beforeEach(async () => {
  mockReplace.mockReset();
  mockPathname.mockReturnValue("/");
  useSessionStore.setState({ user: null, isPopupOpen: false });
  useToastStore.setState({ current: null });
  const { fetchUnreadCount } = await import("@/features/inbox/api");
  vi.mocked(fetchUnreadCount).mockReset();
  vi.mocked(fetchUnreadCount).mockResolvedValue({ unread_count: 0 });
});

describe("TopNav — user 분기 (Story 2.7 AC-2)", () => {
  it("user === null 이면 '로그인' 버튼이 렌더되고 클릭 시 팝업이 오픈된다 (Story 1.2 회귀 방지)", () => {
    render(<TopNav />, { wrapper });
    const btn = screen.getByRole("button", { name: "로그인" });
    btn.click();
    expect(useSessionStore.getState().isPopupOpen).toBe(true);
  });

  it("비로그인 시 쪽지함·계정 메뉴가 DOM에 마운트되지 않는다 (Story 4.3 AC-1 회귀)", () => {
    render(<TopNav />, { wrapper });
    expect(screen.queryByRole("link", { name: "쪽지함" })).toBeNull();
    expect(screen.queryByRole("button", { name: /계정 메뉴/ })).toBeNull();
  });

  it("user 존재 시 계정 토글에 이메일이 표시되고, 메뉴 열면 로그아웃 버튼이 노출된다", () => {
    useSessionStore.setState({ user: _LOGGED_IN_USER });
    render(<TopNav />, { wrapper });
    expect(screen.getByText("doc@denvia.com")).toBeDefined();
    expect(screen.queryByRole("menuitem", { name: "로그아웃" })).toBeNull();
    openAccountMenu();
    expect(screen.getByRole("menuitem", { name: "로그아웃" })).toBeDefined();
    expect(screen.queryByRole("button", { name: "로그인" })).toBeNull();
  });

  it("계정 메뉴 → 로그아웃 클릭 시 logout API 호출 + clearSession + router.replace('/')", async () => {
    const { logout } = await import("@/features/auth/api");
    vi.mocked(logout).mockResolvedValue(undefined);

    useSessionStore.setState({ user: _LOGGED_IN_USER });
    render(<TopNav />, { wrapper });

    openAccountMenu();
    const btn = screen.getByRole("menuitem", { name: "로그아웃" });
    fireEvent.click(btn);
    await new Promise((r) => setTimeout(r, 0));

    expect(vi.mocked(logout)).toHaveBeenCalled();
    expect(useSessionStore.getState().user).toBeNull();
    expect(mockReplace).toHaveBeenCalledWith("/");
  });
});

describe("TopNav — 풀 메뉴 확장 (Story 4.3 AC-1)", () => {
  it("로그인 후 쪽지함 링크는 상단에, 마이페이지는 계정 메뉴 안에 표시된다", () => {
    useSessionStore.setState({ user: _LOGGED_IN_USER });
    render(<TopNav />, { wrapper });

    const inboxLink = screen.getByRole("link", { name: "쪽지함" });
    expect(inboxLink.getAttribute("href")).toBe("/inbox");
    expect(screen.queryByRole("menuitem", { name: "마이페이지" })).toBeNull();

    openAccountMenu();
    const myLink = screen.getByRole("menuitem", { name: "마이페이지" });
    expect(myLink.getAttribute("href")).toBe("/my");
  });

  it("/my 라우트에서 메뉴 내부 마이페이지가 aria-current='page'", () => {
    mockPathname.mockReturnValue("/my");
    useSessionStore.setState({ user: _LOGGED_IN_USER });
    render(<TopNav />, { wrapper });
    openAccountMenu();
    const myLink = screen.getByRole("menuitem", { name: "마이페이지" });
    expect(myLink.getAttribute("aria-current")).toBe("page");
  });

  it("/ 라우트에서 마이페이지는 aria-current 미적용", () => {
    mockPathname.mockReturnValue("/");
    useSessionStore.setState({ user: _LOGGED_IN_USER });
    render(<TopNav />, { wrapper });
    openAccountMenu();
    const myLink = screen.getByRole("menuitem", { name: "마이페이지" });
    expect(myLink.getAttribute("aria-current")).toBeNull();
  });

  it("Free 사용자는 'Bs' 플랜 원이 상단에 노출된다 (Basic 약어)", () => {
    useSessionStore.setState({ user: _LOGGED_IN_USER });
    render(<TopNav />, { wrapper });

    const badge = screen.getByLabelText("Basic 플랜");
    expect(badge.textContent).toBe("Bs");
  });

  it("Pro 사용자는 'Pr' 플랜 원이 상단에 노출되고 메뉴 안에서 'Pro' 명이 표시된다", () => {
    useSessionStore.setState({
      user: { ..._LOGGED_IN_USER, subscription_status: "pro" },
    });
    render(<TopNav />, { wrapper });

    expect(screen.getByRole("link", { name: "쪽지함" })).toBeDefined();
    const badge = screen.getByLabelText("Pro 플랜");
    expect(badge.textContent).toBe("Pr");

    openAccountMenu();
    expect(screen.getByText("현재 플랜")).toBeDefined();
    expect(screen.getByText("Pro")).toBeDefined();
  });
});

describe("TopNav — 미읽음 뱃지 (Story 4.5 AC-11)", () => {
  it("비로그인 시 fetchUnreadCount 호출되지 않음", async () => {
    const { fetchUnreadCount } = await import("@/features/inbox/api");
    useSessionStore.setState({ user: null });
    render(<TopNav />, { wrapper });
    await new Promise((r) => setTimeout(r, 10));
    expect(fetchUnreadCount).not.toHaveBeenCalled();
  });

  it("미읽음 0건 → 뱃지 미렌더", async () => {
    const { fetchUnreadCount } = await import("@/features/inbox/api");
    vi.mocked(fetchUnreadCount).mockResolvedValue({ unread_count: 0 });
    useSessionStore.setState({ user: _LOGGED_IN_USER });
    render(<TopNav />, { wrapper });
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("미읽음 1건 → 뱃지 '1' + ARIA label", async () => {
    const { fetchUnreadCount } = await import("@/features/inbox/api");
    vi.mocked(fetchUnreadCount).mockResolvedValue({ unread_count: 1 });
    useSessionStore.setState({ user: _LOGGED_IN_USER });
    render(<TopNav />, { wrapper });
    const badge = await screen.findByRole("status");
    expect(badge.textContent).toBe("1");
    expect(badge.getAttribute("aria-label")).toBe("안 읽은 쪽지 1개");
  });

  it("미읽음 10건 → 뱃지 '9+' (ellipsis)", async () => {
    const { fetchUnreadCount } = await import("@/features/inbox/api");
    vi.mocked(fetchUnreadCount).mockResolvedValue({ unread_count: 10 });
    useSessionStore.setState({ user: _LOGGED_IN_USER });
    render(<TopNav />, { wrapper });
    const badge = await screen.findByRole("status");
    expect(badge.textContent).toBe("9+");
  });

  it("/inbox 라우트에서 쪽지함 링크 aria-current='page'", () => {
    mockPathname.mockReturnValue("/inbox");
    useSessionStore.setState({ user: _LOGGED_IN_USER });
    render(<TopNav />, { wrapper });
    const link = screen.getByRole("link", { name: "쪽지함" });
    expect(link.getAttribute("aria-current")).toBe("page");
  });
});
