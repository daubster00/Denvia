import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";

const ORIGINAL = process.env.NEXT_PUBLIC_KAKAO_CHANNEL_URL;

beforeEach(() => {
  vi.resetModules();
});

afterEach(() => {
  if (ORIGINAL === undefined) {
    delete process.env.NEXT_PUBLIC_KAKAO_CHANNEL_URL;
  } else {
    process.env.NEXT_PUBLIC_KAKAO_CHANNEL_URL = ORIGINAL;
  }
});

describe("CustomerInquiryFAB — 환경변수 분기 (AC-3)", () => {
  it("NEXT_PUBLIC_KAKAO_CHANNEL_URL 미설정 시 null 반환 — 위젯 비렌더", async () => {
    delete process.env.NEXT_PUBLIC_KAKAO_CHANNEL_URL;
    const { CustomerInquiryFAB } = await import("../CustomerInquiryFAB");
    const { container } = render(<CustomerInquiryFAB />);
    expect(container.firstChild).toBeNull();
  });

  it("빈 문자열도 미설정으로 간주 — 위젯 비렌더", async () => {
    process.env.NEXT_PUBLIC_KAKAO_CHANNEL_URL = "";
    const { CustomerInquiryFAB } = await import("../CustomerInquiryFAB");
    const { container } = render(<CustomerInquiryFAB />);
    expect(container.firstChild).toBeNull();
  });

  it("환경변수 설정 시 aria-label과 함께 버튼 렌더 + 클릭 시 noopener,noreferrer로 새 탭 열기", async () => {
    process.env.NEXT_PUBLIC_KAKAO_CHANNEL_URL = "https://pf.kakao.com/_test/chat";
    const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);
    const { CustomerInquiryFAB } = await import("../CustomerInquiryFAB");

    render(<CustomerInquiryFAB />);
    const btn = screen.getByRole("button", {
      name: "고객문의 — 카카오톡 채널 열기",
    });
    btn.click();

    expect(openSpy).toHaveBeenCalledWith(
      "https://pf.kakao.com/_test/chat",
      "_blank",
      "noopener,noreferrer"
    );
    openSpy.mockRestore();
  });
});
