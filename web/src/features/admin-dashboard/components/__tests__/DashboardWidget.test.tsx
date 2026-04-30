import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import {
  DashboardWidget,
  WidgetErrorState,
  WidgetEmptyState,
  WidgetLoadingState,
} from "../DashboardWidget";

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

describe("DashboardWidget shell", () => {
  it("제목과 caption 렌더 + section aria-labelledby", () => {
    const { container } = render(
      <DashboardWidget title="월 예산" caption="이번 달 사용률">
        <div>body</div>
      </DashboardWidget>,
    );
    const section = container.querySelector("section");
    expect(section).not.toBeNull();
    const ariaLabelledBy = section?.getAttribute("aria-labelledby");
    expect(ariaLabelledBy).toBeTruthy();
    const heading = container.querySelector(`#${ariaLabelledBy!}`);
    expect(heading?.textContent).toBe("월 예산");
    expect(screen.getByText("이번 달 사용률")).toBeTruthy();
  });

  it("detailHref 있으면 링크 렌더", () => {
    render(
      <DashboardWidget title="월 예산" detailHref="/admin/dashboard/budget">
        <div>body</div>
      </DashboardWidget>,
    );
    const link = screen.getByRole("link");
    expect(link.getAttribute("href")).toBe("/admin/dashboard/budget");
  });

  it("tone=coming-soon — '준비 중' 배지 표시 + dashed border 클래스", () => {
    const { container } = render(
      <DashboardWidget title="가입자 추이" tone="coming-soon">
        <div>placeholder</div>
      </DashboardWidget>,
    );
    expect(screen.getByText("준비 중")).toBeTruthy();
    expect(container.querySelector("section")?.className).toMatch(/widgetComingSoon/);
  });

  it("tone=coming-soon + detailDisabledTitle — '상세 준비 중' 표시", () => {
    render(
      <DashboardWidget
        title="구독 현황"
        tone="coming-soon"
        detailDisabledTitle="HOLD-PG 이후 활성화"
      >
        <div />
      </DashboardWidget>,
    );
    const disabled = screen.getByText("상세 준비 중");
    expect(disabled.getAttribute("title")).toBe("HOLD-PG 이후 활성화");
    expect(disabled.getAttribute("aria-disabled")).toBe("true");
  });

  it("footnote 렌더", () => {
    render(
      <DashboardWidget title="피드백" footnote="Story 5.4에서 연결">
        <div />
      </DashboardWidget>,
    );
    expect(screen.getByText("Story 5.4에서 연결")).toBeTruthy();
  });
});

describe("Widget state slots", () => {
  it("WidgetLoadingState — role=status + 기본 메시지", () => {
    render(<WidgetLoadingState />);
    const status = screen.getByRole("status");
    expect(status.textContent).toMatch(/로딩 중/);
  });

  it("WidgetErrorState — role=alert + 재시도 버튼 동작", () => {
    const onRetry = vi.fn();
    render(<WidgetErrorState onRetry={onRetry} />);
    expect(screen.getByRole("alert")).toBeTruthy();
    const btn = screen.getByText("다시 시도");
    fireEvent.click(btn);
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("WidgetEmptyState — 메시지 렌더", () => {
    render(<WidgetEmptyState message="이번 기간에 질의 기록이 없습니다." />);
    expect(screen.getByText(/질의 기록이 없습니다/)).toBeTruthy();
  });
});
