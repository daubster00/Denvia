import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PhoneVerifyClient } from "../PhoneVerifyClient";

const mockPush = vi.fn();
const mockReplace = vi.fn();
let mockToken: string | null = "pending_abc";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, replace: mockReplace }),
  useSearchParams: () => ({
    get: (key: string) => (key === "token" ? mockToken : null),
  }),
}));

vi.mock("@/features/auth/api", () => ({
  sendSmsOtp: vi.fn(),
  verifySmsOtp: vi.fn(),
  completeOAuthSignup: vi.fn(),
}));

function renderWithProviders(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  vi.resetAllMocks();
  mockToken = "pending_abc";
  mockPush.mockReset();
  mockReplace.mockReset();
});

describe("PhoneVerifyClient — 라우트 가드", () => {
  it("token 누락 시 /?oauth_error=OAUTH_PENDING_EXPIRED로 replace", async () => {
    mockToken = null;
    renderWithProviders(<PhoneVerifyClient />);
    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith(
        "/?oauth_error=OAUTH_PENDING_EXPIRED"
      );
    });
  });
});

describe("PhoneVerifyClient — 3단계 전이", () => {
  it("휴대폰 입력 → 인증번호 받기 클릭 → OTP 단계 전이", async () => {
    const { sendSmsOtp } = await import("@/features/auth/api");
    vi.mocked(sendSmsOtp).mockResolvedValue({
      sent_at: "",
      cooldown_seconds: 60,
      max_retries: 3,
    });

    renderWithProviders(<PhoneVerifyClient />);

    fireEvent.change(screen.getByPlaceholderText("010-0000-0000"), {
      target: { value: "010-1234-5678" },
    });
    fireEvent.click(screen.getByText("인증번호 받기"));

    await waitFor(() => {
      expect(screen.getByText(/가입 완료/)).toBeTruthy();
    });
  });

  it("OAUTH_PHONE_COLLISION → /?oauth_error=OAUTH_PHONE_COLLISION으로 push (AC-7 spec)", async () => {
    const { sendSmsOtp, verifySmsOtp, completeOAuthSignup } = await import(
      "@/features/auth/api"
    );
    vi.mocked(sendSmsOtp).mockResolvedValue({
      sent_at: "",
      cooldown_seconds: 60,
      max_retries: 3,
    });
    vi.mocked(verifySmsOtp).mockResolvedValue({
      phone_verification_token: "pvt",
    });

    const { ApiError } = await import("@/types/api");
    vi.mocked(completeOAuthSignup).mockRejectedValue(
      new ApiError({
        code: "OAUTH_PHONE_COLLISION",
        message: "phone dup",
        trace_id: "",
      })
    );

    renderWithProviders(<PhoneVerifyClient />);

    fireEvent.change(screen.getByPlaceholderText("010-0000-0000"), {
      target: { value: "010-1234-5678" },
    });
    fireEvent.click(screen.getByText("인증번호 받기"));

    // OTP 6자리
    await waitFor(() => {
      expect(screen.queryAllByRole("textbox").length).toBeGreaterThan(0);
    });
    const inputs = screen
      .getAllByRole("textbox")
      .filter((el) =>
        el.getAttribute("aria-label")?.startsWith("인증번호")
      );
    "123456".split("").forEach((d, i) => {
      if (inputs[i]) fireEvent.change(inputs[i], { target: { value: d } });
    });

    await waitFor(() => {
      expect(verifySmsOtp).toHaveBeenCalled();
    });

    // "가입 완료" 활성화 대기
    const completeBtn = await screen.findByText("가입 완료");
    fireEvent.click(completeBtn);

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith(
        "/?oauth_error=OAUTH_PHONE_COLLISION"
      );
    });
  });
});
