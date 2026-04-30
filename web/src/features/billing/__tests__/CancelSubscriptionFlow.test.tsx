/** CancelSubscriptionFlow 단위 테스트 — Story 3.5. */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";

const mockMutateAsync = vi.fn();

vi.mock("../hooks/useCancelSubscription", () => ({
  useCancelSubscription: () => ({
    mutateAsync: mockMutateAsync,
    isPending: false,
  }),
}));

import { CancelSubscriptionFlow } from "../components/CancelSubscriptionFlow";

describe("CancelSubscriptionFlow", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

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

  it("isOpen=true 시 모달 + textarea + 두 버튼이 렌더된다", () => {
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
    expect(screen.getByText("취소")).toBeDefined();
  });

  it("빈 reason → Submit 버튼 disabled", () => {
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

  it("공백만 입력 시 Submit disabled 유지", () => {
    render(
      <CancelSubscriptionFlow
        isOpen={true}
        onClose={vi.fn()}
        currentPeriodEnd="2026-05-29T00:00:00+00:00"
      />
    );
    const textarea = screen.getByLabelText(
      "해지 사유를 알려주세요"
    ) as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "   " } });
    const submitBtn = screen.getByText("해지하기") as HTMLButtonElement;
    expect(submitBtn.disabled).toBe(true);
  });

  it("비공백 reason 입력 시 Submit enabled, 클릭하면 cancelSubscription 호출", async () => {
    mockMutateAsync.mockResolvedValue({
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

    const textarea = screen.getByLabelText(
      "해지 사유를 알려주세요"
    ) as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "사용 빈도 감소" } });

    const submitBtn = screen.getByText("해지하기") as HTMLButtonElement;
    expect(submitBtn.disabled).toBe(false);

    await act(async () => {
      fireEvent.click(submitBtn);
    });

    expect(mockMutateAsync).toHaveBeenCalledWith("사용 빈도 감소");
    await waitFor(() =>
      expect(screen.getByText("해지가 예약되었습니다")).toBeDefined()
    );
  });

  it("에러 발생 시 step='error', errorMessage 노출, '다시 시도' 클릭 → form 복귀", async () => {
    mockMutateAsync.mockRejectedValue(new Error("네트워크 오류"));

    render(
      <CancelSubscriptionFlow
        isOpen={true}
        onClose={vi.fn()}
        currentPeriodEnd="2026-05-29T00:00:00+00:00"
      />
    );

    const textarea = screen.getByLabelText(
      "해지 사유를 알려주세요"
    ) as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "사유" } });

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
    expect(mockMutateAsync).not.toHaveBeenCalled();
  });
});
