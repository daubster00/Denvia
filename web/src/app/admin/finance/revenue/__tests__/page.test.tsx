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
  gross_revenue_krw: 1_485_000,
  refund_krw: 0,
  net_revenue_krw: 1_485_000,
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
    gross_revenue_krw: 100_000 * (i + 1),
    refund_krw: 0,
    net_revenue_krw: 100_000 * (i + 1),
    token_cost_krw: 1_000 * (i + 1),
    variance_krw: 99_000 * (i + 1),
  })),
};

describe("RevenueDashboardPage", () => {
  it("KPI 6개 (총매출/환불/순매출/토큰비용/차액/에러) + 차트 + 헤더 렌더", async () => {
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
    await screen.findByText("당월 총매출");
    expect(screen.getByText("당월 환불액")).toBeTruthy();
    expect(screen.getByText("당월 순매출")).toBeTruthy();
    expect(screen.getByText("당월 토큰 비용")).toBeTruthy();
    expect(screen.getByText("차액 (순매출 − 토큰비용)")).toBeTruthy();
    expect(screen.getByText("에러·이상로그")).toBeTruthy();

    // 총매출 == 순매출 (환불 0) — 두 번 등장
    const gross = await screen.findAllByText("1,485,000원");
    expect(gross.length).toBe(2);
    expect(screen.getByText("0원")).toBeTruthy(); // 환불액
    expect(screen.getByText("17,284원")).toBeTruthy();
  });

  it("환불 발생 시 환불액에 `−` + 순매출이 총매출보다 작음", async () => {
    const { fetchRevenueVariance, fetchRevenueVarianceSeries } = await import(
      "@/features/admin-dashboard/api/analytics"
    );
    (fetchRevenueVariance as ReturnType<typeof vi.fn>).mockResolvedValue({
      ...baseMonth,
      gross_revenue_krw: 39_000,
      refund_krw: 10_000,
      net_revenue_krw: 29_000,
      revenue_krw: 39_000,
      token_cost_krw: 8_400,
      variance_krw: 20_600,
    });
    (fetchRevenueVarianceSeries as ReturnType<typeof vi.fn>).mockResolvedValue(
      baseSeries,
    );

    renderWithQuery(<RevenueDashboardPage />);

    await screen.findByText("−10,000원"); // 환불액
    expect(screen.getByText("39,000원")).toBeTruthy(); // 총매출
    expect(screen.getByText("29,000원")).toBeTruthy(); // 순매출
    expect(screen.getByText("20,600원")).toBeTruthy(); // 차액 (흑자)
    expect(screen.getByText(/흑자/)).toBeTruthy();
  });

  it("음수 차액 시 부호 `−` + error tone trend", async () => {
    const { fetchRevenueVariance, fetchRevenueVarianceSeries } = await import(
      "@/features/admin-dashboard/api/analytics"
    );
    (fetchRevenueVariance as ReturnType<typeof vi.fn>).mockResolvedValue({
      ...baseMonth,
      revenue_krw: 5_000,
      gross_revenue_krw: 5_000,
      net_revenue_krw: 5_000,
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
    await screen.findAllByText("1,485,000원");

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
    await screen.findAllByText("1,485,000원");

    const button = screen.getByRole("button", { name: /엑셀 다운로드/ });
    fireEvent.click(button);

    await waitFor(() => {
      expect(fetchRevenueVarianceExport).toHaveBeenCalled();
    });
  });

});
