import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BudgetSummaryWidget } from "../BudgetSummaryWidget";

vi.mock("../../api/budget", () => ({
  fetchBudgetCurrentMonth: vi.fn(),
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

describe("BudgetSummaryWidget", () => {
  it("로딩 상태 → '로딩 중…' 표시", async () => {
    const { fetchBudgetCurrentMonth } = await import("../../api/budget");
    (fetchBudgetCurrentMonth as ReturnType<typeof vi.fn>).mockImplementation(
      () => new Promise(() => {}),
    );
    renderWithQuery(<BudgetSummaryWidget />);
    expect(screen.getByText(/로딩 중/)).toBeTruthy();
  });

  it("실데이터 — 게이지·금액·상세 링크 렌더", async () => {
    const { fetchBudgetCurrentMonth } = await import("../../api/budget");
    (fetchBudgetCurrentMonth as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      year_month: "2026-04",
      monthly_limit_usd: "100.00",
      spent_usd: "42.50",
      monthly_limit_krw: 140_000,
      spent_krw: 59_500,
      usd_to_krw: 1400,
      percent: 42.5,
      status: "normal",
      killswitch_active: false,
      killswitch_mode: null,
    });

    renderWithQuery(<BudgetSummaryWidget />);

    await screen.findByText("₩59,500");
    expect(screen.getByText("₩140,000")).toBeTruthy();
    expect(screen.getByText("₩80,500")).toBeTruthy(); // 남은 예산 = 140000 - 59500
    expect(screen.getByText("2026-04")).toBeTruthy();
    const link = screen.getByRole("link");
    expect(link.getAttribute("href")).toBe("/admin/dashboard/budget");
    expect(screen.getByRole("progressbar")).toBeTruthy();
  });

  it("status=warning → caption 색상 클래스 적용", async () => {
    const { fetchBudgetCurrentMonth } = await import("../../api/budget");
    (fetchBudgetCurrentMonth as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      year_month: "2026-04",
      monthly_limit_usd: "100.00",
      spent_usd: "85.00",
      monthly_limit_krw: 140_000,
      spent_krw: 119_000,
      usd_to_krw: 1400,
      percent: 85,
      status: "warning",
      killswitch_active: false,
      killswitch_mode: null,
    });
    const { container } = renderWithQuery(<BudgetSummaryWidget />);
    await screen.findByText("₩119,000");
    const warningClass = container.querySelector('[class*="figureValueWarning"]');
    expect(warningClass).not.toBeNull();
  });

  it("API 실패 → 오류 + 재시도 버튼", async () => {
    const { fetchBudgetCurrentMonth } = await import("../../api/budget");
    (fetchBudgetCurrentMonth as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error("network"),
    );
    renderWithQuery(<BudgetSummaryWidget />);
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeTruthy();
    });
    const retry = screen.getByText("다시 시도");
    expect(retry).toBeTruthy();
    fireEvent.click(retry);
  });
});
