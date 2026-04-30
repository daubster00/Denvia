import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RagStatusWidget } from "../RagStatusWidget";

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

describe("RagStatusWidget", () => {
  it("pending 0 → '최신' 배지", async () => {
    const { fetchRagStatus } = await import("@/features/admin-rag/api/knowledge");
    (fetchRagStatus as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      pending_changes_count: 0,
      last_rebuild_at: "2026-04-28T12:00:00+09:00",
      last_rebuild_status: "success",
      active_rebuild: null,
    });
    renderWithQuery(<RagStatusWidget />);
    expect(await screen.findByText("최신")).toBeTruthy();
    expect(screen.getByText("성공")).toBeTruthy();
    const link = screen.getByRole("link");
    expect(link.getAttribute("href")).toBe("/admin/rag/data");
  });

  it("pending > 0 → 재빌드 대기 배지", async () => {
    const { fetchRagStatus } = await import("@/features/admin-rag/api/knowledge");
    (fetchRagStatus as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      pending_changes_count: 3,
      last_rebuild_at: null,
      last_rebuild_status: null,
      active_rebuild: null,
    });
    renderWithQuery(<RagStatusWidget />);
    expect(await screen.findByText(/재빌드 대기 3건/)).toBeTruthy();
  });

  it("active_rebuild → progressbar + 퍼센트", async () => {
    const { fetchRagStatus } = await import("@/features/admin-rag/api/knowledge");
    (fetchRagStatus as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      pending_changes_count: 1,
      last_rebuild_at: null,
      last_rebuild_status: null,
      active_rebuild: {
        job_id: 11,
        status: "running",
        progress_percent: 42,
        stage: "embedding",
      },
    });
    renderWithQuery(<RagStatusWidget />);
    await screen.findByText(/embedding/);
    const bar = screen.getByRole("progressbar");
    expect(bar.getAttribute("aria-valuenow")).toBe("42");
    expect(screen.getByText("42%")).toBeTruthy();
  });

  it("API 실패 → 오류 + 재시도", async () => {
    const { fetchRagStatus } = await import("@/features/admin-rag/api/knowledge");
    (fetchRagStatus as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error("fail"));
    renderWithQuery(<RagStatusWidget />);
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByText("다시 시도")).toBeTruthy();
  });
});
