import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import AdminUsersEditsPage from "../page";

const useSearchParamsMock = vi.fn();

vi.mock("next/navigation", () => ({
  useSearchParams: () => useSearchParamsMock(),
}));

vi.mock("@/features/admin-users/api/audit", () => ({
  fetchAuditLogs: vi.fn(),
}));

function withQuery(ui: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{ui}</QueryClientProvider>;
}

beforeEach(() => {
  vi.clearAllMocks();
  // 기본 searchParams: 비어있음
  useSearchParamsMock.mockReturnValue({
    get: () => null,
  });
});

describe("AdminUsersEditsPage", () => {
  it("renders header + filters + empty state on first mount with no data", async () => {
    const { fetchAuditLogs } = await import(
      "@/features/admin-users/api/audit"
    );
    (fetchAuditLogs as ReturnType<typeof vi.fn>).mockResolvedValue({
      items: [],
      page: 1,
      per_page: 20,
      total: 0,
    });
    render(withQuery(<AdminUsersEditsPage />));
    expect(screen.getByText("사용자 수정 이력")).toBeTruthy();
    await waitFor(() => {
      expect(screen.getByText("수정 이력이 없습니다")).toBeTruthy();
    });
  });

  it("parses user_id from query string and applies as target_id", async () => {
    useSearchParamsMock.mockReturnValue({
      get: (key: string) => (key === "user_id" ? "42" : null),
    });
    const { fetchAuditLogs } = await import(
      "@/features/admin-users/api/audit"
    );
    (fetchAuditLogs as ReturnType<typeof vi.fn>).mockResolvedValue({
      items: [],
      page: 1,
      per_page: 20,
      total: 0,
    });
    render(withQuery(<AdminUsersEditsPage />));
    await waitFor(() => {
      expect(fetchAuditLogs).toHaveBeenCalled();
    });
    const callArgs = (fetchAuditLogs as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(callArgs.target_id).toBe(42);
  });

  it("toggles action filter and re-queries", async () => {
    const { fetchAuditLogs } = await import(
      "@/features/admin-users/api/audit"
    );
    (fetchAuditLogs as ReturnType<typeof vi.fn>).mockResolvedValue({
      items: [],
      page: 1,
      per_page: 20,
      total: 0,
    });
    render(withQuery(<AdminUsersEditsPage />));
    await waitFor(() => {
      expect(fetchAuditLogs).toHaveBeenCalled();
    });
    const initialCount = (fetchAuditLogs as ReturnType<typeof vi.fn>).mock.calls
      .length;
    fireEvent.click(screen.getByTestId("action-filter-user.permission_edit"));
    await waitFor(() => {
      expect(
        (fetchAuditLogs as ReturnType<typeof vi.fn>).mock.calls.length,
      ).toBeGreaterThan(initialCount);
    });
  });

  it("opens AuditDiffDrawer on detail click", async () => {
    const { fetchAuditLogs } = await import(
      "@/features/admin-users/api/audit"
    );
    (fetchAuditLogs as ReturnType<typeof vi.fn>).mockResolvedValue({
      items: [
        {
          id: 7,
          actor_user_id: 1,
          actor_email: "admin@denvia.local",
          action: "user.permission_edit",
          target_type: "user",
          target_id: 42,
          target_email: "target@example.com",
          diff_json: {
            before: { daily_quota_override: null },
            after: { daily_quota_override: 50 },
          },
          ip: "127.0.0.1",
          ua: null,
          trace_id: "abc",
          created_at: "2026-05-01T12:00:00+09:00",
        },
      ],
      page: 1,
      per_page: 20,
      total: 1,
    });
    render(withQuery(<AdminUsersEditsPage />));
    await waitFor(() => {
      expect(screen.getByTestId("audit-detail-button-7")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("audit-detail-button-7"));
    await waitFor(() => {
      expect(screen.getByTestId("audit-diff-drawer")).toBeTruthy();
    });
  });
});
