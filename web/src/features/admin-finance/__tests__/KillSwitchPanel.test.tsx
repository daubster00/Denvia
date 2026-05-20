import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { KillSwitchPanel } from "@/features/admin-finance/components/KillSwitchPanel";
import * as killswitchApi from "@/features/admin-finance/api/killswitch";
import type { KillswitchStatusResponse } from "@/features/admin-finance/api/killswitch";

function withQueryClient(ui: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

const inactivePayload: KillswitchStatusResponse = {
  auto_free_only: {
    active: false,
    activated_at: null,
    year_month: "2026-05",
    current_percent: 5.5,
    monthly_limit_usd: "100.00",
    spent_usd: "5.50",
    monthly_limit_krw: 140_000,
    spent_krw: 7_700,
    usd_to_krw: 1400,
  },
  manual_total: {
    active: false,
    activated_at: null,
    deactivated_at: null,
    reason: null,
    activated_by_admin_email: null,
    activated_by_admin_id: null,
  },
};

const manualActivePayload: KillswitchStatusResponse = {
  auto_free_only: { ...inactivePayload.auto_free_only },
  manual_total: {
    active: true,
    activated_at: "2026-05-07T05:00:00Z",
    deactivated_at: null,
    reason: "OpenAI 장애 대응",
    activated_by_admin_email: "ad****@denvia.local",
    activated_by_admin_id: 1,
  },
};

describe("KillSwitchPanel", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("로딩 중 status 메시지", async () => {
    vi.spyOn(killswitchApi, "fetchKillswitchStatus").mockImplementation(
      () => new Promise(() => {}),
    );
    render(withQueryClient(<KillSwitchPanel />));
    expect(screen.getByRole("status").textContent).toContain("불러오는 중");
  });

  it("auto/manual 비활성 시 두 카드 모두 OFF로 렌더", async () => {
    vi.spyOn(killswitchApi, "fetchKillswitchStatus").mockResolvedValue(
      inactivePayload,
    );
    render(withQueryClient(<KillSwitchPanel />));
    await waitFor(() => {
      expect(screen.getByText(/자동 무료 차단/)).toBeTruthy();
      expect(screen.getByText(/수동 전체 정지/)).toBeTruthy();
    });
    const offMatches = screen.getAllByText(/상태: OFF/);
    expect(offMatches.length).toBe(2);
    expect(screen.getByRole("button", { name: /전체 정지 발동/ })).toBeTruthy();
  });

  it("manual_total 활성 시 발동자/사유 노출 + 해제 버튼 노출", async () => {
    vi.spyOn(killswitchApi, "fetchKillswitchStatus").mockResolvedValue(
      manualActivePayload,
    );
    render(withQueryClient(<KillSwitchPanel />));
    await waitFor(() => {
      expect(screen.getByText("ad****@denvia.local")).toBeTruthy();
    });
    expect(screen.getByText("OpenAI 장애 대응")).toBeTruthy();
    expect(screen.getByRole("button", { name: /전체 정지 해제/ })).toBeTruthy();
    // 발동 버튼은 활성 상태에서는 표시되지 않음
    expect(
      screen.queryByRole("button", { name: /전체 정지 발동/ }),
    ).toBeNull();
  });

  it("API 에러 시 에러 메시지 + 다시 시도 버튼", async () => {
    vi.spyOn(killswitchApi, "fetchKillswitchStatus").mockRejectedValue(
      new Error("boom"),
    );
    render(withQueryClient(<KillSwitchPanel />));
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeTruthy();
    });
    expect(screen.getByRole("button", { name: "다시 시도" })).toBeTruthy();
  });
});
