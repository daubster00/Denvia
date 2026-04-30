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
  it("기본 렌더 — month unit 활성, 차트 영역 표시", async () => {
    const { fetchSignups } = await import(
      "@/features/admin-dashboard/api/analytics"
    );
    (fetchSignups as ReturnType<typeof vi.fn>).mockResolvedValue({
      unit: "month",
      from: "2025-05-01",
      to: "2026-04-30",
      buckets: [
        { bucket_start: "2026-04-01", cumulative: 50, active: 40, withdrawn: 10 },
      ],
    });

    renderWithQuery(<SignupsPage />);

    expect(screen.getByRole("heading", { name: "가입자 추세" })).toBeTruthy();
    await screen.findByText("50명");
    const monthBtn = screen.getByRole("button", { name: "월" });
    expect(monthBtn.getAttribute("aria-pressed")).toBe("true");
  });

  it("단위 토글(일) 클릭 → fetchSignups가 unit=day로 재호출", async () => {
    const { fetchSignups } = await import(
      "@/features/admin-dashboard/api/analytics"
    );
    (fetchSignups as ReturnType<typeof vi.fn>).mockResolvedValue({
      unit: "month",
      from: "2025-05-01",
      to: "2026-04-30",
      buckets: [],
    });

    renderWithQuery(<SignupsPage />);

    await waitFor(() =>
      expect(fetchSignups).toHaveBeenCalledWith(
        expect.objectContaining({ unit: "month" }),
      ),
    );

    const dayBtn = screen.getByRole("button", { name: "일" });
    fireEvent.click(dayBtn);

    await waitFor(() =>
      expect(fetchSignups).toHaveBeenCalledWith(
        expect.objectContaining({ unit: "day" }),
      ),
    );
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
