import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { PaymentEventDetailDrawer } from "@/features/admin-finance/components/PaymentEventDetailDrawer";
import * as api from "@/features/admin-finance/api/payments";

function withClient(children: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const sample: api.PaymentEventDetail = {
  event_id: 42,
  payment_id: 99,
  event_type: "charge_failed",
  charged_at: "2026-05-07T05:23:11+00:00",
  amount_krw: 9900,
  user_id: 7,
  user_email_masked: "u**@example.com",
  card_last4: "1234",
  card_company: "현대",
  provider_order_id: "sub-99-2026-05-07",
  provider_error_code: "INVALID_CARD_NUMBER",
  provider_error_message: "잘못된 카드번호",
  status: "failed",
  raw_response_json: { code: "INVALID_CARD_NUMBER", message: "잘못된 카드번호" },
};

describe("PaymentEventDetailDrawer", () => {
  beforeEach(() => {
    vi.spyOn(api, "fetchPaymentEventDetail").mockResolvedValue(sample);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("dialog role + aria-modal", async () => {
    render(
      withClient(
        <PaymentEventDetailDrawer eventId={42} onClose={vi.fn()} />,
      ),
    );
    await waitFor(() => screen.getByRole("dialog"));
    const dialog = screen.getByRole("dialog");
    expect(dialog.getAttribute("aria-modal")).toBe("true");
  });

  it("ESC 키 → onClose 호출", async () => {
    const onClose = vi.fn();
    render(
      withClient(
        <PaymentEventDetailDrawer eventId={42} onClose={onClose} />,
      ),
    );
    await waitFor(() => screen.getByRole("dialog"));
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  it("닫기 버튼 클릭 → onClose 호출", async () => {
    const onClose = vi.fn();
    render(
      withClient(
        <PaymentEventDetailDrawer eventId={42} onClose={onClose} />,
      ),
    );
    await waitFor(() => screen.getByRole("dialog"));
    fireEvent.click(screen.getByLabelText("닫기"));
    expect(onClose).toHaveBeenCalled();
  });

  it("raw_response_json 원본 렌더", async () => {
    render(
      withClient(
        <PaymentEventDetailDrawer eventId={42} onClose={vi.fn()} />,
      ),
    );
    // JSON viewer pre/code 블록에 stringified JSON이 있어야 함
    await waitFor(() => {
      const code = screen
        .getAllByText((_, el) => el?.tagName === "CODE")
        .find((el) => el.textContent?.includes('"code"'));
      expect(code?.textContent).toContain("INVALID_CARD_NUMBER");
    });
  });

  it("PG 에러 코드 영역 노출", async () => {
    render(
      withClient(
        <PaymentEventDetailDrawer eventId={42} onClose={vi.fn()} />,
      ),
    );
    await waitFor(() => screen.getByText("PG 에러"));
    expect(screen.getByText("잘못된 카드번호")).toBeTruthy();
  });
});
