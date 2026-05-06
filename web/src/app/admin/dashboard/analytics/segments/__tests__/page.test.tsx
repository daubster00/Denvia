import { describe, it, expect, vi, beforeEach, beforeAll } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import SegmentsAnalyticsPage from "../page";

beforeAll(() => {
  // @ts-expect-error jsdom polyfill
  global.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
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

vi.mock("@/features/admin-dashboard/api/analytics", () => ({
  buildSegmentsExportUrl: vi.fn(
    () =>
      "http://localhost:8000/api/v1/admin/analytics/segments/export",
  ),
  fetchSegments: vi.fn(),
  fetchSegmentsExport: vi.fn(),
}));

vi.mock("@/features/admin-dashboard/components/DashboardChart", () => ({
  DashboardChart: ({ ariaLabel }: { ariaLabel: string }) => (
    <div role="img" aria-label={ariaLabel}>
      chart
    </div>
  ),
}));

vi.mock("@/features/admin-dashboard/components/KPICard", () => ({
  KPICard: ({
    label,
    value,
    onClick,
  }: {
    label: string;
    value: string;
    onClick?: () => void;
  }) => (
    <button type="button" onClick={onClick} data-testid={`kpi-${label}`}>
      <span>{label}</span>
      <span>{value}</span>
    </button>
  ),
}));

const SAMPLE = {
  as_of: "2026-05-01T15:30:00+09:00",
  applied_filters: { include_withdrawn: false, include_blocked: false },
  total: 145,
  by_segment: [
    { segment: "doctor", count: 60, active_count: 58, pro_count: 14 },
    { segment: "hygienist", count: 70, active_count: 68, pro_count: 6 },
    {
      segment: "student_other",
      count: 15,
      active_count: 14,
      pro_count: 0,
    },
  ],
  by_experience: [
    { segment: "doctor", years_bucket: "0-2", count: 8 },
    { segment: "doctor", years_bucket: "3-5", count: 14 },
    { segment: "doctor", years_bucket: "6-10", count: 18 },
    { segment: "doctor", years_bucket: "11-20", count: 12 },
    { segment: "doctor", years_bucket: "20+", count: 8 },
    { segment: "hygienist", years_bucket: "0-2", count: 22 },
    { segment: "hygienist", years_bucket: "3-5", count: 20 },
    { segment: "hygienist", years_bucket: "6-10", count: 15 },
    { segment: "hygienist", years_bucket: "11-20", count: 8 },
    { segment: "hygienist", years_bucket: "20+", count: 5 },
  ],
};

function renderWithQuery(ui: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("SegmentsAnalyticsPage", () => {
  it("3 KPICard + bar 차트 + 연차 차트 2개 렌더", async () => {
    const { fetchSegments } = await import(
      "@/features/admin-dashboard/api/analytics"
    );
    (fetchSegments as ReturnType<typeof vi.fn>).mockResolvedValue(SAMPLE);

    renderWithQuery(<SegmentsAnalyticsPage />);

    await screen.findByText("60명");
    expect(screen.getByText("70명")).toBeTruthy();
    expect(screen.getByText("15명")).toBeTruthy();

    // bar 차트
    expect(
      screen.getByRole("img", { name: "가입유형 분포 차트" }),
    ).toBeTruthy();
    // 연차 차트 2개
    expect(
      screen.getByRole("img", { name: "치과의사 연차 분포" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("img", { name: "치과위생사 연차 분포" }),
    ).toBeTruthy();
    // 학생/기타 안내 텍스트
    expect(
      screen.getByText(/학생.기타 가입유형은 연차 정보가 없습니다/),
    ).toBeTruthy();
  });

  it("KPICard 클릭 → /admin/users?segment=doctor 라우팅", async () => {
    const { fetchSegments } = await import(
      "@/features/admin-dashboard/api/analytics"
    );
    (fetchSegments as ReturnType<typeof vi.fn>).mockResolvedValue(SAMPLE);
    renderWithQuery(<SegmentsAnalyticsPage />);

    const kpi = await screen.findByTestId("kpi-치과의사");
    fireEvent.click(kpi);
    expect(pushMock).toHaveBeenCalledWith("/admin/users?segment=doctor");
  });

  it("탈퇴자 포함 체크박스 토글 → fetchSegments 호출 인자 변화", async () => {
    const { fetchSegments } = await import(
      "@/features/admin-dashboard/api/analytics"
    );
    (fetchSegments as ReturnType<typeof vi.fn>).mockResolvedValue(SAMPLE);
    renderWithQuery(<SegmentsAnalyticsPage />);

    await screen.findByText("60명");
    expect(fetchSegments).toHaveBeenCalledWith({
      include_withdrawn: false,
      include_blocked: false,
    });

    const withdrawnCheckbox = screen.getByRole("checkbox", {
      name: /탈퇴자 포함/,
    });
    fireEvent.click(withdrawnCheckbox);

    await waitFor(() => {
      expect(fetchSegments).toHaveBeenCalledWith({
        include_withdrawn: true,
        include_blocked: false,
      });
    });
  });

  it("엑셀 다운로드 버튼 클릭 → fetchSegmentsExport 호출", async () => {
    const { fetchSegments, fetchSegmentsExport } = await import(
      "@/features/admin-dashboard/api/analytics"
    );
    (fetchSegments as ReturnType<typeof vi.fn>).mockResolvedValue(SAMPLE);
    const fakeBlob = new Blob(["xlsx-bytes"], {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    (fetchSegmentsExport as ReturnType<typeof vi.fn>).mockResolvedValue({
      blob: fakeBlob,
      filename: "segments_2026-05-01.xlsx",
    });
    // jsdom에 URL.createObjectURL 누락 — 폴리필
    const origCreate = URL.createObjectURL;
    const origRevoke = URL.revokeObjectURL;
    URL.createObjectURL = vi.fn(() => "blob:fake");
    URL.revokeObjectURL = vi.fn();

    try {
      renderWithQuery(<SegmentsAnalyticsPage />);
      await screen.findByText("60명");
      const btn = screen.getByRole("button", { name: /엑셀 다운로드/ });
      fireEvent.click(btn);
      await waitFor(() => {
        expect(fetchSegmentsExport).toHaveBeenCalled();
      });
    } finally {
      URL.createObjectURL = origCreate;
      URL.revokeObjectURL = origRevoke;
    }
  });

  it("빈 데이터 — EmptyState 렌더", async () => {
    const { fetchSegments } = await import(
      "@/features/admin-dashboard/api/analytics"
    );
    (fetchSegments as ReturnType<typeof vi.fn>).mockResolvedValue({
      ...SAMPLE,
      total: 0,
      by_segment: [
        { segment: "doctor", count: 0, active_count: 0, pro_count: 0 },
        { segment: "hygienist", count: 0, active_count: 0, pro_count: 0 },
        {
          segment: "student_other",
          count: 0,
          active_count: 0,
          pro_count: 0,
        },
      ],
      by_experience: [],
    });
    renderWithQuery(<SegmentsAnalyticsPage />);
    await screen.findByText(/사용자 데이터가 없습니다/);
  });
});
