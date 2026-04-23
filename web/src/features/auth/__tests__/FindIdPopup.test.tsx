import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { FindIdPopup } from "../FindIdPopup";

vi.mock("@/features/auth/api", () => ({
  sendSmsOtp: vi.fn(),
  verifySmsOtp: vi.fn(),
  lookupId: vi.fn(),
}));

const mockOnBack = vi.fn();

beforeEach(() => {
  vi.resetAllMocks();
});

describe("FindIdPopup — 단계 전이", () => {
  it("1단계: 휴대폰 입력 화면이 렌더된다", () => {
    render(<FindIdPopup onBack={mockOnBack} />);
    expect(screen.getByText("인증번호 전송")).toBeTruthy();
    expect(screen.getByPlaceholderText("010-0000-0000")).toBeTruthy();
  });

  it("휴대폰 입력 후 인증번호 전송 → 2단계 OTP 화면으로 이동", async () => {
    const { sendSmsOtp } = await import("@/features/auth/api");
    vi.mocked(sendSmsOtp).mockResolvedValue({ sent_at: "", cooldown_seconds: 60, max_retries: 3 });

    render(<FindIdPopup onBack={mockOnBack} />);

    fireEvent.change(screen.getByPlaceholderText("010-0000-0000"), {
      target: { value: "010-1234-5678" },
    });
    fireEvent.click(screen.getByText("인증번호 전송"));

    await waitFor(() => {
      expect(screen.getByText(/인증번호를 전송했습니다/)).toBeTruthy();
    });
  });
});

describe("FindIdPopup — 결과 분기", () => {
  async function setupOtpVerified(lookupResult: {
    email_masked: string | null;
    signup_method: "email" | "kakao" | "google" | "naver" | "social" | null;
  }) {
    const { sendSmsOtp, verifySmsOtp, lookupId } = await import("@/features/auth/api");
    vi.mocked(sendSmsOtp).mockResolvedValue({ sent_at: "", cooldown_seconds: 60, max_retries: 3 });
    vi.mocked(verifySmsOtp).mockResolvedValue({ phone_verification_token: "token_abc" });
    vi.mocked(lookupId).mockResolvedValue(lookupResult);

    render(<FindIdPopup onBack={mockOnBack} />);

    fireEvent.change(screen.getByPlaceholderText("010-0000-0000"), {
      target: { value: "010-1234-5678" },
    });
    fireEvent.click(screen.getByText("인증번호 전송"));

    await waitFor(() => {
      expect(screen.getByText(/인증번호를 전송했습니다/)).toBeTruthy();
    });

    // OTP 6자리 입력 시뮬레이션 (각 input에 개별 입력)
    const inputs = screen.getAllByRole("textbox").filter(
      (el) => el.getAttribute("aria-label")?.startsWith("인증번호")
    );
    "123456".split("").forEach((digit, i) => {
      if (inputs[i]) {
        fireEvent.change(inputs[i], { target: { value: digit } });
      }
    });

    await waitFor(() => {
      expect(lookupId).toHaveBeenCalled();
    });
  }

  it("이메일 가입자 결과: 마스킹된 이메일 표시", async () => {
    await setupOtpVerified({ email_masked: "d****@denvia.com", signup_method: "email" });

    await waitFor(() => {
      expect(screen.getByText("d****@denvia.com")).toBeTruthy();
    });
    expect(screen.getByText(/이메일로 로그인해주세요/)).toBeTruthy();
  });

  it("소셜 가입자 결과: 소셜 로그인 안내 표시", async () => {
    await setupOtpVerified({ email_masked: "d****@denvia.com", signup_method: "social" });

    await waitFor(() => {
      expect(screen.getByText(/소셜 로그인을 이용해주세요/)).toBeTruthy();
    });
  });

  it("미가입자 결과: 가입 없음 안내 표시", async () => {
    await setupOtpVerified({ email_masked: null, signup_method: null });

    await waitFor(() => {
      expect(screen.getByText(/가입된 계정이 없거나/)).toBeTruthy();
    });
  });

  it("카카오 가입자 결과: 카카오 로그인 안내 표시", async () => {
    await setupOtpVerified({ email_masked: "d****@denvia.com", signup_method: "kakao" });

    await waitFor(() => {
      expect(screen.getByText(/카카오 계정으로 가입되어/)).toBeTruthy();
      expect(screen.getByText(/카카오 로그인을 이용해주세요/)).toBeTruthy();
    });
  });

  it("구글 가입자 결과: 구글 로그인 안내 표시", async () => {
    await setupOtpVerified({ email_masked: "d****@denvia.com", signup_method: "google" });

    await waitFor(() => {
      expect(screen.getByText(/구글 계정으로 가입되어/)).toBeTruthy();
      expect(screen.getByText(/구글 로그인을 이용해주세요/)).toBeTruthy();
    });
  });

  it("네이버 가입자 결과: 네이버 로그인 안내 표시", async () => {
    await setupOtpVerified({ email_masked: "d****@denvia.com", signup_method: "naver" });

    await waitFor(() => {
      expect(screen.getByText(/네이버 계정으로 가입되어/)).toBeTruthy();
      expect(screen.getByText(/네이버 로그인을 이용해주세요/)).toBeTruthy();
    });
  });
});
