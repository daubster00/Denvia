import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { PlanCard } from "../PlanCard";

vi.mock("@/features/billing/api", () => ({
  fetchCurrentSubscription: vi.fn(),
  resumeSubscription: vi.fn(),
  cancelSubscription: vi.fn(),
}));

const { fetchCurrentSubscription } = await import("@/features/billing/api");

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  vi.mocked(fetchCurrentSubscription).mockResolvedValue({
    status: "none",
    started_at: null,
    current_period_end: null,
    next_charge_at: null,
    canceled_at: null,
    cancel_reason: null,
  });
});

describe("PlanCard — Story 4.3 AC-2 / AC-4", () => {
  it("free + show_subscribe_button=true → 현재 플랜에는 구독하기 링크 미노출", () => {
    render(<PlanCard subscriptionStatus="free" showSubscribeButton={true} />, {
      wrapper,
    });
    expect(screen.getByText("Basic")).toBeDefined();
    expect(screen.queryByRole("link", { name: "구독하기" })).toBeNull();
  });

  it("free + show_subscribe_button=false → 구독하기 버튼 DOM 미마운트 (FR48)", () => {
    render(<PlanCard subscriptionStatus="free" showSubscribeButton={false} />, {
      wrapper,
    });
    expect(screen.getByText("Basic")).toBeDefined();
    expect(screen.queryByRole("link", { name: "구독하기" })).toBeNull();
  });

  it("pro → 'Pro — 무제한' 노출, 구독하기 버튼 미노출", () => {
    render(<PlanCard subscriptionStatus="pro" showSubscribeButton={false} />, {
      wrapper,
    });
    expect(screen.getByText("Pro — 무제한")).toBeDefined();
    expect(screen.queryByLabelText("Pro 플랜")).toBeNull();
    expect(screen.queryByRole("link", { name: "구독하기" })).toBeNull();
  });

  it("admin → '관리자(무제한)' + 구독하기 버튼 미노출", () => {
    render(<PlanCard subscriptionStatus="admin" showSubscribeButton={false} />, {
      wrapper,
    });
    expect(screen.getByText("관리자(무제한)")).toBeDefined();
    expect(screen.queryByRole("link", { name: "구독하기" })).toBeNull();
  });

  it("내부 500회 상한 노출 0건 (NFR-O5)", () => {
    render(<PlanCard subscriptionStatus="pro" showSubscribeButton={false} />, {
      wrapper,
    });
    expect(screen.queryByText(/500/)).toBeNull();
  });
});
