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
      pending_cancellation_count: null,
      upcoming_renewals: [],
    });

    renderWithQuery(<SubscribersPage />);
    expect(screen.getByRole("heading", { name: "구독 현황" })).toBeTruthy();
    await screen.findByText("134명");
    expect(screen.getByText(/2026-04-29 15:30 KST/)).toBeTruthy();
  });

  it("HOLD-PG 자리 — 'PG 연동 후 표시됩니다' 메시지 노출", async () => {
    const { fetchSubscribers } = await import(
      "@/features/admin-dashboard/api/analytics"
    );
    (fetchSubscribers as ReturnType<typeof vi.fn>).mockResolvedValue({
      as_of: "2026-04-29T15:30:00+09:00",
      free_count: 5,
      pro_count: 1,
      blocked_count: 0,
      withdrawn_count: 0,
      pending_cancellation_count: null,
      upcoming_renewals: [],
    });

    renderWithQuery(<SubscribersPage />);
    await screen.findByText("5명");
    expect(
      screen.getByText(/유료 종결 예정 리스트는 PG 연동 후 표시됩니다/),
    ).toBeTruthy();
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
      pending_cancellation_count: null,
      upcoming_renewals: [],
    });

    renderWithQuery(<SubscribersPage />);
    await screen.findByText("10명");
    expect(screen.getByText("5명")).toBeTruthy();
    expect(screen.getByText("2명")).toBeTruthy();
    expect(screen.getByText("3명")).toBeTruthy();
    // 합 검증은 컴포넌트가 노출하지 않으므로, KPI 4개 모두 확인
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
