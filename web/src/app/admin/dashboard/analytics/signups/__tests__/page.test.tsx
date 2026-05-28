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
  it("기본 렌더 — 최근 7일 프리셋, 일 단위 활성, 차트 영역 표시", async () => {
    const { fetchSignups } = await import(
      "@/features/admin-dashboard/api/analytics"
    );
    (fetchSignups as ReturnType<typeof vi.fn>).mockResolvedValue({
      unit: "day",
      from: "2026-05-12",
      to: "2026-05-18",
      buckets: [
        { bucket_start: "2026-05-18", cumulative: 50, active: 40, withdrawn: 10, new_signups: 5 },
      ],
    });

    renderWithQuery(<SignupsPage />);

    expect(screen.getByRole("heading", { name: "가입자 추세" })).toBeTruthy();
    await screen.findByText("50명");
    const dayBtn = screen.getByRole("button", { name: "일" });
    expect(dayBtn.getAttribute("aria-pressed")).toBe("true");
    const presetBtn = screen.getByRole("button", { name: "최근 7일" });
    expect(presetBtn.getAttribute("aria-pressed")).toBe("true");
  });

  it("단위 토글(월) 클릭 → fetchSignups가 unit=month로 재호출", async () => {
    const { fetchSignups } = await import(
      "@/features/admin-dashboard/api/analytics"
    );
    (fetchSignups as ReturnType<typeof vi.fn>).mockResolvedValue({
      unit: "day",
      from: "2026-05-12",
      to: "2026-05-18",
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

    await waitFor(() =>
      expect(fetchSignups).toHaveBeenCalledWith(
        expect.objectContaining({ unit: "month" }),
      ),
    );
  });

  it("기간 프리셋(최근 30일) 클릭 → 30일 범위로 fetchSignups 재호출", async () => {
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

    fireEvent.click(screen.getByRole("button", { name: "최근 30일" }));

    await waitFor(() => {
      const lastCall = (fetchSignups as ReturnType<typeof vi.fn>).mock.calls.at(
        -1,
      )?.[0];
      expect(lastCall).toBeDefined();
      const from = new Date(lastCall.from);
      const to = new Date(lastCall.to);
      const diffDays = Math.round(
        (to.getTime() - from.getTime()) / (24 * 60 * 60 * 1000),
      );
      expect(diffDays).toBe(29);
    });
  });

  it("사용자 지정 프리셋 선택 시 시작일/종료일 입력 노출", async () => {
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

    expect(screen.queryByLabelText("시작일")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "사용자 지정" }));
    expect(screen.getByLabelText("시작일")).toBeTruthy();
    expect(screen.getByLabelText("종료일")).toBeTruthy();
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
