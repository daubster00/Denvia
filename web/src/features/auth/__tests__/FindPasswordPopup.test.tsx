import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { FindPasswordPopup } from "../FindPasswordPopup";

vi.mock("@/features/auth/api", () => ({
  requestPasswordReset: vi.fn(),
}));

const mockOnBack = vi.fn();

beforeEach(() => {
  vi.resetAllMocks();
  mockOnBack.mockReset();
});

describe("FindPasswordPopup", () => {
  it("이메일 + 휴대폰 입력 폼이 렌더된다", () => {
    render(<FindPasswordPopup onBack={mockOnBack} />);
    expect(screen.getByLabelText(/이메일/)).toBeDefined();
    expect(screen.getByText("임시 비밀번호 받기")).toBeDefined();
  });

  it("submit 시 requestPasswordReset이 호출된다", async () => {
    const { requestPasswordReset } = await import("@/features/auth/api");
    vi.mocked(requestPasswordReset).mockResolvedValue({ ok: true, linked_providers: [] });

    render(<FindPasswordPopup onBack={mockOnBack} />);

    fireEvent.change(screen.getByLabelText(/이메일/), {
      target: { value: "doc@denvia.com" },
    });
    fireEvent.change(screen.getByPlaceholderText("010-0000-0000"), {
      target: { value: "010-1234-5678" },
    });
    fireEvent.click(screen.getByText("임시 비밀번호 받기"));

    await waitFor(() => {
      expect(requestPasswordReset).toHaveBeenCalledWith({
        email: "doc@denvia.com",
        phone: "01012345678",
      });
    });
  });

  it("성공 후 SMS 확인 안내 메시지를 표시한다", async () => {
    const { requestPasswordReset } = await import("@/features/auth/api");
    vi.mocked(requestPasswordReset).mockResolvedValue({ ok: true, linked_providers: [] });

    render(<FindPasswordPopup onBack={mockOnBack} />);

    fireEvent.change(screen.getByLabelText(/이메일/), {
      target: { value: "doc@denvia.com" },
    });
    fireEvent.change(screen.getByPlaceholderText("010-0000-0000"), {
      target: { value: "010-1234-5678" },
    });
    fireEvent.click(screen.getByText("임시 비밀번호 받기"));

    await waitFor(() => {
      expect(screen.getByText(/SMS를 확인해주세요/)).toBeTruthy();
    });
  });

  it("API 오류가 발생해도 성공 화면으로 전환된다 (계정 열거 방지)", async () => {
    const { requestPasswordReset } = await import("@/features/auth/api");
    vi.mocked(requestPasswordReset).mockRejectedValue(new Error("server error"));

    render(<FindPasswordPopup onBack={mockOnBack} />);

    fireEvent.change(screen.getByLabelText(/이메일/), {
      target: { value: "doc@denvia.com" },
    });
    fireEvent.change(screen.getByPlaceholderText("010-0000-0000"), {
      target: { value: "010-1234-5678" },
    });
    fireEvent.click(screen.getByText("임시 비밀번호 받기"));

    await waitFor(() => {
      expect(screen.getByText(/SMS를 확인해주세요/)).toBeTruthy();
    });
  });

  it("소셜 전용 계정이면 안내 + 소셜 로그인 버튼을 노출한다", async () => {
    const { requestPasswordReset } = await import("@/features/auth/api");
    vi.mocked(requestPasswordReset).mockResolvedValue({
      ok: true,
      linked_providers: ["kakao"],
    });

    render(<FindPasswordPopup onBack={mockOnBack} />);

    fireEvent.change(screen.getByLabelText(/이메일/), {
      target: { value: "social@denvia.com" },
    });
    fireEvent.change(screen.getByPlaceholderText("010-0000-0000"), {
      target: { value: "010-9999-8888" },
    });
    fireEvent.click(screen.getByText("임시 비밀번호 받기"));

    await waitFor(() => {
      expect(screen.getByText(/카카오\(으\)로 가입하신 계정입니다/)).toBeTruthy();
      expect(screen.getByLabelText("카카오로 로그인")).toBeTruthy();
    });
    // 기본 SMS 안내는 노출되지 않음
    expect(screen.queryByText(/SMS를 확인해주세요/)).toBeNull();
  });

  it("성공 화면에서 onBack 버튼이 있다", async () => {
    const { requestPasswordReset } = await import("@/features/auth/api");
    vi.mocked(requestPasswordReset).mockResolvedValue({ ok: true, linked_providers: [] });

    render(<FindPasswordPopup onBack={mockOnBack} />);

    fireEvent.change(screen.getByLabelText(/이메일/), {
      target: { value: "doc@denvia.com" },
    });
    fireEvent.change(screen.getByPlaceholderText("010-0000-0000"), {
      target: { value: "010-1234-5678" },
    });
    fireEvent.click(screen.getByText("임시 비밀번호 받기"));

    await waitFor(() => {
      expect(screen.getByText("로그인 화면으로 돌아가기")).toBeTruthy();
    });

    fireEvent.click(screen.getByText("로그인 화면으로 돌아가기"));
    expect(mockOnBack).toHaveBeenCalled();
  });
});
