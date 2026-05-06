import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SegmentsSummaryWidget } from "../SegmentsSummaryWidget";

vi.mock("../../api/analytics", () => ({
  fetchSegments: vi.fn(),
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

const SAMPLE_DATA = {
  as_of: "2026-05-01T15:30:00+09:00",
  applied_filters: { include_withdrawn: false, include_blocked: false },
  total: 145,
  by_segment: [
    { segment: "doctor" as const, count: 60, active_count: 58, pro_count: 14 },
    {
      segment: "hygienist" as const,
      count: 70,
      active_count: 68,
      pro_count: 6,
    },
    {
      segment: "student_other" as const,
      count: 15,
      active_count: 14,
      pro_count: 0,
    },
  ],
  by_experience: [],
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("SegmentsSummaryWidget", () => {
  it("로딩 상태 — WidgetLoadingState 표시", async () => {
    const { fetchSegments } = await import("../../api/analytics");
    (fetchSegments as ReturnType<typeof vi.fn>).mockImplementation(
      () => new Promise(() => {}),
    );
    renderWithQuery(<SegmentsSummaryWidget />);
    expect(screen.getByText(/로딩 중/)).toBeTruthy();
  });

  it("실데이터 — 3 segment + 합계 4행 렌더", async () => {
    const { fetchSegments } = await import("../../api/analytics");
    (fetchSegments as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      SAMPLE_DATA,
    );
    renderWithQuery(<SegmentsSummaryWidget />);
    await screen.findByText("60명");
    expect(screen.getByText("70명")).toBeTruthy();
    expect(screen.getByText("15명")).toBeTruthy();
    expect(screen.getByText("145명")).toBeTruthy();
    expect(screen.getByText("치과의사")).toBeTruthy();
    expect(screen.getByText("치과위생사")).toBeTruthy();
    expect(screen.getByText("학생/기타")).toBeTruthy();
    expect(screen.getByText("합계")).toBeTruthy();
  });

  it("빈 데이터 — EmptyState 노출", async () => {
    const { fetchSegments } = await import("../../api/analytics");
    (fetchSegments as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ...SAMPLE_DATA,
      total: 0,
      by_segment: [
        {
          segment: "doctor" as const,
          count: 0,
          active_count: 0,
          pro_count: 0,
        },
        {
          segment: "hygienist" as const,
          count: 0,
          active_count: 0,
          pro_count: 0,
        },
        {
          segment: "student_other" as const,
          count: 0,
          active_count: 0,
          pro_count: 0,
        },
      ],
    });
    renderWithQuery(<SegmentsSummaryWidget />);
    await screen.findByText(/사용자 데이터가 없습니다/);
  });

  it("오류 상태 — WidgetErrorState 표시", async () => {
    const { fetchSegments } = await import("../../api/analytics");
    (fetchSegments as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error("network"),
    );
    renderWithQuery(<SegmentsSummaryWidget />);
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeTruthy();
    });
  });

  it("상세 링크 /admin/dashboard/analytics/segments 포함", async () => {
    const { fetchSegments } = await import("../../api/analytics");
    (fetchSegments as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      SAMPLE_DATA,
    );
    renderWithQuery(<SegmentsSummaryWidget />);
    await screen.findByText("60명");
    const link = screen.getByRole("link", {
      name: /가입유형 분포 상세 페이지로 이동/,
    });
    expect(link.getAttribute("href")).toBe(
      "/admin/dashboard/analytics/segments",
    );
  });
});
