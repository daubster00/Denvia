/** SupportWidget 단위 테스트 — 0030 1:1 문의 게시판화.
 *
 * 위젯은 더 이상 모달을 띄우지 않는다. 클릭 시 /my/inquiries/new 로 이동하는
 * 링크 1개만 렌더하며, 비로그인/관리자 화면에서는 미렌더된다.
 */

import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

import { useSessionStore } from "@/stores/session-store";

const mockPathname = vi.fn(() => "/");

vi.mock("next/navigation", () => ({
  usePathname: () => mockPathname(),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

import { SupportWidget } from "../components/SupportWidget";

const _LOGGED_IN_USER = {
  user_id: 1,
  email: "u@e.com",
  role: "user" as const,
  subscription_status: "free" as const,
  segment: null,
  years_of_experience: null,
  must_reset_password: false,
  is_social: false,
};

beforeEach(() => {
  mockPathname.mockReturnValue("/");
  useSessionStore.setState({ user: null });
});

describe("SupportWidget — 가시성 분기", () => {
  it("/admin/* 라우트에서는 미렌더", () => {
    mockPathname.mockReturnValue("/admin/dashboard");
    const { container } = render(<SupportWidget />);
    expect(container.textContent).toBe("");
  });

  it("비로그인 → 위젯 자체 미렌더", () => {
    useSessionStore.setState({ user: null });
    const { container } = render(<SupportWidget />);
    expect(container.textContent).toBe("");
    expect(screen.queryByRole("link", { name: "문의 작성" })).toBeNull();
  });

  it("로그인 → /my/inquiries/new 로 가는 링크 1개", () => {
    useSessionStore.setState({ user: _LOGGED_IN_USER });
    render(<SupportWidget />);
    const link = screen.getByRole("link", { name: "문의 작성" });
    expect(link).toBeDefined();
    expect(link.getAttribute("href")).toBe("/my/inquiries/new");
  });
});
