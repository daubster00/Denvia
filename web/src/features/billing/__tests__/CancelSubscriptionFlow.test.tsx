/** CancelSubscriptionFlow 단위 테스트 — Story 3.5 + Story 3.6 v1.1. */

import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  act,
} from "@testing-library/react";

import type { RefundEligibilityResponse } from "../types";

const mockCancelMutateAsync = vi.fn();
const mockRefundMutateAsync = vi.fn();
const mockEligibility = vi.fn<() => {
  data: RefundEligibilityResponse | undefined;
  isLoading: boolean;
}>();

vi.mock("../hooks/useCancelSubscription", () => ({
  useCancelSubscription: () => ({
    mutateAsync: mockCancelMutateAsync,
    isPending: false,
  }),
}));

vi.mock("../hooks/useCancelWithRefund", () => ({
  useCancelWithRefund: () => ({
    mutateAsync: mockRefundMutateAsync,
    isPending: false,
  }),
}));

vi.mock("../hooks/useRefundEligibility", () => ({
  useRefundEligibility: () => mockEligibility(),
}));

import { CancelSubscriptionFlow } from "../components/CancelSubscriptionFlow";

const ELIGIBLE_OK: RefundEligibilityResponse = {
  eligible: true,
  payment_id: 123,
  amount_krw: 9900,
  charged_at: "2026-05-10T05:23:11+00:00",
  days_since_charge: 3,
  qa_count_during_period: 0,
  reason_code: "ok",
};

const NOT_ELIGIBLE_PERIOD: RefundEligibilityResponse = {
  eligible: false,
  payment_id: 123,
  amount_krw: 9900,
  charged_at: "2026-04-01T05:23:11+00:00",
  days_since_charge: 42,
  qa_count_during_period: 0,
  reason_code: "period_exceeded",
};

const NO_ACTIVE_PAYMENT: RefundEligibilityResponse = {
  eligible: false,
  payment_id: null,
  amount_krw: null,
  charged_at: null,
  days_since_charge: null,
  qa_count_during_period: null,
  reason_code: "no_active_payment",
};

beforeEach(() => {
  vi.clearAllMocks();
  mockEligibility.mockReturnValue({ data: NO_ACTIVE_PAYMENT, isLoading: false });
});

describe("CancelSubscriptionFlow — base (Story 3.5)", () => {
  it("isOpen=false 시 모달이 렌더되지 않는다", () => {
    const { container } = render(
      <CancelSubscriptionFlow
        isOpen={false}
        onClose={vi.fn()}
        currentPeriodEnd="2026-05-29T00:00:00+00:00"
      />
    );
    expect(container.querySelector("[role='dialog']")).toBeNull();
  });

  it("eligible=false + isOpen=true → textarea + '해지하기' 버튼만 노출", () => {
    render(
      <CancelSubscriptionFlow
        isOpen={true}
        onClose={vi.fn()}
        currentPeriodEnd="2026-05-29T00:00:00+00:00"
      />
    );
    expect(screen.getByRole("dialog")).toBeDefined();
    expect(screen.getByLabelText("해지 사유를 알려주세요")).toBeDefined();
    expect(screen.getByText("해지하기")).toBeDefined();
    // 라디오 옵션은 미노출
    expect(screen.queryByText(/지금 즉시 해지 \+ 전액 환불/)).toBeNull();
  });

  it("빈 reason → '해지하기' 버튼 disabled", () => {
    render(
      <CancelSubscriptionFlow
        isOpen={true}
        onClose={vi.fn()}
        currentPeriodEnd="2026-05-29T00:00:00+00:00"
      />
    );
    const submitBtn = screen.getByText("해지하기") as HTMLButtonElement;
    expect(submitBtn.disabled).toBe(true);
  });

  it("비공백 reason 입력 후 클릭 → cancelSubscription 호출 + 'done_canceled' step", async () => {
    mockCancelMutateAsync.mockResolvedValue({
      status: "cancel_pending",
      effective_at: "2026-05-29T00:00:00+00:00",
    });

    render(
      <CancelSubscriptionFlow
        isOpen={true}
        onClose={vi.fn()}
        currentPeriodEnd="2026-05-29T00:00:00+00:00"
      />
    );

    fireEvent.change(screen.getByLabelText("해지 사유를 알려주세요"), {
      target: { value: "사용 빈도 감소" },
    });

    await act(async () => {
      fireEvent.click(screen.getByText("해지하기"));
    });

    expect(mockCancelMutateAsync).toHaveBeenCalledWith("사용 빈도 감소");
    await waitFor(() =>
      expect(screen.getByText("해지가 예약되었습니다")).toBeDefined()
    );
  });

  it("일반 해지 에러 발생 → step='error' + '다시 시도' 클릭으로 form 복귀", async () => {
    mockCancelMutateAsync.mockRejectedValue(new Error("네트워크 오류"));

    render(
      <CancelSubscriptionFlow
        isOpen={true}
        onClose={vi.fn()}
        currentPeriodEnd="2026-05-29T00:00:00+00:00"
      />
    );

    fireEvent.change(screen.getByLabelText("해지 사유를 알려주세요"), {
      target: { value: "사유" },
    });

    await act(async () => {
      fireEvent.click(screen.getByText("해지하기"));
    });

    await waitFor(() => expect(screen.getByText("네트워크 오류")).toBeDefined());

    fireEvent.click(screen.getByText("다시 시도"));
    expect(screen.getByLabelText("해지 사유를 알려주세요")).toBeDefined();
  });

  it("'취소' 클릭 → onClose 호출, mutateAsync 미호출", () => {
    const onClose = vi.fn();
    render(
      <CancelSubscriptionFlow
        isOpen={true}
        onClose={onClose}
        currentPeriodEnd="2026-05-29T00:00:00+00:00"
      />
    );
    fireEvent.click(screen.getByText("취소"));
    expect(onClose).toHaveBeenCalledOnce();
    expect(mockCancelMutateAsync).not.toHaveBeenCalled();
  });
});

describe("CancelSubscriptionFlow — 청약철회 분기 (Story 3.6 v1.1)", () => {
  it("eligible=true → 두 옵션 라디오 + 환불 금액 안내 노출", () => {
    mockEligibility.mockReturnValue({ data: ELIGIBLE_OK, isLoading: false });

    render(
      <CancelSubscriptionFlow
        isOpen={true}
        onClose={vi.fn()}
        currentPeriodEnd="2026-05-29T00:00:00+00:00"
      />
    );

    expect(screen.getByText("다음 결제일까지 이용 후 종료")).toBeDefined();
    expect(screen.getByText("지금 즉시 해지 + 전액 환불")).toBeDefined();
    expect(screen.getByText(/9,900원/)).toBeDefined();
  });

  it("cooling_off 옵션 선택 → submit 카피 변경 + textarea 미노출", () => {
    mockEligibility.mockReturnValue({ data: ELIGIBLE_OK, isLoading: false });

    render(
      <CancelSubscriptionFlow
        isOpen={true}
        onClose={vi.fn()}
        currentPeriodEnd="2026-05-29T00:00:00+00:00"
      />
    );

    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    fireEvent.click(radios[1]);

    expect(
      screen.getAllByText("지금 즉시 해지 + 전액 환불").length
    ).toBeGreaterThan(0);
    expect(screen.queryByLabelText("해지 사유를 알려주세요")).toBeNull();
  });

  it("cooling_off submit → cancelSubscriptionWithRefund 호출 + 'done_refunded' step", async () => {
    mockEligibility.mockReturnValue({ data: ELIGIBLE_OK, isLoading: false });
    mockRefundMutateAsync.mockResolvedValue({
      status: "refunded",
      refund_kind: "cooling_off",
      amount_krw: 9900,
      refunded_at: "2026-05-13T10:00:00+00:00",
      subscription_status: "canceled",
    });

    render(
      <CancelSubscriptionFlow
        isOpen={true}
        onClose={vi.fn()}
        currentPeriodEnd="2026-05-29T00:00:00+00:00"
      />
    );

    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    fireEvent.click(radios[1]);

    const submitBtns = screen.getAllByText("지금 즉시 해지 + 전액 환불");
    const submitBtn = submitBtns.find(
      (el) => el.tagName === "BUTTON"
    ) as HTMLButtonElement;

    await act(async () => {
      fireEvent.click(submitBtn);
    });

    expect(mockRefundMutateAsync).toHaveBeenCalledOnce();
    expect(mockCancelMutateAsync).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(screen.getByText("환불이 완료되었습니다")).toBeDefined()
    );
    expect(screen.getByText(/9,900원이 결제 수단으로 환불/)).toBeDefined();
  });

  it("cooling_off 502 응답 → step='error' + 다시 시도 가능", async () => {
    mockEligibility.mockReturnValue({ data: ELIGIBLE_OK, isLoading: false });
    mockRefundMutateAsync.mockRejectedValue(
      new Error("결제 서비스에 일시 지연이 있습니다. 잠시 후 다시 시도해주세요.")
    );

    render(
      <CancelSubscriptionFlow
        isOpen={true}
        onClose={vi.fn()}
        currentPeriodEnd="2026-05-29T00:00:00+00:00"
      />
    );

    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    fireEvent.click(radios[1]);

    const submitBtns = screen.getAllByText("지금 즉시 해지 + 전액 환불");
    const submitBtn = submitBtns.find(
      (el) => el.tagName === "BUTTON"
    ) as HTMLButtonElement;

    await act(async () => {
      fireEvent.click(submitBtn);
    });

    await waitFor(() =>
      expect(screen.getByText(/결제 서비스에 일시 지연이 있습니다/)).toBeDefined()
    );
    expect(screen.getByText("다시 시도")).toBeDefined();
  });

  it("eligible=false (period_exceeded) → 1:1 문의 안내 카피 노출", () => {
    mockEligibility.mockReturnValue({
      data: NOT_ELIGIBLE_PERIOD,
      isLoading: false,
    });

    render(
      <CancelSubscriptionFlow
        isOpen={true}
        onClose={vi.fn()}
        currentPeriodEnd="2026-05-29T00:00:00+00:00"
      />
    );

    expect(screen.queryByText("지금 즉시 해지 + 전액 환불")).toBeNull();
    expect(screen.getByText("1:1 문의")).toBeDefined();
    expect(screen.getByText(/환불이 필요하신 경우/)).toBeDefined();
  });
});
