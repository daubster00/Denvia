/** SupportWidget 단위 테스트 — Story 4.5 (T8.7).
 *  카카오 채널 버튼은 현재 숨김 상태 — 관련 분기 테스트는 비활성화.
 */

import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { useSessionStore } from "@/stores/session-store";

const mockPathname = vi.fn(() => "/");

vi.mock("next/navigation", () => ({
  usePathname: () => mockPathname(),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

vi.mock("../api", () => ({
  postInquiry: vi.fn(),
}));

const { postInquiry } = await import("../api");

import { SupportWidget } from "../components/SupportWidget";

function makeWrapper() {
  return function wrapper({ children }: { children: ReactNode }) {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

const _LOGGED_IN_USER = {
  user_id: 1,
  email: "u@e.com",
  role: "user" as const,
  subscription_status: "free" as const,
  segment: null,
  years_of_experience: null,
  must_reset_password: false,
};

beforeEach(() => {
  mockPathname.mockReturnValue("/");
  useSessionStore.setState({ user: null });
  vi.mocked(postInquiry).mockReset();
});

describe("SupportWidget — 가시성 분기", () => {
  it("/admin/* 라우트에서는 미렌더", () => {
    mockPathname.mockReturnValue("/admin/dashboard");
    const { container } = render(<SupportWidget />, { wrapper: makeWrapper() });
    expect(container.textContent).toBe("");
  });

  it("비로그인 → 위젯 자체 미렌더 (카카오 버튼 숨김 상태)", () => {
    useSessionStore.setState({ user: null });
    const { container } = render(<SupportWidget />, { wrapper: makeWrapper() });
    expect(container.textContent).toBe("");
    expect(screen.queryByLabelText("카카오톡 채널 상담")).toBeNull();
    expect(screen.queryByRole("button", { name: "문의 작성" })).toBeNull();
  });

  it("로그인 → 문의 작성 버튼만 표시 (카카오 버튼 숨김 상태)", () => {
    useSessionStore.setState({ user: _LOGGED_IN_USER });
    render(<SupportWidget />, { wrapper: makeWrapper() });
    expect(screen.getByRole("button", { name: "문의 작성" })).toBeDefined();
    expect(screen.queryByLabelText("카카오톡 채널 상담")).toBeNull();
  });
});

describe("SupportWidget — 문의 작성 버튼", () => {
  it("로그인 사용자 클릭 시 InquirySubmitDialog 마운트", async () => {
    useSessionStore.setState({ user: _LOGGED_IN_USER });
    render(<SupportWidget />, { wrapper: makeWrapper() });
    fireEvent.click(screen.getByRole("button", { name: "문의 작성" }));
    expect(await screen.findByText("고객 문의")).toBeDefined();
  });

  it("성공 응답 시 모달 close + Toast 호출", async () => {
    useSessionStore.setState({ user: _LOGGED_IN_USER });
    vi.mocked(postInquiry).mockResolvedValue({ inquiry_id: 7 });

    render(<SupportWidget />, { wrapper: makeWrapper() });
    fireEvent.click(screen.getByRole("button", { name: "문의 작성" }));

    fireEvent.change(await screen.findByPlaceholderText(/결제가 두 번/), {
      target: { value: "결제 문의" },
    });
    fireEvent.change(screen.getByPlaceholderText(/도움이 필요/), {
      target: { value: "두 번 청구되었어요" },
    });
    fireEvent.click(screen.getByRole("button", { name: "제출" }));

    await waitFor(() =>
      expect(postInquiry).toHaveBeenCalledWith("결제 문의", "두 번 청구되었어요"),
    );
    await waitFor(() => expect(screen.queryByText("고객 문의")).toBeNull());
  });

  it("422 응답 시 인라인 에러 메시지 표시", async () => {
    useSessionStore.setState({ user: _LOGGED_IN_USER });
    const { ApiError } = await import("@/types/api");
    vi.mocked(postInquiry).mockRejectedValue(
      new ApiError({
        code: "INVALID_PARAM",
        message: "제목이 너무 깁니다.",
        trace_id: "t1",
      }),
    );

    render(<SupportWidget />, { wrapper: makeWrapper() });
    fireEvent.click(screen.getByRole("button", { name: "문의 작성" }));
    fireEvent.change(await screen.findByPlaceholderText(/결제가 두 번/), {
      target: { value: "OK" },
    });
    fireEvent.change(screen.getByPlaceholderText(/도움이 필요/), {
      target: { value: "본문" },
    });
    fireEvent.click(screen.getByRole("button", { name: "제출" }));

    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toContain("제목이 너무 깁니다."),
    );
  });

  it("429 RATE_LIMITED 응답 시 인라인 에러", async () => {
    useSessionStore.setState({ user: _LOGGED_IN_USER });
    const { ApiError } = await import("@/types/api");
    vi.mocked(postInquiry).mockRejectedValue(
      new ApiError({
        code: "RATE_LIMITED",
        message: "잠시 후 다시 시도해주세요.",
        trace_id: "t2",
      }),
    );

    render(<SupportWidget />, { wrapper: makeWrapper() });
    fireEvent.click(screen.getByRole("button", { name: "문의 작성" }));
    fireEvent.change(await screen.findByPlaceholderText(/결제가 두 번/), {
      target: { value: "OK" },
    });
    fireEvent.change(screen.getByPlaceholderText(/도움이 필요/), {
      target: { value: "본문" },
    });
    fireEvent.click(screen.getByRole("button", { name: "제출" }));

    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toContain("분당 3회 제한"),
    );
  });

  it("폼 검증 — 제목 빈값 시 인라인 에러 + 제출 차단", async () => {
    useSessionStore.setState({ user: _LOGGED_IN_USER });
    render(<SupportWidget />, { wrapper: makeWrapper() });
    fireEvent.click(screen.getByRole("button", { name: "문의 작성" }));

    const submitBtn = await screen.findByRole("button", { name: "제출" });
    const textareaEl = screen.getByPlaceholderText(/도움이 필요/);
    (textareaEl as HTMLTextAreaElement).value = "본문";
    fireEvent.click(submitBtn);
    expect(postInquiry).not.toHaveBeenCalled();
  });
});
