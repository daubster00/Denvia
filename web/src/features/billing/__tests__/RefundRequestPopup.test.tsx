/** RefundRequestPopup 단위 테스트 — Story 3.6. */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";

const mockMutateAsync = vi.fn();

vi.mock("../hooks/useRequestRefund", () => ({
  useRequestRefund: () => ({
    mutateAsync: mockMutateAsync,
    isPending: false,
  }),
}));

import { RefundRequestPopup } from "../components/RefundRequestPopup";
import type { RefundPaymentInfo } from "../types";

const samplePayment: RefundPaymentInfo = {
  id: 200,
  amount_krw: 9900,
  charged_at: "2026-04-25T10:00:00+00:00",
  card_last4: "1234",
};

describe("RefundRequestPopup", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("isOpen=false 시 모달이 렌더되지 않는다", () => {
    const { container } = render(
      <RefundRequestPopup
        isOpen={false}
        onClose={vi.fn()}
        payment={samplePayment}
      />
    );
    expect(container.querySelector("[role='dialog']")).toBeNull();
  });

  it("isOpen=true 시 결제 정보 + textarea + 버튼이 렌더된다", () => {
    render(
      <RefundRequestPopup
        isOpen={true}
        onClose={vi.fn()}
        payment={samplePayment}
      />
    );
    expect(screen.getByRole("dialog")).toBeDefined();
    // 결제 금액 표시
    expect(screen.getByText("9,900원")).toBeDefined();
    // 카드 뒷자리 표시
    expect(screen.getByText("**** 1234")).toBeDefined();
    expect(screen.getByLabelText("환불 사유 (선택)")).toBeDefined();
    expect(screen.getByText("환불 요청하기")).toBeDefined();
    expect(screen.getByText("취소")).toBeDefined();
  });

  it("reason 빈 입력으로도 Submit 가능 (optional)", async () => {
    mockMutateAsync.mockResolvedValue({
      status: "refunded",
      amount_krw: 9900,
      refunded_at: "2026-04-29T12:00:00+00:00",
    });

    render(
      <RefundRequestPopup
        isOpen={true}
        onClose={vi.fn()}
        payment={samplePayment}
      />
    );

    const submitBtn = screen.getByText("환불 요청하기") as HTMLButtonElement;
    expect(submitBtn.disabled).toBe(false);

    await act(async () => {
      fireEvent.click(submitBtn);
    });

    expect(mockMutateAsync).toHaveBeenCalledWith({
      paymentId: 200,
      reason: undefined,
    });
  });

  it("자동 환불 성공 → done_refunded 상태로 전이", async () => {
    mockMutateAsync.mockResolvedValue({
      status: "refunded",
      amount_krw: 9900,
      refunded_at: "2026-04-29T12:00:00+00:00",
    });

    const onSuccess = vi.fn();
    render(
      <RefundRequestPopup
        isOpen={true}
        onClose={vi.fn()}
        payment={samplePayment}
        onSuccess={onSuccess}
      />
    );

    const textarea = screen.getByLabelText(
      "환불 사유 (선택)"
    ) as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "사용 안 함" } });

    await act(async () => {
      fireEvent.click(screen.getByText("환불 요청하기"));
    });

    await waitFor(() =>
      expect(screen.getByText("환불이 완료되었습니다")).toBeDefined()
    );
    expect(onSuccess).toHaveBeenCalledOnce();
    expect(mockMutateAsync).toHaveBeenCalledWith({
      paymentId: 200,
      reason: "사용 안 함",
    });
  });

  it("수동 검토 — period_exceeded 카피 표시", async () => {
    mockMutateAsync.mockResolvedValue({
      status: "queued_for_review",
      queue_id: 42,
      reason_code: "period_exceeded",
    });

    render(
      <RefundRequestPopup
        isOpen={true}
        onClose={vi.fn()}
        payment={samplePayment}
      />
    );

    await act(async () => {
      fireEvent.click(screen.getByText("환불 요청하기"));
    });

    await waitFor(() =>
      expect(screen.getByText("환불 요청이 접수되었습니다")).toBeDefined()
    );
    expect(
      screen.getByText(/결제 후 7일이 지나 자동 환불이 불가능합니다/)
    ).toBeDefined();
  });

  it("수동 검토 — qa_count_exceeded 카피 표시", async () => {
    mockMutateAsync.mockResolvedValue({
      status: "queued_for_review",
      queue_id: 43,
      reason_code: "qa_count_exceeded",
    });

    render(
      <RefundRequestPopup
        isOpen={true}
        onClose={vi.fn()}
        payment={samplePayment}
      />
    );

    await act(async () => {
      fireEvent.click(screen.getByText("환불 요청하기"));
    });

    await waitFor(() =>
      expect(
        screen.getByText(/구독 기간 동안 사용 이력이 있어/)
      ).toBeDefined()
    );
  });

  it("수동 검토 — both 카피 표시", async () => {
    mockMutateAsync.mockResolvedValue({
      status: "queued_for_review",
      queue_id: 44,
      reason_code: "both",
    });

    render(
      <RefundRequestPopup
        isOpen={true}
        onClose={vi.fn()}
        payment={samplePayment}
      />
    );

    await act(async () => {
      fireEvent.click(screen.getByText("환불 요청하기"));
    });

    await waitFor(() =>
      expect(
        screen.getByText(/결제 후 7일 \+ 사용 이력 모두 해당/)
      ).toBeDefined()
    );
  });

  it("502 에러 → 다시 시도 버튼 클릭 → form 복귀", async () => {
    mockMutateAsync.mockRejectedValue(
      new Error("BILLING_PROVIDER_UNAVAILABLE")
    );

    render(
      <RefundRequestPopup
        isOpen={true}
        onClose={vi.fn()}
        payment={samplePayment}
      />
    );

    await act(async () => {
      fireEvent.click(screen.getByText("환불 요청하기"));
    });

    await waitFor(() =>
      expect(
        screen.getByText("결제 서비스에 일시 지연이 있습니다. 잠시 후 다시 시도해주세요.")
      ).toBeDefined()
    );

    fireEvent.click(screen.getByText("다시 시도"));
    expect(screen.getByLabelText("환불 사유 (선택)")).toBeDefined();
  });

  it("409 REFUND_ALREADY_PROCESSED → 코드별 카피 표시", async () => {
    mockMutateAsync.mockRejectedValue(new Error("REFUND_ALREADY_PROCESSED"));

    render(
      <RefundRequestPopup
        isOpen={true}
        onClose={vi.fn()}
        payment={samplePayment}
      />
    );

    await act(async () => {
      fireEvent.click(screen.getByText("환불 요청하기"));
    });

    await waitFor(() =>
      expect(screen.getByText("이미 환불된 결제입니다.")).toBeDefined()
    );
  });

  it("'취소' 클릭 → onClose 호출, mutateAsync 미호출", () => {
    const onClose = vi.fn();
    render(
      <RefundRequestPopup
        isOpen={true}
        onClose={onClose}
        payment={samplePayment}
      />
    );
    fireEvent.click(screen.getByText("취소"));
    expect(onClose).toHaveBeenCalledOnce();
    expect(mockMutateAsync).not.toHaveBeenCalled();
  });

  it("card_last4 null → '정보 없음' 표시", () => {
    render(
      <RefundRequestPopup
        isOpen={true}
        onClose={vi.fn()}
        payment={{ ...samplePayment, card_last4: null }}
      />
    );
    expect(screen.getByText("정보 없음")).toBeDefined();
  });
});
