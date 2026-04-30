import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { DashboardChart } from "../DashboardChart";

// Recharts uses ResizeObserver which jsdom does not provide; stub it.
beforeAll(() => {
  // @ts-expect-error - jsdom polyfill
  global.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

describe("DashboardChart", () => {
  it("data 비어있음 → emptyMessage + role=img + aria-label", () => {
    render(
      <DashboardChart
        variant="line"
        data={[]}
        series={[{ key: "value", label: "값", tone: "brand" }]}
        ariaLabel="테스트 차트"
        emptyMessage="표시할 항목이 없습니다."
      />,
    );
    const region = screen.getByRole("img", { name: "테스트 차트" });
    expect(region).toBeTruthy();
    expect(screen.getByText("표시할 항목이 없습니다.")).toBeTruthy();
  });

  it("data 있음 + line variant → ResponsiveContainer 영역 + 범례 라벨", () => {
    const data = [
      { name: "1월", value: 10 },
      { name: "2월", value: 12 },
    ];
    render(
      <DashboardChart
        variant="line"
        data={data}
        series={[{ key: "value", label: "월별 수치", tone: "success" }]}
        ariaLabel="월별 추이"
      />,
    );
    expect(screen.getByRole("img", { name: "월별 추이" })).toBeTruthy();
    expect(screen.getByText("월별 수치")).toBeTruthy();
  });

  it("기본 emptyMessage 사용", () => {
    render(
      <DashboardChart
        variant="bar"
        data={[]}
        series={[{ key: "v", label: "값" }]}
        ariaLabel="빈 차트"
      />,
    );
    expect(screen.getByText("표시할 데이터가 없습니다.")).toBeTruthy();
  });

  it("variant=donut data 있을 때 렌더 (예외 없이)", () => {
    const data = [
      { name: "A", value: 1 },
      { name: "B", value: 2 },
    ];
    expect(() =>
      render(
        <DashboardChart
          variant="donut"
          data={data}
          series={[
            { key: "value", label: "A", tone: "brand" },
            { key: "value", label: "B", tone: "warning" },
          ]}
          ariaLabel="구독 비율"
        />,
      ),
    ).not.toThrow();
  });
});

// suppress unused-vi import warning if any
void vi;
