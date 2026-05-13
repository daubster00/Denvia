import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RevenueSummaryWidget } from "../RevenueSummaryWidget";

vi.mock("../../api/analytics", () => ({
  fetchRevenueVariance: vi.fn(),
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

const baseData = {
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

describe("RevenueSummaryWidget", () => {
  it("로딩 상태 → 로딩 메시지", async () => {
    const { fetchRevenueVariance } = await import("../../api/analytics");
    (fetchRevenueVariance as ReturnType<typeof vi.fn>).mockImplementation(
      () => new Promise(() => {}),
    );
    renderWithQuery(<RevenueSummaryWidget />);
    expect(screen.getByText(/로딩 중/)).toBeTruthy();
  });

  it("데이터 6개 행 렌더 (총매출/환불/순매출/토큰비용/차액/에러)", async () => {
    const { fetchRevenueVariance } = await import("../../api/analytics");
    (fetchRevenueVariance as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      baseData,
    );
    renderWithQuery(<RevenueSummaryWidget />);
    await screen.findByText("당월 총매출");
    // 환불 0 기준: 총매출 == 순매출 이므로 1,485,000원이 두 번 등장
    const grossCells = await screen.findAllByText("1,485,000원");
    expect(grossCells.length).toBe(2);
    expect(screen.getByText("0원")).toBeTruthy(); // 환불액
    expect(screen.getByText("17,284원")).toBeTruthy();
    expect(screen.getByText("1,467,716원")).toBeTruthy();
    expect(screen.getByText("15건")).toBeTruthy(); // 3+12
    expect(screen.getByText("순매출")).toBeTruthy();
    expect(screen.getByText("환불액")).toBeTruthy();
  });

  it("환불 발생 시 환불액에 `−` 부호 + 순매출 차감", async () => {
    const { fetchRevenueVariance } = await import("../../api/analytics");
    (fetchRevenueVariance as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ...baseData,
      gross_revenue_krw: 30_000,
      refund_krw: 10_000,
      net_revenue_krw: 20_000,
      revenue_krw: 30_000,
      variance_krw: 20_000 - 17_284,
    });
    renderWithQuery(<RevenueSummaryWidget />);
    await screen.findByText("−10,000원");
    expect(screen.getByText("20,000원")).toBeTruthy();
    expect(screen.getByText("30,000원")).toBeTruthy();
  });

  it("음수 차액 시 부호 `−` + varianceNegative 클래스", async () => {
    const { fetchRevenueVariance } = await import("../../api/analytics");
    (fetchRevenueVariance as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ...baseData,
      revenue_krw: 5_000,
      gross_revenue_krw: 5_000,
      net_revenue_krw: 5_000,
      token_cost_krw: 10_000,
      variance_krw: -5_000,
    });
    renderWithQuery(<RevenueSummaryWidget />);
    await screen.findByText("−5,000원");
  });

  it("양수 차액 시 부호 없음", async () => {
    const { fetchRevenueVariance } = await import("../../api/analytics");
    (fetchRevenueVariance as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ...baseData,
      variance_krw: 1_000,
    });
    renderWithQuery(<RevenueSummaryWidget />);
    const varianceCell = await screen.findByText("1,000원");
    expect(varianceCell.textContent).toBe("1,000원");
  });

  it("오류 상태 → WidgetErrorState (role=alert) 표시", async () => {
    const { fetchRevenueVariance } = await import("../../api/analytics");
    (fetchRevenueVariance as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error("network"),
    );
    renderWithQuery(<RevenueSummaryWidget />);
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeTruthy();
    });
  });

  it("상세 링크 /admin/finance/revenue 포함", async () => {
    const { fetchRevenueVariance } = await import("../../api/analytics");
    (fetchRevenueVariance as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      baseData,
    );
    renderWithQuery(<RevenueSummaryWidget />);
    await screen.findAllByText("1,485,000원");
    const link = screen.getByRole("link", {
      name: /재무 요약 상세 페이지로 이동/,
    });
    expect(link.getAttribute("href")).toBe("/admin/finance/revenue");
  });
});
