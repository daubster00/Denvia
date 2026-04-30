import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import AdminDashboardPage from "../page";

vi.mock("@/features/admin-dashboard/api/budget", () => ({
  fetchBudgetCurrentMonth: vi.fn(),
}));

vi.mock("@/features/admin-dashboard/api/analytics", () => ({
  fetchUserTokens: vi.fn(),
  fetchSignups: vi.fn(),
  fetchSubscribers: vi.fn(),
  fetchFeedback: vi.fn(),
}));

vi.mock("@/features/admin-rag/api/knowledge", () => ({
  fetchRagStatus: vi.fn(),
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
    const { fetchUserTokens, fetchSignups, fetchSubscribers, fetchFeedback } = await import(
      "@/features/admin-dashboard/api/analytics"
    );
    const { fetchRagStatus } = await import(
      "@/features/admin-rag/api/knowledge"
    );
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
      pending_cancellation_count: null,
      upcoming_renewals: [],
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
    return {
      fetchBudgetCurrentMonth,
      fetchUserTokens,
      fetchRagStatus,
      fetchSignups,
      fetchSubscribers,
      fetchFeedback,
    };
  }

  it("placeholder 문구가 더 이상 노출되지 않음 + 위젯/KPI 렌더", async () => {
    const { fetchBudgetCurrentMonth, fetchUserTokens, fetchRagStatus } =
      await loadMocks();
    (fetchBudgetCurrentMonth as ReturnType<typeof vi.fn>).mockResolvedValue({
      year_month: "2026-04",
      monthly_limit_usd: "100.00",
      spent_usd: "30.00",
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
          question_count: 8,
          avg_cost_per_question: "0.0625",
        },
      ],
      page: 1,
      per_page: 5,
      total: 1,
      range: "month",
      year_month: "2026-04",
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
    expect((await screen.findAllByText("$ 0.5000")).length).toBeGreaterThanOrEqual(1);
    expect((await screen.findAllByText("0건")).length).toBeGreaterThanOrEqual(1);
  });

  it("새로고침 버튼 렌더 + aria-label", async () => {
    const { fetchBudgetCurrentMonth, fetchUserTokens, fetchRagStatus } =
      await loadMocks();
    (fetchBudgetCurrentMonth as ReturnType<typeof vi.fn>).mockResolvedValue({
      year_month: "2026-04",
      monthly_limit_usd: "100.00",
      spent_usd: "30.00",
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

  it("준비 중 위젯 5종 모두 노출", async () => {
    const { fetchBudgetCurrentMonth, fetchUserTokens, fetchRagStatus } =
      await loadMocks();
    (fetchBudgetCurrentMonth as ReturnType<typeof vi.fn>).mockResolvedValue({
      year_month: "2026-04",
      monthly_limit_usd: "100.00",
      spent_usd: "0.00",
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
    expect(screen.getByText("이상탐지/CS")).toBeTruthy();
    // Story 5.4: 피드백 비율 위젯 활성화 → 준비 중 배지 2개 (재무/이상탐지만 placeholder 유지)
    expect(screen.getAllByText("준비 중")).toHaveLength(2);

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
  });

  it("일부 API 실패해도 다른 위젯 렌더 (격리)", async () => {
    const { fetchBudgetCurrentMonth, fetchUserTokens, fetchRagStatus } =
      await loadMocks();
    (fetchBudgetCurrentMonth as ReturnType<typeof vi.fn>).mockResolvedValue({
      year_month: "2026-04",
      monthly_limit_usd: "100.00",
      spent_usd: "10.00",
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
    });
    (fetchRagStatus as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("rag fail"),
    );

    renderWithQuery(<AdminDashboardPage />);
    // 다른 위젯의 데이터/링크는 정상 렌더
    expect(await screen.findByText("$ 10.00")).toBeTruthy();
    // RAG 위젯은 alert 렌더
    expect(await screen.findByRole("alert")).toBeTruthy();
  });
});
