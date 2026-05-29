import { describe, it, expect, vi, beforeAll, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import SubscribersPage from "../page";

beforeAll(() => {
  // @ts-expect-error - jsdom polyfill
  global.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

vi.mock("@/features/admin-dashboard/api/analytics", () => ({
  fetchSubscribers: vi.fn(),
}));

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...rest
  }: {
    href: string;
    children: React.ReactNode;
  }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

function renderWithQuery(ui: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("SubscribersPage", () => {
  it("기본 렌더 — 헤더 + 도넛 + KPI", async () => {
    const { fetchSubscribers } = await import(
      "@/features/admin-dashboard/api/analytics"
    );
    (fetchSubscribers as ReturnType<typeof vi.fn>).mockResolvedValue({
      as_of: "2026-04-29T15:30:00+09:00",
      free_count: 134,
      pro_count: 12,
      blocked_count: 1,
      withdrawn_count: 7,
      pending_cancellation_count: 0,
      pending_cancellations: [],
    });

    renderWithQuery(<SubscribersPage />);
    expect(screen.getByRole("heading", { name: "구독 현황" })).toBeTruthy();
    await screen.findByText("134명");
    expect(screen.getByText(/2026-04-29 15:30 KST/)).toBeTruthy();
  });

  it("해지 예약 없음 → 비어있음 안내 노출", async () => {
    const { fetchSubscribers } = await import(
      "@/features/admin-dashboard/api/analytics"
    );
    (fetchSubscribers as ReturnType<typeof vi.fn>).mockResolvedValue({
      as_of: "2026-04-29T15:30:00+09:00",
      free_count: 5,
      pro_count: 1,
      blocked_count: 0,
      withdrawn_count: 0,
      pending_cancellation_count: 0,
      pending_cancellations: [],
    });

    renderWithQuery(<SubscribersPage />);
    await screen.findByText("5명");
    expect(
      screen.getByText(/현재 해지 예약된 구독이 없습니다/),
    ).toBeTruthy();
    expect(screen.getByText(/총 0건/)).toBeTruthy();
  });

  it("해지 예약 목록 — 행 + 종료 예정일 + D-카운트", async () => {
    const { fetchSubscribers } = await import(
      "@/features/admin-dashboard/api/analytics"
    );
    // 충분히 미래로 잡아 D-카운트가 양수가 되게 함 (테스트 안정성)
    const future = new Date(Date.now() + 1000 * 60 * 60 * 24 * 10).toISOString();
    (fetchSubscribers as ReturnType<typeof vi.fn>).mockResolvedValue({
      as_of: "2026-04-29T15:30:00+09:00",
      free_count: 10,
      pro_count: 3,
      blocked_count: 0,
      withdrawn_count: 0,
      pending_cancellation_count: 2,
      pending_cancellations: [
        {
          user_id: 1,
          email_masked: "a****@x.com",
          canceled_at: "2026-04-20T10:00:00+09:00",
          current_period_end: future,
        },
        {
          user_id: 2,
          email_masked: "b****@y.com",
          canceled_at: "2026-04-25T09:30:00+09:00",
          current_period_end: future,
        },
      ],
    });

    renderWithQuery(<SubscribersPage />);
    await screen.findByText("a****@x.com");
    expect(screen.getByText("b****@y.com")).toBeTruthy();
    expect(screen.getByText(/총 2건/)).toBeTruthy();
    expect(screen.getByText("2026-04-20")).toBeTruthy();
    // D-카운트는 "D-N" 또는 "오늘" 형식
    const dCells = screen.getAllByText(/^D-\d+$|^오늘$/);
    expect(dCells.length).toBeGreaterThanOrEqual(2);
  });

  it("4 KPI 합 = 전체 (시뮬레이션 응답 기준)", async () => {
    const { fetchSubscribers } = await import(
      "@/features/admin-dashboard/api/analytics"
    );
    (fetchSubscribers as ReturnType<typeof vi.fn>).mockResolvedValue({
      as_of: "2026-04-29T00:00:00+09:00",
      free_count: 10,
      pro_count: 5,
      blocked_count: 2,
      withdrawn_count: 3,
      pending_cancellation_count: 0,
      pending_cancellations: [],
    });

    renderWithQuery(<SubscribersPage />);
    await screen.findByText("10명");
    expect(screen.getByText("5명")).toBeTruthy();
    expect(screen.getByText("2명")).toBeTruthy();
    expect(screen.getByText("3명")).toBeTruthy();
  });

  it("API 실패 → role=alert", async () => {
    const { fetchSubscribers } = await import(
      "@/features/admin-dashboard/api/analytics"
    );
    (fetchSubscribers as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("network"),
    );
    renderWithQuery(<SubscribersPage />);
    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
  });
});
