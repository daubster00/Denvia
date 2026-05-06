/** Story 1.7 — ConfirmWithdrawPopup 단위 테스트 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ConfirmWithdrawPopup } from "../ConfirmWithdrawPopup";
import { useSessionStore } from "@/stores/session-store";
import { useAlertStore } from "@/stores/alert-store";
import { useToastStore } from "@/stores/toast-store";
import { ApiError } from "@/types/api";
import * as authApi from "../api";

const mockReplace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mockReplace, push: vi.fn() }),
}));

// sessionStorage mock — useSessionStore의 persist 호환
const mockStorage: Record<string, string> = {};
Object.defineProperty(window, "sessionStorage", {
  value: {
    getItem: (k: string) => mockStorage[k] ?? null,
    setItem: (k: string, v: string) => {
      mockStorage[k] = v;
    },
    removeItem: (k: string) => {
      delete mockStorage[k];
    },
    clear: () => {
      Object.keys(mockStorage).forEach((k) => delete mockStorage[k]);
    },
  },
  writable: true,
});

function makeUser(opts: { is_social: boolean }) {
  return {
    user_id: 1,
    email: "doc@denvia.com",
    role: "user" as const,
    subscription_status: "free" as const,
    segment: null,
    years_of_experience: null,
    must_reset_password: false,
    is_social: opts.is_social,
  };
}

function renderPopup(open = true) {
  const onClose = vi.fn();
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const utils = render(
    <QueryClientProvider client={qc}>
      <ConfirmWithdrawPopup open={open} onClose={onClose} />
    </QueryClientProvider>,
  );
  return { ...utils, onClose };
}

beforeEach(() => {
  useSessionStore.setState({ user: null });
  useAlertStore.setState({ current: null });
  useToastStore.setState({ current: null });
  Object.keys(mockStorage).forEach((k) => delete mockStorage[k]);
  mockReplace.mockReset();
  vi.restoreAllMocks();
});

describe("ConfirmWithdrawPopup — 자체 가입자(is_social=false)", () => {
  it("체크박스 + 비밀번호 미입력 시 탈퇴하기 disabled", () => {
    useSessionStore.setState({ user: makeUser({ is_social: false }) });
    renderPopup();
    const submit = screen.getByRole("button", { name: /탈퇴하기/ });
    expect((submit as HTMLButtonElement).disabled).toBe(true);
  });

  it("체크박스 + 비밀번호 입력 → 탈퇴 성공 → clearSession + Toast + router.replace", async () => {
    const user = userEvent.setup();
    useSessionStore.setState({ user: makeUser({ is_social: false }) });
    const withdrawSpy = vi.spyOn(authApi, "withdraw").mockResolvedValue();

    renderPopup();
    await user.click(screen.getByRole("checkbox"));
    await user.type(screen.getByLabelText(/현재 비밀번호/), "password123");
    await user.click(screen.getByRole("button", { name: /탈퇴하기/ }));

    await waitFor(() => {
      expect(withdrawSpy).toHaveBeenCalledWith({ password: "password123" });
    });
    expect(useSessionStore.getState().user).toBeNull();
    expect(mockReplace).toHaveBeenCalledWith("/");
    expect(useToastStore.getState().current?.message).toContain("탈퇴가 완료");
  });

  it("AUTH_INVALID_CREDENTIALS 401 → 비밀번호 인라인 에러 표시", async () => {
    const user = userEvent.setup();
    useSessionStore.setState({ user: makeUser({ is_social: false }) });
    vi.spyOn(authApi, "withdraw").mockRejectedValue(
      new ApiError({
        code: "AUTH_INVALID_CREDENTIALS",
        message: "비밀번호가 일치하지 않습니다",
        trace_id: "",
      }),
    );

    renderPopup();
    await user.click(screen.getByRole("checkbox"));
    await user.type(screen.getByLabelText(/현재 비밀번호/), "wrong");
    await user.click(screen.getByRole("button", { name: /탈퇴하기/ }));

    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toContain("일치하지 않습니다");
    });
    // 세션은 유지
    expect(useSessionStore.getState().user).not.toBeNull();
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("SUBSCRIPTION_ACTIVE_MUST_CANCEL_FIRST 409 → useAlertStore.show 호출", async () => {
    const user = userEvent.setup();
    useSessionStore.setState({ user: makeUser({ is_social: false }) });
    vi.spyOn(authApi, "withdraw").mockRejectedValue(
      new ApiError({
        code: "SUBSCRIPTION_ACTIVE_MUST_CANCEL_FIRST",
        message: "구독을 먼저 해지해주세요",
        trace_id: "",
      }),
    );

    renderPopup();
    await user.click(screen.getByRole("checkbox"));
    await user.type(screen.getByLabelText(/현재 비밀번호/), "ok");
    await user.click(screen.getByRole("button", { name: /탈퇴하기/ }));

    await waitFor(() => {
      expect(useAlertStore.getState().current?.title).toBe("구독 해지 필요");
    });
    expect(useSessionStore.getState().user).not.toBeNull();
  });
});

describe("ConfirmWithdrawPopup — 소셜 가입자(is_social=true)", () => {
  it("OTP 발송 → verify → 탈퇴 성공 흐름", async () => {
    const user = userEvent.setup();
    useSessionStore.setState({ user: makeUser({ is_social: true }) });

    vi.spyOn(authApi, "sendWithdrawOtp").mockResolvedValue({
      masked_phone: "010-****-5678",
    });
    vi.spyOn(authApi, "verifyWithdrawOtp").mockResolvedValue({
      phone_verification_token: "tok-abc",
    });
    const withdrawSpy = vi.spyOn(authApi, "withdraw").mockResolvedValue();

    renderPopup();
    // 비밀번호 입력 필드는 없어야 함
    expect(screen.queryByLabelText(/현재 비밀번호/)).toBeNull();

    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: /인증번호 전송/ }));

    await waitFor(() =>
      expect(screen.getByLabelText(/인증번호 6자리/)).toBeDefined(),
    );

    await user.type(screen.getByLabelText(/인증번호 6자리/), "123456");
    await user.click(screen.getByRole("button", { name: /^확인$/ }));

    await waitFor(() => {
      expect(screen.getByText(/인증이 완료되었습니다/)).toBeDefined();
    });

    await user.click(screen.getByRole("button", { name: /탈퇴하기/ }));

    await waitFor(() => {
      expect(withdrawSpy).toHaveBeenCalledWith({
        phone_verification_token: "tok-abc",
      });
    });
    expect(useSessionStore.getState().user).toBeNull();
    expect(mockReplace).toHaveBeenCalledWith("/");
  });

  it("phone_verification_token 미획득 상태에서는 탈퇴하기 disabled", () => {
    useSessionStore.setState({ user: makeUser({ is_social: true }) });
    renderPopup();
    const submit = screen.getByRole("button", { name: /탈퇴하기/ });
    expect((submit as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("ConfirmWithdrawPopup — open=false", () => {
  it("렌더되지 않음", () => {
    useSessionStore.setState({ user: makeUser({ is_social: false }) });
    renderPopup(false);
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
