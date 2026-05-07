import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { AdminLogTimeline } from "@/features/admin-finance/components/AdminLogTimeline";
import type { PaymentEventItem } from "@/features/admin-finance/api/payments";

function makeEvent(overrides: Partial<PaymentEventItem> = {}): PaymentEventItem {
  return {
    event_id: 1,
    payment_id: 11,
    event_type: "charge_failed",
    charged_at: "2026-05-07T05:23:11+00:00",
    amount_krw: 9900,
    user_id: 42,
    user_email_masked: "u**@example.com",
    card_last4: "1234",
    card_company: "현대",
    provider_order_id: "sub-11-2026-05-07",
    provider_error_code: "INVALID_CARD_NUMBER",
    provider_error_message: "잘못된 카드번호",
    status: "failed",
    ...overrides,
  };
}

describe("AdminLogTimeline", () => {
  it("isLoading=true 일 때 status 메시지", () => {
    render(<AdminLogTimeline events={[]} onRowClick={vi.fn()} isLoading />);
    expect(screen.getByRole("status").textContent).toContain("불러오는 중");
  });

  it("events 비어있으면 emptyMessage 노출", () => {
    render(
      <AdminLogTimeline
        events={[]}
        onRowClick={vi.fn()}
        emptyMessage="없음"
      />,
    );
    expect(screen.getByRole("status").textContent).toBe("없음");
  });

  it("row 클릭 시 onRowClick 호출", () => {
    const onClick = vi.fn();
    const ev = makeEvent();
    render(<AdminLogTimeline events={[ev]} onRowClick={onClick} />);
    const row = screen.getByRole("button", { name: /결제 이벤트 #1 상세 보기/ });
    fireEvent.click(row);
    expect(onClick).toHaveBeenCalledWith(ev);
  });

  it("Enter 키 → onRowClick 호출", () => {
    const onClick = vi.fn();
    const ev = makeEvent({ event_id: 7 });
    render(<AdminLogTimeline events={[ev]} onRowClick={onClick} />);
    const row = screen.getByRole("button", { name: /결제 이벤트 #7 상세 보기/ });
    fireEvent.keyDown(row, { key: "Enter" });
    expect(onClick).toHaveBeenCalledWith(ev);
  });

  it("Space 키 → onRowClick 호출", () => {
    const onClick = vi.fn();
    const ev = makeEvent({ event_id: 8 });
    render(<AdminLogTimeline events={[ev]} onRowClick={onClick} />);
    const row = screen.getByRole("button", { name: /결제 이벤트 #8 상세 보기/ });
    fireEvent.keyDown(row, { key: " " });
    expect(onClick).toHaveBeenCalledWith(ev);
  });

  it("groupByDate=true (기본) 일 때 날짜 헤딩 노출", () => {
    render(
      <AdminLogTimeline
        events={[makeEvent({ event_id: 1 }), makeEvent({ event_id: 2 })]}
        onRowClick={vi.fn()}
      />,
    );
    expect(screen.getAllByRole("heading", { level: 3 }).length).toBeGreaterThan(0);
  });

  it("PG 에러 코드 셀에 코드 노출", () => {
    render(
      <AdminLogTimeline
        events={[makeEvent({ provider_error_code: "EXPIRED_CARD" })]}
        onRowClick={vi.fn()}
      />,
    );
    expect(screen.getByText("EXPIRED_CARD")).toBeTruthy();
  });
});
