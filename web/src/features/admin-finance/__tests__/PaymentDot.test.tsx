import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import {
  PaymentDot,
  getPaymentEventMeta,
} from "@/features/admin-finance/components/PaymentDot";
import type { PaymentEventType } from "@/features/admin-finance/api/payments";

describe("getPaymentEventMeta", () => {
  it("7가지 event_type 모두 한글 라벨 + toneClass 매핑", () => {
    const cases: Array<[PaymentEventType, string, string]> = [
      ["charge_requested", "결제 요청", "neutral"],
      ["charge_success", "결제 완료", "success"],
      ["charge_failed", "결제 실패", "chargeFailed"],
      ["retry_scheduled", "재시도 예약", "warning"],
      ["refund_requested", "환불 요청", "refundPending"],
      ["refund_success", "환불 완료", "refunded"],
      ["refund_denied", "환불 거절", "failed"],
    ];
    for (const [type, label, toneClass] of cases) {
      const meta = getPaymentEventMeta(type);
      expect(meta.label).toBe(label);
      expect(meta.toneClass).toBe(toneClass);
    }
  });
});

describe("PaymentDot", () => {
  it("기본 aria-label은 한글 라벨", () => {
    const { container } = render(<PaymentDot type="charge_failed" />);
    const dot = container.querySelector("[role='img']")!;
    expect(dot.getAttribute("aria-label")).toBe("결제 실패");
  });

  it("외부 ariaLabel 주입 시 우선 사용", () => {
    const { container } = render(
      <PaymentDot type="charge_success" ariaLabel="custom" />,
    );
    const dot = container.querySelector("[role='img']")!;
    expect(dot.getAttribute("aria-label")).toBe("custom");
  });
});
