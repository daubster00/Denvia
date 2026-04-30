/** PaymentStatusBadge 단위 테스트 — Story 4.4. */

import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { PaymentStatusBadge } from "../components/PaymentStatusBadge";

describe("PaymentStatusBadge", () => {
  it("status=success → '결제 완료' + aria-label", () => {
    render(<PaymentStatusBadge status="success" />);
    expect(screen.getByText("결제 완료")).toBeDefined();
    expect(screen.getByLabelText("결제 상태: 결제 완료")).toBeDefined();
  });

  it("status=failed → '실패'", () => {
    render(<PaymentStatusBadge status="failed" />);
    expect(screen.getByText("실패")).toBeDefined();
    expect(screen.getByLabelText("결제 상태: 실패")).toBeDefined();
  });

  it("status=refunded → '환불 완료'", () => {
    render(<PaymentStatusBadge status="refunded" />);
    expect(screen.getByText("환불 완료")).toBeDefined();
    expect(screen.getByLabelText("결제 상태: 환불 완료")).toBeDefined();
  });

  it("status=refund_pending → '환불 처리 중'", () => {
    render(<PaymentStatusBadge status="refund_pending" />);
    expect(screen.getByText("환불 처리 중")).toBeDefined();
    expect(screen.getByLabelText("결제 상태: 환불 처리 중")).toBeDefined();
  });

  it("status=pending → '처리 중'", () => {
    render(<PaymentStatusBadge status="pending" />);
    expect(screen.getByText("처리 중")).toBeDefined();
    expect(screen.getByLabelText("결제 상태: 처리 중")).toBeDefined();
  });
});
