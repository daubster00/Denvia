import { describe, it, expect, beforeAll, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { SubscribersDonut } from "../SubscribersDonut";
import type { SubscribersResponse } from "../../api/analytics";

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

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

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

  it("각 segment 클릭 → /admin/users 필터 링크로 이동", () => {
    render(<SubscribersDonut data={makeData()} />);

    // KPI + legend 양쪽에 각 segment 당 1개씩 = 총 2개 링크
    const freeLinks = screen.getAllByLabelText(/무료 사용자 목록 보기/);
    expect(freeLinks.length).toBe(2);
    freeLinks.forEach((el) => {
      expect(el.getAttribute("href")).toBe(
        "/admin/users?subscription_status=free&withdrawn=false",
      );
    });

    const proLinks = screen.getAllByLabelText(/Pro 사용자 목록 보기/);
    proLinks.forEach((el) => {
      expect(el.getAttribute("href")).toBe(
        "/admin/users?subscription_status=pro&withdrawn=false",
      );
    });

    const blockedLinks = screen.getAllByLabelText(/차단 사용자 목록 보기/);
    blockedLinks.forEach((el) => {
      expect(el.getAttribute("href")).toBe(
        "/admin/users?subscription_status=blocked&withdrawn=false",
      );
    });

    const withdrawnLinks = screen.getAllByLabelText(/탈퇴 사용자 목록 보기/);
    withdrawnLinks.forEach((el) => {
      expect(el.getAttribute("href")).toBe("/admin/users?withdrawn=true");
    });
  });
});
