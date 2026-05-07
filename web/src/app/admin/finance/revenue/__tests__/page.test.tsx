import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import RevenueDashboardPage from "../page";

vi.mock("@/features/admin-dashboard/api/analytics", () => ({
  fetchRevenueVariance: vi.fn(),
  fetchRevenueVarianceSeries: vi.fn(),
  fetchRevenueVarianceExport: vi.fn(),
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
  return render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

const baseMonth = {
  year_month: "2026-05",
  revenue_krw: 1_485_000,
  token_cost_usd: "12.345600",
  token_cost_krw: 17_284,
  usd_to_krw: 1400,
  variance_krw: 1_467_716,
  error_count: 3,
  anomaly_count: 12,
  applied_filters: {
    year_month: "2026-05",
    kst_start: "2026-05-01T00:00:00+09:00",
    kst_end_exclusive: "2026-06-01T00:00:00+09:00",
  },
};

const baseSeries = {
  months: 12,
  to: "2026-05",
  from: "2025-06",
  usd_to_krw: 1400,
  items: Array.from({ length: 12 }, (_, i) => ({
    year_month: `2025-${String((i + 6) % 12 || 12).padStart(2, "0")}`,
    revenue_krw: 100_000 * (i + 1),
    token_cost_krw: 1_000 * (i + 1),
    variance_krw: 99_000 * (i + 1),
  })),
};

describe("RevenueDashboardPage", () => {
  it("KPI 4개 + 차트 + 헤더 렌더", async () => {
    const { fetchRevenueVariance, fetchRevenueVarianceSeries } = await import(
      "@/features/admin-dashboard/api/analytics"
    );
    (fetchRevenueVariance as ReturnType<typeof vi.fn>).mockResolvedValue(
      baseMonth,
    );
    (fetchRevenueVarianceSeries as ReturnType<typeof vi.fn>).mockResolvedValue(
      baseSeries,
    );

    renderWithQuery(<RevenueDashboardPage />);

    expect(screen.getByText("매출 대시보드")).toBeTruthy();
    await screen.findByText("당월 매출");
    expect(screen.getByText("당월 토큰 비용")).toBeTruthy();
    expect(screen.getByText("차액")).toBeTruthy();
    expect(screen.getByText("에러·이상로그")).toBeTruthy();

    expect(await screen.findByText("1,485,000원")).toBeTruthy();
    expect(screen.getByText("17,284원")).toBeTruthy();
  });

  it("음수 차액 시 부호 `−` + error tone trend", async () => {
    const { fetchRevenueVariance, fetchRevenueVarianceSeries } = await import(
      "@/features/admin-dashboard/api/analytics"
    );
    (fetchRevenueVariance as ReturnType<typeof vi.fn>).mockResolvedValue({
      ...baseMonth,
      revenue_krw: 5_000,
      token_cost_krw: 10_000,
      variance_krw: -5_000,
    });
    (fetchRevenueVarianceSeries as ReturnType<typeof vi.fn>).mockResolvedValue(
      baseSeries,
    );

    renderWithQuery(<RevenueDashboardPage />);

    await screen.findByText("−5,000원");
    expect(screen.getByText(/적자/)).toBeTruthy();
  });

  it("월 input 변경 → query 재호출", async () => {
    const { fetchRevenueVariance, fetchRevenueVarianceSeries } = await import(
      "@/features/admin-dashboard/api/analytics"
    );
    (fetchRevenueVariance as ReturnType<typeof vi.fn>).mockResolvedValue(
      baseMonth,
    );
    (fetchRevenueVarianceSeries as ReturnType<typeof vi.fn>).mockResolvedValue(
      baseSeries,
    );

    renderWithQuery(<RevenueDashboardPage />);
    await screen.findByText("1,485,000원");

    const monthInput = screen.getByLabelText(/조회 월/) as HTMLInputElement;
    fireEvent.change(monthInput, { target: { value: "2026-04" } });

    await waitFor(() => {
      expect(
        (fetchRevenueVariance as ReturnType<typeof vi.fn>).mock.calls.some(
          (c) => c[0]?.year_month === "2026-04",
        ),
      ).toBe(true);
    });
  });

  it("엑셀 다운로드 버튼 클릭 → fetchRevenueVarianceExport 호출", async () => {
    const {
      fetchRevenueVariance,
      fetchRevenueVarianceSeries,
      fetchRevenueVarianceExport,
    } = await import("@/features/admin-dashboard/api/analytics");
    (fetchRevenueVariance as ReturnType<typeof vi.fn>).mockResolvedValue(
      baseMonth,
    );
    (fetchRevenueVarianceSeries as ReturnType<typeof vi.fn>).mockResolvedValue(
      baseSeries,
    );

    const blob = new Blob(["x"], {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    (
      fetchRevenueVarianceExport as ReturnType<typeof vi.fn>
    ).mockResolvedValueOnce({
      blob,
      filename: "revenue_variance_2026-05.xlsx",
    });

    // URL.createObjectURL stub
    global.URL.createObjectURL = vi.fn(() => "blob:mock");
    global.URL.revokeObjectURL = vi.fn();

    renderWithQuery(<RevenueDashboardPage />);
    await screen.findByText("1,485,000원");

    const button = screen.getByRole("button", { name: /엑셀 다운로드/ });
    fireEvent.click(button);

    await waitFor(() => {
      expect(fetchRevenueVarianceExport).toHaveBeenCalled();
    });
  });

  it("뒤로가기 링크 = /admin/finance", async () => {
    const { fetchRevenueVariance, fetchRevenueVarianceSeries } = await import(
      "@/features/admin-dashboard/api/analytics"
    );
    (fetchRevenueVariance as ReturnType<typeof vi.fn>).mockResolvedValue(
      baseMonth,
    );
    (fetchRevenueVarianceSeries as ReturnType<typeof vi.fn>).mockResolvedValue(
      baseSeries,
    );

    renderWithQuery(<RevenueDashboardPage />);
    const backLink = await screen.findByRole("link", {
      name: /재무로 돌아가기/,
    });
    expect(backLink.getAttribute("href")).toBe("/admin/finance");
  });
});
