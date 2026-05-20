import { describe, it, expect, vi, beforeEach, beforeAll } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import FeedbackPage from "../page";

// Recharts ResizeObserver stub
beforeAll(() => {
  // @ts-expect-error - jsdom polyfill
  global.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

vi.mock("@/features/admin-dashboard/api/analytics", () => ({
  buildFeedbackExportUrl: vi.fn(() => "http://localhost:8000/api/v1/admin/analytics/feedback/export?unit=month&rating_filter=all"),
  fetchFeedback: vi.fn(),
  fetchFeedbackExport: vi.fn(),
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

vi.mock("@/features/admin-dashboard/components/DashboardChart", () => ({
  DashboardChart: ({ ariaLabel }: { ariaLabel: string }) => (
    <div role="img" aria-label={ariaLabel}>chart</div>
  ),
}));

vi.mock("@/features/admin-dashboard/components/KPICard", () => ({
  KPICard: ({ label, value }: { label: string; value: string }) => (
    <div>
      <span>{label}</span>
      <span>{value}</span>
    </div>
  ),
}));

const mockData = {
  unit: "month",
  from: "2025-05-01",
  to: "2026-04-30",
  rating_filter: "all",
  summary: { good_count: 120, bad_count: 34, good_ratio: 0.779 },
  series: [{ bucket_start: "2026-04-01", good: 55, bad: 8 }],
  items: [
    {
      qa_log_id: 1001,
      question_text: "임플란트 선택 기준?",
      answer_text: "크라운·브릿지·틀니 세 종류입니다.",
      rating: "good" as const,
      segment: "doctor",
      user_id: 42,
      email: "doctor@denvia.test",
      created_at: "2026-04-15T10:23:00+09:00",
    },
  ],
  page: 1,
  per_page: 50,
  total: 1,
};

function renderWithQuery(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("FeedbackPage", () => {
  it("단위 토글 3개 aria-pressed 정상 동작", async () => {
    const { fetchFeedback } = await import(
      "@/features/admin-dashboard/api/analytics"
    );
    (fetchFeedback as ReturnType<typeof vi.fn>).mockResolvedValue(mockData);
    renderWithQuery(<FeedbackPage />);

    const weekBtn = screen.getByRole("button", { name: "주" });
    expect(weekBtn.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(weekBtn);
    expect(weekBtn.getAttribute("aria-pressed")).toBe("true");
  });

  it("rating_filter 토글 동작", async () => {
    const { fetchFeedback } = await import(
      "@/features/admin-dashboard/api/analytics"
    );
    (fetchFeedback as ReturnType<typeof vi.fn>).mockResolvedValue(mockData);
    renderWithQuery(<FeedbackPage />);

    const goodBtn = screen.getByRole("button", { name: "GOOD만" });
    expect(goodBtn.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(goodBtn);
    expect(goodBtn.getAttribute("aria-pressed")).toBe("true");
  });

  it("검색어 입력 필드 존재", () => {
    renderWithQuery(<FeedbackPage />);
    const input = screen.getByRole("searchbox", { name: "질문·답변 키워드 검색" });
    expect(input).toBeTruthy();
  });

  it("데이터 로드 후 테이블 행 클릭 → Drawer 오픈", async () => {
    const { fetchFeedback } = await import(
      "@/features/admin-dashboard/api/analytics"
    );
    (fetchFeedback as ReturnType<typeof vi.fn>).mockResolvedValue(mockData);
    renderWithQuery(<FeedbackPage />);

    await screen.findByText("임플란트 선택 기준?");
    const row = screen.getByRole("row", { name: "피드백 상세 보기" });
    fireEvent.click(row);
    expect(screen.getByRole("dialog", { name: "답변 상세" })).toBeTruthy();
  });

  it("계정 컬럼이 고객 관리 페이지 링크로 노출", async () => {
    const { fetchFeedback } = await import(
      "@/features/admin-dashboard/api/analytics"
    );
    (fetchFeedback as ReturnType<typeof vi.fn>).mockResolvedValue(mockData);
    renderWithQuery(<FeedbackPage />);

    const link = await screen.findByRole("link", {
      name: /doctor@denvia\.test/,
    });
    expect(link.getAttribute("href")).toBe("/admin/users/42");
  });

  it("엑셀 버튼 클릭 → 다운로드 iframe 생성", async () => {
    const { buildFeedbackExportUrl, fetchFeedback } = await import(
      "@/features/admin-dashboard/api/analytics"
    );
    (fetchFeedback as ReturnType<typeof vi.fn>).mockResolvedValue(mockData);

    renderWithQuery(<FeedbackPage />);
    await screen.findByText("임플란트 선택 기준?");

    const exportBtn = screen.getByRole("button", { name: "현재 필터 기준으로 엑셀 내보내기" });
    fireEvent.click(exportBtn);

    await waitFor(() => {
      expect(buildFeedbackExportUrl).toHaveBeenCalled();
      expect(document.querySelector('iframe[title="feedback-export-download"]')).toBeTruthy();
    });
  });
});
