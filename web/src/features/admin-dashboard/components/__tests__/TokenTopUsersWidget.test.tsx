import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TokenTopUsersWidget } from "../TokenTopUsersWidget";

vi.mock("../../api/analytics", () => ({
  fetchUserTokens: vi.fn(),
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

function makeRow(overrides: Partial<{
  user_id: number;
  email: string;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost_usd: string;
  total_cost_krw: number;
  avg_cost_per_question_krw: number;
  question_count: number;
  segment: string | null;
  avg_cost_per_question: string;
}> = {}) {
  return {
    user_id: 1,
    email: "user1@example.com",
    segment: null,
    total_input_tokens: 1000,
    total_output_tokens: 500,
    total_cost_usd: "0.1234",
    total_cost_krw: 173,
    avg_cost_per_question_krw: 35,
    question_count: 5,
    avg_cost_per_question: "0.0247",
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("TokenTopUsersWidget", () => {
  it("TOP 5 렌더 + 상세 링크 + per_page=5 호출", async () => {
    const { fetchUserTokens } = await import("../../api/analytics");
    (fetchUserTokens as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      items: [
        makeRow({ user_id: 1, email: "a@x.com", total_cost_usd: "0.5000", question_count: 50 }),
        makeRow({ user_id: 2, email: "b@x.com", total_cost_usd: "0.4000", question_count: 40 }),
        makeRow({ user_id: 3, email: "c@x.com", total_cost_usd: "0.3000", question_count: 30 }),
        makeRow({ user_id: 4, email: "d@x.com", total_cost_usd: "0.2000", question_count: 20 }),
        makeRow({ user_id: 5, email: "e@x.com", total_cost_usd: "0.1000", question_count: 10 }),
      ],
      page: 1,
      per_page: 5,
      total: 5,
      range: "month",
      year_month: "2026-04",
      usd_to_krw: 1400,
    });

    renderWithQuery(<TokenTopUsersWidget />);

    expect(await screen.findByText("a@x.com")).toBeTruthy();
    expect(screen.getByText("b@x.com")).toBeTruthy();
    expect(screen.getByText("e@x.com")).toBeTruthy();
    // 각 행의 이메일은 사용자 상세로 이동하는 링크
    const emailLink = screen.getByText("a@x.com").closest("a");
    expect(emailLink?.getAttribute("href")).toBe("/admin/users/1");
    // 위젯 하단 상세 보기 링크는 그대로 유지
    const detailLink = screen
      .getAllByRole("link")
      .find((l) => l.getAttribute("href") === "/admin/dashboard/token-breakdown");
    expect(detailLink).toBeTruthy();

    expect(fetchUserTokens).toHaveBeenCalledWith({ range: "month", per_page: 5 });
  });

  it("0건 → 빈 상태 카피", async () => {
    const { fetchUserTokens } = await import("../../api/analytics");
    (fetchUserTokens as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      items: [],
      page: 1,
      per_page: 5,
      total: 0,
      range: "month",
      year_month: "2026-04",
      usd_to_krw: 1400,
    });
    renderWithQuery(<TokenTopUsersWidget />);
    expect(await screen.findByText("이번 기간에 질의 기록이 없습니다.")).toBeTruthy();
  });

  it("이메일 클릭 → 해당 사용자 상세(/admin/users/{id})로 이동", async () => {
    const { fetchUserTokens } = await import("../../api/analytics");
    (fetchUserTokens as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      items: [makeRow({ user_id: 9, email: "z@x.com" })],
      page: 1,
      per_page: 5,
      total: 1,
      range: "month",
      year_month: "2026-04",
      usd_to_krw: 1400,
    });
    renderWithQuery(<TokenTopUsersWidget />);
    await screen.findByText("z@x.com");
    const emailLink = screen.getByText("z@x.com").closest("a");
    expect(emailLink?.getAttribute("href")).toBe("/admin/users/9");
  });

  it("API 실패 → 오류 + 재시도", async () => {
    const { fetchUserTokens } = await import("../../api/analytics");
    (fetchUserTokens as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error("fail"));
    renderWithQuery(<TokenTopUsersWidget />);
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByText("다시 시도")).toBeTruthy();
  });
});
