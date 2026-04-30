import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { FeedbackSummaryWidget } from "../FeedbackSummaryWidget";

vi.mock("../../api/analytics", () => ({
  fetchFeedback: vi.fn(),
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

function renderWithQuery(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("FeedbackSummaryWidget", () => {
  it("로딩 상태 → WidgetLoadingState 표시", async () => {
    const { fetchFeedback } = await import("../../api/analytics");
    (fetchFeedback as ReturnType<typeof vi.fn>).mockImplementation(
      () => new Promise(() => {})
    );
    renderWithQuery(<FeedbackSummaryWidget />);
    expect(screen.getByText(/로딩 중/)).toBeTruthy();
  });

  it("실데이터 — GOOD/BAD 카운트 + 비율 렌더", async () => {
    const { fetchFeedback } = await import("../../api/analytics");
    (fetchFeedback as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      unit: "month",
      from: "2025-05-01",
      to: "2026-04-30",
      rating_filter: "all",
      summary: { good_count: 120, bad_count: 34, good_ratio: 0.779 },
      series: [],
      items: [],
      page: 1,
      per_page: 1,
      total: 154,
    });
    renderWithQuery(<FeedbackSummaryWidget />);
    await screen.findByText("120건");
    expect(screen.getByText("34건")).toBeTruthy();
    expect(screen.getByText("77.9%")).toBeTruthy();
  });

  it("오류 상태 → WidgetErrorState 표시", async () => {
    const { fetchFeedback } = await import("../../api/analytics");
    (fetchFeedback as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error("network")
    );
    renderWithQuery(<FeedbackSummaryWidget />);
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeTruthy();
    });
  });

  it("상세 링크 /admin/dashboard/analytics/feedback 포함", async () => {
    const { fetchFeedback } = await import("../../api/analytics");
    (fetchFeedback as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      unit: "month",
      from: "2025-05-01",
      to: "2026-04-30",
      rating_filter: "all",
      summary: { good_count: 5, bad_count: 2, good_ratio: 0.714 },
      series: [],
      items: [],
      page: 1,
      per_page: 1,
      total: 7,
    });
    renderWithQuery(<FeedbackSummaryWidget />);
    await screen.findByText("5건");
    const link = screen.getByRole("link", { name: /피드백 비율 상세 페이지로 이동/ });
    expect(link.getAttribute("href")).toBe("/admin/dashboard/analytics/feedback");
  });
});
