import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { TopNav } from "../TopNav";
import { useSessionStore } from "@/stores/session-store";

const mockReplace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mockReplace }),
}));

vi.mock("@/features/auth/api", () => ({
  logout: vi.fn(),
}));

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  mockReplace.mockReset();
  useSessionStore.setState({ user: null, isPopupOpen: false });
});

describe("TopNav — user 분기 (Story 2.7 AC-2)", () => {
  it("user === null 이면 '로그인' 버튼이 렌더되고 클릭 시 팝업이 오픈된다 (Story 1.2 회귀 방지)", () => {
    render(<TopNav />, { wrapper });
    const btn = screen.getByRole("button", { name: "로그인" });
    btn.click();
    expect(useSessionStore.getState().isPopupOpen).toBe(true);
  });

  it("user 존재 시 이메일 + '로그아웃' 버튼이 렌더된다", () => {
    useSessionStore.setState({
      user: {
        user_id: 7,
        email: "doc@denvia.com",
        role: "user",
        subscription_status: "free",
        segment: "doctor",
        years_of_experience: 5,
        must_reset_password: false,
      },
    });
    render(<TopNav />, { wrapper });
    expect(screen.getByText("doc@denvia.com")).toBeDefined();
    expect(screen.getByRole("button", { name: "로그아웃" })).toBeDefined();
    expect(screen.queryByRole("button", { name: "로그인" })).toBeNull();
  });

  it("user 존재 + 로그아웃 클릭 시 logout API 호출 + clearSession + router.replace('/')", async () => {
    const { logout } = await import("@/features/auth/api");
    vi.mocked(logout).mockResolvedValue(undefined);

    useSessionStore.setState({
      user: {
        user_id: 7,
        email: "doc@denvia.com",
        role: "user",
        subscription_status: "free",
        segment: "doctor",
        years_of_experience: 5,
        must_reset_password: false,
      },
    });
    render(<TopNav />, { wrapper });

    const btn = screen.getByRole("button", { name: "로그아웃" });
    btn.click();
    // promise resolve 대기
    await new Promise((r) => setTimeout(r, 0));

    expect(vi.mocked(logout)).toHaveBeenCalled();
    expect(useSessionStore.getState().user).toBeNull();
    expect(mockReplace).toHaveBeenCalledWith("/");
  });
});
