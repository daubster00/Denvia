import { describe, it, expect, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";
import { SubscribersDonut } from "../SubscribersDonut";
import type { SubscribersResponse } from "../../api/analytics";

beforeAll(() => {
  // @ts-expect-error - jsdom polyfill
  global.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

function makeData(
  partial: Partial<SubscribersResponse> = {},
): SubscribersResponse {
  return {
    as_of: "2026-04-29T15:30:00+09:00",
    free_count: 100,
    pro_count: 10,
    blocked_count: 2,
    withdrawn_count: 5,
    pending_cancellation_count: 0,
    pending_cancellations: [],
    ...partial,
  };
}

describe("SubscribersDonut", () => {
  it("4 segment 라벨(무료/Pro/차단/탈퇴) 렌더", () => {
    render(<SubscribersDonut data={makeData()} />);
    // 범례 + KPI 양쪽에 라벨이 등장
    expect(screen.getAllByText("무료").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Pro").length).toBeGreaterThan(0);
    expect(screen.getAllByText("차단").length).toBeGreaterThan(0);
    expect(screen.getAllByText("탈퇴").length).toBeGreaterThan(0);
  });

  it("aria-label에 4 segment 카운트 모두 포함", () => {
    render(<SubscribersDonut data={makeData()} />);
    const region = screen.getByRole("img");
    expect(region.getAttribute("aria-label")).toBe(
      "구독 현황 — 무료 100명, Pro 10명, 차단 2명, 탈퇴 5명",
    );
  });

  it("총합 0 → EmptyState 렌더", () => {
    render(
      <SubscribersDonut
        data={makeData({
          free_count: 0,
          pro_count: 0,
          blocked_count: 0,
          withdrawn_count: 0,
        })}
      />,
    );
    const status = screen.getByRole("status");
    expect(status.textContent).toMatch(/구독 데이터가 없습니다/);
  });

  it("KPICard 4개 — 카운트 표시", () => {
    render(<SubscribersDonut data={makeData()} />);
    expect(screen.getByText("100명")).toBeTruthy();
    expect(screen.getByText("10명")).toBeTruthy();
    expect(screen.getByText("2명")).toBeTruthy();
    expect(screen.getByText("5명")).toBeTruthy();
  });

  it("범례 카운트와 비율(%) 표시", () => {
    render(<SubscribersDonut data={makeData()} />);
    // 100 + 10 + 2 + 5 = 117. free 100 → 85.5%
    expect(screen.getByText(/100명 \(85\.5%\)/)).toBeTruthy();
  });
});
