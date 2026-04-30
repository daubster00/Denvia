/** BillingKeyForm 단위 테스트 — Story 3.2. */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

const { requestBillingAuthMock, paymentMock } = vi.hoisted(() => {
  const requestBillingAuthMock = vi.fn().mockResolvedValue(undefined);
  const paymentMock = vi.fn(() => ({
    requestBillingAuth: requestBillingAuthMock,
  }));
  return { requestBillingAuthMock, paymentMock };
});

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

vi.mock("@tosspayments/tosspayments-sdk", () => ({
  loadTossPayments: vi.fn(async () => ({
    payment: paymentMock,
  })),
}));

vi.mock("@/stores/session-store", () => ({
  useSessionStore: (selector: (s: unknown) => unknown) => {
    const state = { user: null, openPopup: vi.fn(), setUser: vi.fn() };
    return selector(state);
  },
}));

import { BillingKeyForm } from "../components/BillingKeyForm";

describe("BillingKeyForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    requestBillingAuthMock.mockResolvedValue(undefined);
    vi.stubEnv("NEXT_PUBLIC_TOSS_CLIENT_KEY", "test_ck_123");
  });

  it("isOpen=false 시 모달이 렌더되지 않는다", () => {
    const { container } = render(
      <BillingKeyForm isOpen={false} onClose={vi.fn()} />
    );
    expect(container.querySelector("[role='dialog']")).toBeNull();
  });

  it("isOpen=true 시 모달이 렌더된다", () => {
    render(<BillingKeyForm isOpen={true} onClose={vi.fn()} />);
    expect(screen.getByRole("dialog")).toBeDefined();
  });

  it("'카드 등록하고 Pro 시작하기' 버튼이 렌더된다", () => {
    render(<BillingKeyForm isOpen={true} onClose={vi.fn()} />);
    expect(screen.getByText("카드 등록하고 Pro 시작하기")).toBeDefined();
  });

  it("닫기 버튼 클릭 시 onClose가 호출된다", () => {
    const onClose = vi.fn();
    render(<BillingKeyForm isOpen={true} onClose={onClose} />);
    fireEvent.click(screen.getByLabelText("닫기"));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("초기 step='processing'으로 주입 시 스피너 상태가 렌더된다", () => {
    render(
      <BillingKeyForm isOpen={true} onClose={vi.fn()} initialStep="processing" />
    );
    expect(screen.getByText("결제 처리 중...")).toBeDefined();
  });

  it("토스 자동결제 등록 요청에 billing auth 파라미터를 전달한다", async () => {
    render(<BillingKeyForm isOpen={true} onClose={vi.fn()} />);

    fireEvent.click(screen.getByText("카드 등록하고 Pro 시작하기"));

    await waitFor(() => expect(requestBillingAuthMock).toHaveBeenCalledOnce());
    expect(requestBillingAuthMock).toHaveBeenCalledWith({
      method: "CARD",
      successUrl: `${window.location.origin}/subscribe?step=billing_auth_ok`,
      failUrl: `${window.location.origin}/subscribe?step=billing_auth_fail`,
    });
  });
});
