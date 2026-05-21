import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AnomalyCSSummaryWidget } from "../AnomalyCSSummaryWidget";

vi.mock("@/features/admin-anomaly/api/anomaly", () => ({
  fetchAnomalyList: vi.fn(),
}));

vi.mock("@/features/admin-support/api/inquiries", () => ({
  fetchSupportCounts: vi.fn(),
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

const anomalyResponse = {
  page: 1,
  per_page: 3,
  total: 5,
  items: [
    {
      id: 11,
      type: "login_brute_force" as const,
      target_user_id: 101,
      target_user_email_masked: "abc***@example.com",
      ip: "192.168.0.1",
      ua: "Mozilla",
      details: {},
      status: "new" as const,
      reviewed_by_admin_id: null,
      reviewed_at: null,
      created_at: "2026-05-11T05:30:00+00:00",
    },
    {
      id: 12,
      type: "rapid_followup_questions" as const,
      target_user_id: null,
      target_user_email_masked: null,
      ip: "10.0.0.2",
      ua: null,
      details: {},
      status: "new" as const,
      reviewed_by_admin_id: null,
      reviewed_at: null,
      created_at: "2026-05-11T03:15:00+00:00",
    },
  ],
};

const supportResponse = {
  open_inquiries: 7,
};

describe("AnomalyCSSummaryWidget", () => {
  it("로딩 상태 → 로딩 메시지", async () => {
    const { fetchAnomalyList } = await import(
      "@/features/admin-anomaly/api/anomaly"
    );
    const { fetchSupportCounts } = await import(
      "@/features/admin-support/api/inquiries"
    );
    (fetchAnomalyList as ReturnType<typeof vi.fn>).mockImplementation(
      () => new Promise(() => {}),
    );
    (fetchSupportCounts as ReturnType<typeof vi.fn>).mockImplementation(
      () => new Promise(() => {}),
    );
    renderWithQuery(<AnomalyCSSummaryWidget />);
    expect(screen.getByText(/로딩 중/)).toBeTruthy();
  });

  it("미검토 이상행동·미응답 문의 카운트 + 최근 항목 렌더", async () => {
    const { fetchAnomalyList } = await import(
      "@/features/admin-anomaly/api/anomaly"
    );
    const { fetchSupportCounts } = await import(
      "@/features/admin-support/api/inquiries"
    );
    (fetchAnomalyList as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      anomalyResponse,
    );
    (fetchSupportCounts as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      supportResponse,
    );

    renderWithQuery(<AnomalyCSSummaryWidget />);

    await screen.findByText("5건");
    expect(screen.getByText("7건")).toBeTruthy();
    expect(screen.queryByText(/환불 대기/)).toBeNull();
    expect(screen.getByText("로그인 무차별 시도")).toBeTruthy();
    expect(screen.getByText("abc***@example.com")).toBeTruthy();
    expect(screen.getByText("IP 10.0.0.2")).toBeTruthy();
  });

  it("미검토 이상행동 카운트가 0이면 alert 컬러 미적용 (전체 0건 → 빈 상태)", async () => {
    const { fetchAnomalyList } = await import(
      "@/features/admin-anomaly/api/anomaly"
    );
    const { fetchSupportCounts } = await import(
      "@/features/admin-support/api/inquiries"
    );
    (fetchAnomalyList as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      page: 1,
      per_page: 3,
      total: 0,
      items: [],
    });
    (fetchSupportCounts as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      open_inquiries: 0,
    });

    renderWithQuery(<AnomalyCSSummaryWidget />);

    await screen.findByText("처리 대기 건이 없습니다.");
  });

  it("카운트는 0이지만 다른 영역에 대기 건이 있는 경우 — 최근 이상행동 빈 메시지", async () => {
    const { fetchAnomalyList } = await import(
      "@/features/admin-anomaly/api/anomaly"
    );
    const { fetchSupportCounts } = await import(
      "@/features/admin-support/api/inquiries"
    );
    (fetchAnomalyList as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      page: 1,
      per_page: 3,
      total: 0,
      items: [],
    });
    (fetchSupportCounts as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      open_inquiries: 4,
    });

    renderWithQuery(<AnomalyCSSummaryWidget />);

    await screen.findByText("미검토 이상행동이 없습니다.");
  });

  it("오류 상태 → WidgetErrorState 표시", async () => {
    const { fetchAnomalyList } = await import(
      "@/features/admin-anomaly/api/anomaly"
    );
    const { fetchSupportCounts } = await import(
      "@/features/admin-support/api/inquiries"
    );
    (fetchAnomalyList as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error("boom"),
    );
    (fetchSupportCounts as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      supportResponse,
    );

    renderWithQuery(<AnomalyCSSummaryWidget />);
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeTruthy();
    });
  });

  it("상세 링크 /admin/anomaly + 인라인 CS 링크 포함", async () => {
    const { fetchAnomalyList } = await import(
      "@/features/admin-anomaly/api/anomaly"
    );
    const { fetchSupportCounts } = await import(
      "@/features/admin-support/api/inquiries"
    );
    (fetchAnomalyList as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      anomalyResponse,
    );
    (fetchSupportCounts as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      supportResponse,
    );

    renderWithQuery(<AnomalyCSSummaryWidget />);
    await screen.findByText("5건");

    const detailLink = screen.getByRole("link", {
      name: /이상탐지 \/ CS 상세 페이지로 이동/,
    });
    expect(detailLink.getAttribute("href")).toBe("/admin/anomaly");

    const inquiriesLink = screen.getByRole("link", {
      name: /미응답 문의 상세 보기/,
    });
    expect(inquiriesLink.getAttribute("href")).toBe("/admin/cs");

    expect(
      screen.queryByRole("link", { name: /환불 대기 상세 보기/ }),
    ).toBeNull();
  });
});
