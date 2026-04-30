import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { BudgetGauge } from "../BudgetGauge";

describe("BudgetGauge", () => {
  it("정상(< 80%) — role=progressbar, aria-valuenow 정확", () => {
    render(<BudgetGauge current={50} max={100} />);
    const gauge = screen.getByRole("progressbar");
    expect(gauge).toBeTruthy();
    expect(gauge.getAttribute("aria-valuenow")).toBe("50");
    expect(gauge.getAttribute("aria-valuemin")).toBe("0");
    expect(gauge.getAttribute("aria-valuemax")).toBe("100");
    expect(gauge.getAttribute("aria-label")).toBe("월 예산 사용률");
  });

  it("정상 상태 — '정상' 텍스트 표시", () => {
    render(<BudgetGauge current={50} max={100} />);
    expect(screen.getByText(/정상/)).toBeTruthy();
  });

  it("80% — '주의' 텍스트 + marker80 렌더", () => {
    const { container } = render(<BudgetGauge current={80} max={100} />);
    expect(screen.getByText(/주의/)).toBeTruthy();
    // marker80 span이 존재해야 함 (state !== normal)
    expect(container.querySelector("[aria-hidden]")).not.toBeNull();
  });

  it("95% — '위험' 텍스트 렌더", () => {
    render(<BudgetGauge current={95} max={100} />);
    expect(screen.getByText(/위험/)).toBeTruthy();
  });

  it("killswitchActive + auto_free_only — '예산 한도 도달' 캡션 표시", () => {
    render(
      <BudgetGauge
        current={100}
        max={100}
        killswitchActive={true}
        killswitchMode="auto_free_only"
      />
    );
    expect(screen.getByText(/예산 한도 도달/)).toBeTruthy();
  });

  it("killswitchActive + manual_total — '수동 비상 정지' 캡션 표시", () => {
    render(
      <BudgetGauge
        current={50}
        max={100}
        killswitchActive={true}
        killswitchMode="manual_total"
      />
    );
    expect(screen.getByText(/수동 비상 정지/)).toBeTruthy();
  });

  it("max=0 — DivisionByZero 없이 0% 표시", () => {
    render(<BudgetGauge current={0} max={0} />);
    expect(screen.getByText(/0\.00%/)).toBeTruthy();
  });
});
