import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { AutoModeCard } from "@/features/admin-finance/components/AutoModeCard";
import type { AutoFreeOnlyStatus } from "@/features/admin-finance/api/killswitch";

function makeStatus(overrides: Partial<AutoFreeOnlyStatus> = {}): AutoFreeOnlyStatus {
  return {
    active: false,
    activated_at: null,
    year_month: "2026-05",
    current_percent: 12.5,
    monthly_limit_usd: "100.00",
    spent_usd: "12.50",
    ...overrides,
  };
}

describe("AutoModeCard", () => {
  it("비활성 시 정상 범위 안내 문구 노출", () => {
    render(<AutoModeCard status={makeStatus()} />);
    expect(screen.getByText(/현재 예산 사용량은 정상 범위입니다/)).toBeTruthy();
    expect(screen.getByText(/상태: OFF/)).toBeTruthy();
  });

  it("활성 시 자동 활성화 안내 문구 + 발동 시각 노출", () => {
    render(
      <AutoModeCard
        status={makeStatus({
          active: true,
          activated_at: "2026-05-07T05:23:00+00:00",
          current_percent: 102.5,
          spent_usd: "102.50",
        })}
      />,
    );
    expect(screen.getByText(/100%에 도달해 자동 활성화/)).toBeTruthy();
    expect(screen.getByText(/상태: ON/)).toBeTruthy();
    expect(screen.getByText(/2026-05-07 14:23 \(KST\)/)).toBeTruthy();
  });

  it("year_month / 사용량(%) / 한도 USD 메타 노출", () => {
    render(<AutoModeCard status={makeStatus({ current_percent: 87.34 })} />);
    expect(screen.getByText("2026-05")).toBeTruthy();
    expect(screen.getByText("87.34%")).toBeTruthy();
    expect(screen.getByText("$100.00")).toBeTruthy();
  });

  it("예산 한도 상향 링크 노출", () => {
    render(<AutoModeCard status={makeStatus()} />);
    const link = screen.getByRole("link", { name: /예산 한도 상향/ });
    expect(link.getAttribute("href")).toBe("/admin/settings#monthly-budget");
  });
});
