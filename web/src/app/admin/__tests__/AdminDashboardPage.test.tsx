import { describe, it, expect, vi, beforeEach, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import AdminDashboardPage from "../page";

beforeAll(() => {
  // recharts ResponsiveContainer requires ResizeObserver; jsdom does not provide it.
  // @ts-expect-error - jsdom polyfill
  global.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

vi.mock("@/features/admin-dashboard/api/budget", () => ({
  fetchBudgetCurrentMonth: vi.fn(),
}));

vi.mock("@/features/admin-dashboard/api/analytics", () => ({
  fetchUserTokens: vi.fn(),
  fetchSignups: vi.fn(),
  fetchSubscribers: vi.fn(),
  fetchFeedback: vi.fn(),
  fetchSegments: vi.fn(),
  fetchRevenueVariance: vi.fn(),
}));

vi.mock("@/features/admin-rag/api/knowledge", () => ({
  fetchRagStatus: vi.fn(),
}));

vi.mock("@/features/admin-anomaly/api/anomaly", () => ({
  fetchAnomalyList: vi.fn(),
}));

vi.mock("@/features/admin-support/api/inquiries", () => ({
  fetchSupportCounts: vi.fn(),
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

describe("AdminDashboardPage", () => {
  async function loadMocks() {
    const { fetchBudgetCurrentMonth } = await import(
      "@/features/admin-dashboard/api/budget"
    );
    const {
      fetchUserTokens,
      fetchSignups,
      fetchSubscribers,
      fetchFeedback,
      fetchSegments,
      fetchRevenueVariance,
    } = await import("@/features/admin-dashboard/api/analytics");
    const { fetchRagStatus } = await import(
      "@/features/admin-rag/api/knowledge"
    );
    const { fetchAnomalyList } = await import(
      "@/features/admin-anomaly/api/anomaly"
    );
    const { fetchSupportCounts } = await import(
      "@/features/admin-support/api/inquiries"
    );
    // Story 5.6: 이상탐지/CS 위젯 기본 stub (빈 상태)
    (fetchAnomalyList as ReturnType<typeof vi.fn>).mockResolvedValue({
      page: 1,
      per_page: 3,
      total: 0,
      items: [],
    });
    (fetchSupportCounts as ReturnType<typeof vi.fn>).mockResolvedValue({
      open_inquiries: 0,
    });
    // Story 5.3: 기본 stub
    (fetchSignups as ReturnType<typeof vi.fn>).mockResolvedValue({
      unit: "month",
      from: "2025-05-01",
      to: "2026-04-30",
      buckets: [
        { bucket_start: "2026-04-01", cumulative: 5, active: 4, withdrawn: 1 },
      ],
    });
    (fetchSubscribers as ReturnType<typeof vi.fn>).mockResolvedValue({
      as_of: "2026-04-29T15:30:00+09:00",
      free_count: 3,
      pro_count: 1,
      blocked_count: 0,
      withdrawn_count: 1,
      pending_cancellation_count: 0,
      pending_cancellations: [],
    });
    // Story 5.4: 피드백 위젯 stub
    (fetchFeedback as ReturnType<typeof vi.fn>).mockResolvedValue({
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
    // Story 5.5: 재무 요약 위젯 stub
    (fetchRevenueVariance as ReturnType<typeof vi.fn>).mockResolvedValue({
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
    });
    // Story 6.4: 가입유형 위젯 stub
    (fetchSegments as ReturnType<typeof vi.fn>).mockResolvedValue({
      as_of: "2026-05-01T15:30:00+09:00",
      applied_filters: { include_withdrawn: false, include_blocked: false },
      total: 5,
      by_segment: [
        { segment: "doctor", count: 3, active_count: 3, pro_count: 1 },
        { segment: "hygienist", count: 1, active_count: 1, pro_count: 0 },
        { segment: "student_other", count: 1, active_count: 1, pro_count: 0 },
      ],
      by_experience: [],
    });
    return {
      fetchBudgetCurrentMonth,
      fetchUserTokens,
      fetchRagStatus,
      fetchSignups,
      fetchSubscribers,
      fetchFeedback,
      fetchSegments,
      fetchAnomalyList,
      fetchSupportCounts,
    };
  }

  it("placeholder 문구가 더 이상 노출되지 않음 + 위젯/KPI 렌더", async () => {
    const { fetchBudgetCurrentMonth, fetchUserTokens, fetchRagStatus } =
      await loadMocks();
    (fetchBudgetCurrentMonth as ReturnType<typeof vi.fn>).mockResolvedValue({
      year_month: "2026-04",
      monthly_limit_usd: "100.00",
      spent_usd: "30.00",
      monthly_limit_krw: 140_000,
      spent_krw: 42_000,
      usd_to_krw: 1400,
      percent: 30.0,
      status: "normal",
      killswitch_active: false,
      killswitch_mode: null,
    });
    (fetchUserTokens as ReturnType<typeof vi.fn>).mockResolvedValue({
      items: [
        {
          user_id: 1,
          email: "a@x.com",
          segment: null,
          total_input_tokens: 100,
          total_output_tokens: 200,
          total_cost_usd: "0.5000",
          total_cost_krw: 700,
          avg_cost_per_question_krw: 88,
          question_count: 8,
          avg_cost_per_question: "0.0625",
        },
      ],
      page: 1,
      per_page: 5,
      total: 1,
      range: "month",
      year_month: "2026-04",
      usd_to_krw: 1400,
    });
    (fetchRagStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      pending_changes_count: 0,
      last_rebuild_at: "2026-04-28T12:00:00+09:00",
      last_rebuild_status: "success",
      active_rebuild: null,
    });

    renderWithQuery(<AdminDashboardPage />);

    expect(
      screen.queryByText("대시보드 위젯은 Story 5.2에서 구현됩니다."),
    ).toBeNull();
    expect(screen.getByText("관리자 대시보드")).toBeTruthy();
    // 월 예산 사용률은 KPI 라벨과 위젯 제목 두 곳에 노출
    expect(screen.getAllByText("월 예산 사용률").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("상위 5명 질의 수")).toBeTruthy();
    expect(screen.getByText("비용 TOP 사용자")).toBeTruthy();
    expect(screen.getByText("재빌드 대기 변경")).toBeTruthy();

    // KPI 값 — 비동기 query 결과 반영 후
    expect(await screen.findByText("30.0%")).toBeTruthy();
    // 질의 수 / 비용 / 대기 건은 위젯 내부에도 노출될 수 있어 length 검증
    expect((await screen.findAllByText("8건")).length).toBeGreaterThanOrEqual(1);
    expect((await screen.findAllByText("₩700")).length).toBeGreaterThanOrEqual(1);
    expect((await screen.findAllByText("0건")).length).toBeGreaterThanOrEqual(1);
  });

  it("새로고침 버튼 렌더 + aria-label", async () => {
    const { fetchBudgetCurrentMonth, fetchUserTokens, fetchRagStatus } =
      await loadMocks();
    (fetchBudgetCurrentMonth as ReturnType<typeof vi.fn>).mockResolvedValue({
      year_month: "2026-04",
      monthly_limit_usd: "100.00",
      spent_usd: "30.00",
      monthly_limit_krw: 140_000,
      spent_krw: 42_000,
      usd_to_krw: 1400,
      percent: 30,
      status: "normal",
      killswitch_active: false,
      killswitch_mode: null,
    });
    (fetchUserTokens as ReturnType<typeof vi.fn>).mockResolvedValue({
      items: [],
      page: 1,
      per_page: 5,
      total: 0,
      range: "month",
      year_month: "2026-04",
      usd_to_krw: 1400,
    });
    (fetchRagStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      pending_changes_count: 0,
      last_rebuild_at: null,
      last_rebuild_status: null,
      active_rebuild: null,
    });

    renderWithQuery(<AdminDashboardPage />);
    const refresh = screen.getByRole("button", { name: "대시보드 새로고침" });
    expect(refresh).toBeTruthy();
  });

  it("Analytics 위젯 6종(가입자/구독/피드백/세그먼트/재무/이상탐지·CS) 모두 노출", async () => {
    const { fetchBudgetCurrentMonth, fetchUserTokens, fetchRagStatus } =
      await loadMocks();
    (fetchBudgetCurrentMonth as ReturnType<typeof vi.fn>).mockResolvedValue({
      year_month: "2026-04",
      monthly_limit_usd: "100.00",
      spent_usd: "0.00",
      monthly_limit_krw: 140_000,
      spent_krw: 0,
      usd_to_krw: 1400,
      percent: 0,
      status: "normal",
      killswitch_active: false,
      killswitch_mode: null,
    });
    (fetchUserTokens as ReturnType<typeof vi.fn>).mockResolvedValue({
      items: [],
      page: 1,
      per_page: 5,
      total: 0,
      range: "month",
      year_month: "2026-04",
      usd_to_krw: 1400,
    });
    (fetchRagStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      pending_changes_count: 0,
      last_rebuild_at: null,
      last_rebuild_status: null,
      active_rebuild: null,
    });

    renderWithQuery(<AdminDashboardPage />);
    // Story 5.3: 가입자 추이/구독 현황은 실데이터 위젯으로 활성화
    expect(await screen.findByText("가입자 추이")).toBeTruthy();
    expect(screen.getByText("구독 현황")).toBeTruthy();
    expect(screen.getByText("피드백 비율")).toBeTruthy();
    expect(screen.getByText("재무 요약")).toBeTruthy();
    expect(screen.getByText("이상탐지 / CS")).toBeTruthy();
    // Story 5.6: 이상탐지/CS 활성화 → 준비 중 배지 없음
    expect(screen.queryAllByText("준비 중")).toHaveLength(0);

    // Story 5.3 위젯 상세 링크 활성화 — 가입자 추이 / 구독 현황
    const signupsLink = screen.getByRole("link", {
      name: /가입자 추이 상세 페이지로 이동/,
    });
    expect(signupsLink.getAttribute("href")).toBe(
      "/admin/dashboard/analytics/signups",
    );
    const subscribersLink = screen.getByRole("link", {
      name: /구독 현황 상세 페이지로 이동/,
    });
    expect(subscribersLink.getAttribute("href")).toBe(
      "/admin/dashboard/analytics/subscribers",
    );

    // Story 5.4: 피드백 비율 위젯 상세 링크 활성화
    const feedbackLink = screen.getByRole("link", {
      name: /피드백 비율 상세 페이지로 이동/,
    });
    expect(feedbackLink.getAttribute("href")).toBe(
      "/admin/dashboard/analytics/feedback",
    );

    // Story 6.4: 가입유형 분포 위젯 상세 링크 활성화
    const segmentsLink = screen.getByRole("link", {
      name: /가입유형 분포 상세 페이지로 이동/,
    });
    expect(segmentsLink.getAttribute("href")).toBe(
      "/admin/dashboard/analytics/segments",
    );

    // Story 5.5: 재무 요약 위젯 상세 링크 활성화
    const revenueLink = screen.getByRole("link", {
      name: /재무 요약 상세 페이지로 이동/,
    });
    expect(revenueLink.getAttribute("href")).toBe("/admin/finance/revenue");

    // Story 5.6: 이상탐지/CS 위젯 상세 링크 활성화
    const anomalyCsLink = screen.getByRole("link", {
      name: /이상탐지 \/ CS 상세 페이지로 이동/,
    });
    expect(anomalyCsLink.getAttribute("href")).toBe("/admin/anomaly");
  });

  it("일부 API 실패해도 다른 위젯 렌더 (격리)", async () => {
    const { fetchBudgetCurrentMonth, fetchUserTokens, fetchRagStatus } =
      await loadMocks();
    (fetchBudgetCurrentMonth as ReturnType<typeof vi.fn>).mockResolvedValue({
      year_month: "2026-04",
      monthly_limit_usd: "100.00",
      spent_usd: "10.00",
      monthly_limit_krw: 140_000,
      spent_krw: 14_000,
      usd_to_krw: 1400,
      percent: 10,
      status: "normal",
      killswitch_active: false,
      killswitch_mode: null,
    });
    (fetchUserTokens as ReturnType<typeof vi.fn>).mockResolvedValue({
      items: [],
      page: 1,
      per_page: 5,
      total: 0,
      range: "month",
      year_month: "2026-04",
      usd_to_krw: 1400,
    });
    (fetchRagStatus as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("rag fail"),
    );

    renderWithQuery(<AdminDashboardPage />);
    // 다른 위젯의 데이터/링크는 정상 렌더 (10 USD × 1400 = ₩14,000)
    expect(await screen.findByText("₩14,000")).toBeTruthy();
    // RAG 위젯은 alert 렌더
    expect(await screen.findByRole("alert")).toBeTruthy();
  });
});
