import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ResetPasswordPage from "../page";

const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

vi.mock("@/features/auth/api", () => ({
  changePassword: vi.fn(),
}));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ResetPasswordPage />
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.resetAllMocks();
  mockPush.mockReset();
});

describe("ResetPasswordPage", () => {
  it("새 비밀번호 + 확인 입력 폼이 렌더된다", () => {
    renderPage();
    expect(screen.getByLabelText(/새 비밀번호/)).toBeTruthy();
    expect(screen.getByLabelText(/비밀번호 확인/)).toBeTruthy();
    expect(screen.getByText("비밀번호 변경")).toBeTruthy();
  });

  it("8자 미만 → 검증 오류 표시", async () => {
    renderPage();

    fireEvent.change(screen.getByLabelText(/새 비밀번호/), { target: { value: "short" } });
    fireEvent.change(screen.getByLabelText(/비밀번호 확인/), { target: { value: "short" } });
    fireEvent.click(screen.getByText("비밀번호 변경"));

    await waitFor(() => {
      expect(screen.getByText(/8자 이상/)).toBeTruthy();
    });
  });

  it("비밀번호 불일치 → 검증 오류 표시", async () => {
    renderPage();

    fireEvent.change(screen.getByLabelText(/새 비밀번호/), { target: { value: "password123" } });
    fireEvent.change(screen.getByLabelText(/비밀번호 확인/), { target: { value: "different123" } });
    fireEvent.click(screen.getByText("비밀번호 변경"));

    await waitFor(() => {
      expect(screen.getByText(/일치하지 않습니다/)).toBeTruthy();
    });
  });

  it("성공 시 / 로 라우팅된다", async () => {
    const { changePassword } = await import("@/features/auth/api");
    vi.mocked(changePassword).mockResolvedValue({ ok: true });

    renderPage();

    fireEvent.change(screen.getByLabelText(/새 비밀번호/), { target: { value: "newpass99" } });
    fireEvent.change(screen.getByLabelText(/비밀번호 확인/), { target: { value: "newpass99" } });
    fireEvent.click(screen.getByText("비밀번호 변경"));

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith("/");
    });
  });
});
