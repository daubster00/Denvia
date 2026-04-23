import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EmailLoginTab } from "../EmailLoginTab";
import { useSessionStore } from "@/stores/session-store";
import * as authApi from "../api";

// sessionStorage 모킹
const mockStorage: Record<string, string> = {};
Object.defineProperty(window, "sessionStorage", {
  value: {
    getItem: (k: string) => mockStorage[k] ?? null,
    setItem: (k: string, v: string) => { mockStorage[k] = v; },
    removeItem: (k: string) => { delete mockStorage[k]; },
    clear: () => { Object.keys(mockStorage).forEach(k => delete mockStorage[k]); },
  },
  writable: true,
});

beforeEach(() => {
  useSessionStore.setState({ user: null, isPopupOpen: true, preferPersist: false });
  Object.keys(mockStorage).forEach(k => delete mockStorage[k]);
  vi.restoreAllMocks();
});

describe("EmailLoginTab", () => {
  it("이메일·비밀번호 input이 렌더된다", () => {
    render(<EmailLoginTab />);
    expect(screen.getByLabelText(/이메일/i)).toBeDefined();
    expect(screen.getByLabelText(/비밀번호/i)).toBeDefined();
  });

  it("로그인 상태 유지 체크박스가 있다", () => {
    render(<EmailLoginTab />);
    const cb = screen.getByRole("checkbox");
    expect(cb).toBeDefined();
  });

  it("로그인 성공 시 setUser + closePopup 호출", async () => {
    const mockUser = {
      user_id: 1,
      email: "doc@denvia.com",
      role: "user" as const,
      subscription_status: "free" as const,
      segment: null,
      years_of_experience: null,
      must_reset_password: false,
    };
    vi.spyOn(authApi, "login").mockResolvedValue(mockUser);

    const user = userEvent.setup();
    render(<EmailLoginTab />);

    await user.type(screen.getByLabelText(/이메일/i), "doc@denvia.com");
    await user.type(screen.getByLabelText(/비밀번호/i), "password123");
    await user.click(screen.getByRole("button", { name: /로그인/ }));

    await waitFor(() => {
      expect(useSessionStore.getState().user?.user_id).toBe(1);
      expect(useSessionStore.getState().isPopupOpen).toBe(false);
    });
  });

  it("AUTH_INVALID_CREDENTIALS 시 에러 메시지 표시", async () => {
    const { ApiError } = await import("@/types/api");
    vi.spyOn(authApi, "login").mockRejectedValue(
      new ApiError({ code: "AUTH_INVALID_CREDENTIALS", message: "이메일 또는 비밀번호가 일치하지 않습니다.", trace_id: "" })
    );

    const user = userEvent.setup();
    render(<EmailLoginTab />);

    await user.type(screen.getByLabelText(/이메일/i), "doc@denvia.com");
    await user.type(screen.getByLabelText(/비밀번호/i), "wrongpassword");
    await user.click(screen.getByRole("button", { name: /로그인/ }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeDefined();
    });
    expect(screen.getByRole("alert").textContent).toContain("이메일 또는 비밀번호");
  });

  it("AUTH_TEMPORARILY_LOCKED 시 락아웃 메시지 표시", async () => {
    const { ApiError } = await import("@/types/api");
    vi.spyOn(authApi, "login").mockRejectedValue(
      new ApiError({ code: "AUTH_TEMPORARILY_LOCKED", message: "잠시 후 다시 시도해주세요.", trace_id: "" })
    );

    const user = userEvent.setup();
    render(<EmailLoginTab />);

    await user.type(screen.getByLabelText(/이메일/i), "brute@denvia.com");
    await user.type(screen.getByLabelText(/비밀번호/i), "anything12");
    await user.click(screen.getByRole("button", { name: /로그인/ }));

    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toContain("잠시 후");
    });
  });

  it("회원가입 버튼 클릭 시 onSignup 콜백 호출", async () => {
    const onSignup = vi.fn();
    const user = userEvent.setup();
    render(<EmailLoginTab onSignup={onSignup} />);
    await user.click(screen.getByRole("button", { name: /회원가입/i }));
    expect(onSignup).toHaveBeenCalledOnce();
  });
});
