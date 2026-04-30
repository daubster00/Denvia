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
  vi.unstubAllGlobals();
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
    await user.click(screen.getByRole("button", { name: /^로그인$/ }));

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

  // ── OAuth-only 힌트 케이스 (Story 1.8 AC-8, AC-9, AC-11) ────────────────────

  it("AUTH_ACCOUNT_OAUTH_ONLY 단일 provider → 안내 카드 + 버튼 노출", async () => {
    const { ApiError } = await import("@/types/api");
    vi.spyOn(authApi, "login").mockRejectedValue(
      new ApiError({
        code: "AUTH_ACCOUNT_OAUTH_ONLY",
        message: "이 계정은 네이버로 가입되어 있습니다. 네이버로 로그인해 주세요.",
        trace_id: "",
        details: { linked_providers: ["naver"] },
      })
    );

    const user = userEvent.setup();
    render(<EmailLoginTab />);

    await user.type(screen.getByLabelText(/이메일/i), "social@denvia.com");
    await user.type(screen.getByLabelText(/비밀번호/i), "anything12");
    await user.click(screen.getByRole("button", { name: /^로그인$/ }));

    await waitFor(() => {
      expect(screen.getByRole("status")).toBeDefined();
    });
    expect(screen.getByRole("status").textContent).toContain("네이버");
    // 강조 provider 버튼 노출
    expect(screen.getByRole("button", { name: /네이버로 로그인/ })).toBeDefined();
    // 빨간 에러 배너 미노출 (role="alert" 없음)
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("AUTH_ACCOUNT_OAUTH_ONLY 복수 provider → 두 버튼 모두 노출", async () => {
    const { ApiError } = await import("@/types/api");
    vi.spyOn(authApi, "login").mockRejectedValue(
      new ApiError({
        code: "AUTH_ACCOUNT_OAUTH_ONLY",
        message: "이 계정은 카카오, 구글로 가입되어 있습니다. 가입한 채널로 로그인해 주세요.",
        trace_id: "",
        details: { linked_providers: ["kakao", "google"] },
      })
    );

    const user = userEvent.setup();
    render(<EmailLoginTab />);

    await user.type(screen.getByLabelText(/이메일/i), "social@denvia.com");
    await user.type(screen.getByLabelText(/비밀번호/i), "anything12");
    await user.click(screen.getByRole("button", { name: /^로그인$/ }));

    await waitFor(() => {
      expect(screen.getByRole("status")).toBeDefined();
    });
    expect(screen.getByRole("button", { name: /카카오로 로그인/ })).toBeDefined();
    expect(screen.getByRole("button", { name: /구글로 로그인/ })).toBeDefined();
  });

  it("OAuth-only 힌트 노출 후 재submit INVALID → 힌트 사라지고 에러 배너", async () => {
    const { ApiError } = await import("@/types/api");
    const loginSpy = vi.spyOn(authApi, "login")
      .mockRejectedValueOnce(
        new ApiError({
          code: "AUTH_ACCOUNT_OAUTH_ONLY",
          message: "이 계정은 네이버로 가입되어 있습니다. 네이버로 로그인해 주세요.",
          trace_id: "",
          details: { linked_providers: ["naver"] },
        })
      )
      .mockRejectedValueOnce(
        new ApiError({
          code: "AUTH_INVALID_CREDENTIALS",
          message: "이메일 또는 비밀번호가 일치하지 않습니다.",
          trace_id: "",
        })
      );

    const user = userEvent.setup();
    render(<EmailLoginTab />);

    await user.type(screen.getByLabelText(/이메일/i), "social@denvia.com");
    await user.type(screen.getByLabelText(/비밀번호/i), "anything12");
    await user.click(screen.getByRole("button", { name: /^로그인$/ }));

    // 첫 번째: 안내 카드 노출
    await waitFor(() => expect(screen.getByRole("status")).toBeDefined());

    // 두 번째 submit
    await user.click(screen.getByRole("button", { name: /^로그인$/ }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeDefined();
    });
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("provider 버튼 클릭 → window.location.href OAuth authorize 경로로 이동", async () => {
    const { ApiError } = await import("@/types/api");
    vi.spyOn(authApi, "login").mockRejectedValue(
      new ApiError({
        code: "AUTH_ACCOUNT_OAUTH_ONLY",
        message: "이 계정은 카카오로 가입되어 있습니다. 카카오로 로그인해 주세요.",
        trace_id: "",
        details: { linked_providers: ["kakao"] },
      })
    );

    const mockHref = { href: "" };
    vi.stubGlobal("location", mockHref);

    const user = userEvent.setup();
    render(<EmailLoginTab />);

    await user.type(screen.getByLabelText(/이메일/i), "social@denvia.com");
    await user.type(screen.getByLabelText(/비밀번호/i), "anything12");
    await user.click(screen.getByRole("button", { name: /^로그인$/ }));

    await waitFor(() => screen.getByRole("button", { name: /카카오로 로그인/ }));
    await user.click(screen.getByRole("button", { name: /카카오로 로그인/ }));

    expect(mockHref.href).toContain("/api/v1/auth/oauth/kakao/authorize");
    expect(mockHref.href).toContain("mode=login");
  });

  it("RATE_LIMITED 에러도 락아웃 안내 문구 표시", async () => {
    const { ApiError } = await import("@/types/api");
    vi.spyOn(authApi, "login").mockRejectedValue(
      new ApiError({ code: "RATE_LIMITED", message: "Too many requests", trace_id: "" })
    );

    const user = userEvent.setup();
    render(<EmailLoginTab />);

    await user.type(screen.getByLabelText(/이메일/i), "doc@denvia.com");
    await user.type(screen.getByLabelText(/비밀번호/i), "anything12");
    await user.click(screen.getByRole("button", { name: /^로그인$/ }));

    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toContain("잠시 후");
    });
    expect(screen.queryByRole("status")).toBeNull();
  });
});
