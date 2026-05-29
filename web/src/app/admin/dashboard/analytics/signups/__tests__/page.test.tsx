import { describe, it, expect, vi, beforeAll, beforeEach } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import SignupsPage from "../page";

beforeAll(() => {
  // @ts-expect-error - jsdom polyfill
  global.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

vi.mock("@/features/admin-dashboard/api/analytics", () => ({
  fetchSignups: vi.fn(),
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

beforeEach(() => {
  vi.clearAllMocks();
});

describe("SignupsPage", () => {
  it("기본 렌더 — 일 단위 활성, 시작일/종료일 노출, 차트 영역 표시", async () => {
    const { fetchSignups } = await import(
      "@/features/admin-dashboard/api/analytics"
    );
    (fetchSignups as ReturnType<typeof vi.fn>).mockResolvedValue({
      unit: "day",
      from: "2026-04-29",
      to: "2026-05-28",
      buckets: [
        { bucket_start: "2026-05-28", cumulative: 50, active: 40, withdrawn: 10, new_signups: 5 },
      ],
    });

    renderWithQuery(<SignupsPage />);

    expect(screen.getByRole("heading", { name: "가입자 추세" })).toBeTruthy();
    await screen.findByText("50명");
    const dayBtn = screen.getByRole("button", { name: "일" });
    expect(dayBtn.getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByLabelText("조회 시작일")).toBeTruthy();
    expect(screen.getByLabelText("조회 종료일")).toBeTruthy();
  });

  it("단위 토글(월) 클릭 → fetchSignups가 unit=month로 재호출 + 기본 범위 365일", async () => {
    const { fetchSignups } = await import(
      "@/features/admin-dashboard/api/analytics"
    );
    (fetchSignups as ReturnType<typeof vi.fn>).mockResolvedValue({
      unit: "day",
      from: "2026-04-29",
      to: "2026-05-28",
      buckets: [],
    });

    renderWithQuery(<SignupsPage />);

    await waitFor(() =>
      expect(fetchSignups).toHaveBeenCalledWith(
        expect.objectContaining({ unit: "day" }),
      ),
    );

    const monthBtn = screen.getByRole("button", { name: "월" });
    fireEvent.click(monthBtn);

    await waitFor(() => {
      const lastCall = (fetchSignups as ReturnType<typeof vi.fn>).mock.calls.at(
        -1,
      )?.[0];
      expect(lastCall).toBeDefined();
      expect(lastCall.unit).toBe("month");
      const from = new Date(lastCall.from);
      const to = new Date(lastCall.to);
      const diffDays = Math.round(
        (to.getTime() - from.getTime()) / (24 * 60 * 60 * 1000),
      );
      expect(diffDays).toBe(364);
    });
  });

  it("시작일/종료일 input 변경 시 새 범위로 fetchSignups 재호출", async () => {
    const { fetchSignups } = await import(
      "@/features/admin-dashboard/api/analytics"
    );
    (fetchSignups as ReturnType<typeof vi.fn>).mockResolvedValue({
      unit: "day",
      from: "",
      to: "",
      buckets: [],
    });

    renderWithQuery(<SignupsPage />);

    await waitFor(() => expect(fetchSignups).toHaveBeenCalled());

    fireEvent.change(screen.getByLabelText("조회 시작일"), {
      target: { value: "2026-01-01" },
    });

    await waitFor(() => {
      const lastCall = (fetchSignups as ReturnType<typeof vi.fn>).mock.calls.at(
        -1,
      )?.[0];
      expect(lastCall?.from).toBe("2026-01-01");
    });
  });

  it("API 실패 → role=alert + 다시 시도 버튼", async () => {
    const { fetchSignups } = await import(
      "@/features/admin-dashboard/api/analytics"
    );
    (fetchSignups as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("oops"),
    );

    renderWithQuery(<SignupsPage />);
    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
    expect(screen.getByText("다시 시도")).toBeTruthy();
  });

  it("← 대시보드 홈으로 링크 노출", () => {
    renderWithQuery(<SignupsPage />);
    const link = screen.getByRole("link", { name: /대시보드 홈으로/ });
    expect(link.getAttribute("href")).toBe("/admin");
  });
});
