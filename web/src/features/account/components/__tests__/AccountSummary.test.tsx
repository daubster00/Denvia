import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { AccountSummary } from "../AccountSummary";

vi.mock("../../api", () => ({
  fetchUsageSummary: vi.fn(),
}));

vi.mock("@/features/billing/api", () => ({
  fetchCurrentSubscription: vi.fn(),
}));

const { fetchUsageSummary } = await import("../../api");
const { fetchCurrentSubscription } = await import("@/features/billing/api");

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  vi.mocked(fetchUsageSummary).mockReset();
  vi.mocked(fetchCurrentSubscription).mockReset();
});

async function flushAsync() {
  await new Promise((r) => setTimeout(r, 0));
  await new Promise((r) => setTimeout(r, 0));
}

describe("AccountSummary — Story 4.3 AC-2 분기", () => {
  it("free + show_subscribe_button=true → 4개 카드(플랜·사용량·가입유형) + 구독하기", async () => {
    vi.mocked(fetchUsageSummary).mockResolvedValue({
      month_question_count: 12,
      daily_used: 3,
      daily_limit: 10,
      daily_remaining: 7,
      daily_reset_at: "2026-05-01T00:00:00+09:00",
      subscription_status: "free",
      segment: "doctor",
      years_of_experience: 5,
      show_subscribe_button: true,
    });
    vi.mocked(fetchCurrentSubscription).mockResolvedValue({
      status: "none",
      started_at: null,
      current_period_end: null,
      next_charge_at: null,
      canceled_at: null,
      cancel_reason: null,
    });

    render(<AccountSummary />, { wrapper });
    await flushAsync();
    await flushAsync();

    expect(screen.getByText("Basic")).toBeDefined();
    expect(screen.getByText("이번 달 질문")).toBeDefined();
    expect(screen.getByText(/12회/)).toBeDefined();
    expect(screen.getByText(/3\/10회/)).toBeDefined();
    expect(screen.getByText("치과의사")).toBeDefined();
    expect(screen.getByRole("link", { name: "구독하기" })).toBeDefined();
  });

  it("pro → 당일 사용량 카드 미렌더 (월 카운트만 표시)", async () => {
    vi.mocked(fetchUsageSummary).mockResolvedValue({
      month_question_count: 250,
      daily_used: 0,
      daily_limit: 0,
      daily_remaining: 0,
      daily_reset_at: "2026-05-01T00:00:00+09:00",
      subscription_status: "pro",
      segment: "doctor",
      years_of_experience: 10,
      show_subscribe_button: false,
    });
    vi.mocked(fetchCurrentSubscription).mockResolvedValue({
      status: "active",
      started_at: "2026-04-01T00:00:00+09:00",
      current_period_end: "2026-05-01T00:00:00+09:00",
      next_charge_at: "2026-05-01T00:00:00+09:00",
      canceled_at: null,
      cancel_reason: null,
    });

    render(<AccountSummary />, { wrapper });
    await flushAsync();
    await flushAsync();

    expect(screen.getByText("Pro — 무제한")).toBeDefined();
    expect(screen.getByText(/250회/)).toBeDefined();
    expect(screen.queryByText(/오늘 사용량/)).toBeNull();
    expect(screen.queryByRole("link", { name: "구독하기" })).toBeNull();
  });

  it("cancel_pending → '해지 예정' 카드 노출", async () => {
    vi.mocked(fetchUsageSummary).mockResolvedValue({
      month_question_count: 50,
      daily_used: 0,
      daily_limit: 0,
      daily_remaining: 0,
      daily_reset_at: "2026-05-01T00:00:00+09:00",
      subscription_status: "pro",
      segment: "doctor",
      years_of_experience: 5,
      show_subscribe_button: false,
    });
    vi.mocked(fetchCurrentSubscription).mockResolvedValue({
      status: "cancel_pending",
      started_at: "2026-04-01T00:00:00+09:00",
      current_period_end: "2026-05-15T00:00:00+09:00",
      next_charge_at: null,
      canceled_at: "2026-04-25T00:00:00+09:00",
      cancel_reason: "user_request",
    });

    render(<AccountSummary />, { wrapper });
    await flushAsync();
    await flushAsync();

    expect(screen.getByText(/해지 예정/)).toBeDefined();
    expect(screen.getByText(/2026-05-15/)).toBeDefined();
  });

  it("segment is null → 가입유형 카드가 '회원 정보 완성' 안내로 분기", async () => {
    vi.mocked(fetchUsageSummary).mockResolvedValue({
      month_question_count: 0,
      daily_used: 0,
      daily_limit: 10,
      daily_remaining: 10,
      daily_reset_at: "2026-05-01T00:00:00+09:00",
      subscription_status: "free",
      segment: null,
      years_of_experience: null,
      show_subscribe_button: true,
    });
    vi.mocked(fetchCurrentSubscription).mockResolvedValue({
      status: "none",
      started_at: null,
      current_period_end: null,
      next_charge_at: null,
      canceled_at: null,
      cancel_reason: null,
    });

    render(<AccountSummary />, { wrapper });
    await flushAsync();
    await flushAsync();

    expect(screen.getByText("회원 정보를 완성해주세요.")).toBeDefined();
    const link = screen.getByRole("link", { name: "가입유형 설정하기" });
    expect(link.getAttribute("href")).toBe("/signup/segment");
  });

  it("admin → '관리자(무제한)' 노출 + SubscriptionCard fetch 비활성화 (mock 호출 0회)", async () => {
    vi.mocked(fetchUsageSummary).mockResolvedValue({
      month_question_count: 5,
      daily_used: 0,
      daily_limit: 999999,
      daily_remaining: 999999,
      daily_reset_at: "2026-05-01T00:00:00+09:00",
      subscription_status: "admin",
      segment: null,
      years_of_experience: null,
      show_subscribe_button: false,
    });
    vi.mocked(fetchCurrentSubscription).mockResolvedValue({
      status: "none",
      started_at: null,
      current_period_end: null,
      next_charge_at: null,
      canceled_at: null,
      cancel_reason: null,
    });

    render(<AccountSummary />, { wrapper });
    await flushAsync();
    await flushAsync();

    expect(screen.getByText("관리자(무제한)")).toBeDefined();
    expect(vi.mocked(fetchCurrentSubscription)).not.toHaveBeenCalled();
  });
});
