import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { KPICard } from "../KPICard";

describe("KPICard", () => {
  it("label과 value 렌더", () => {
    render(<KPICard label="당월 토큰 비용" value="$ 12.34" />);
    expect(screen.getByText("당월 토큰 비용")).toBeTruthy();
    expect(screen.getByText("$ 12.34")).toBeTruthy();
  });

  it("trend 옵셔널 — 없으면 trend 영역 없음", () => {
    const { container } = render(<KPICard label="라벨" value="값" />);
    // trend dd 없음
    const dds = container.querySelectorAll("dd");
    expect(dds.length).toBe(1);
  });

  it("trend up 방향 표시", () => {
    render(
      <KPICard
        label="라벨"
        value="값"
        trend={{ direction: "up", text: "+5%", tone: "success" }}
      />
    );
    expect(screen.getByText(/▲/)).toBeTruthy();
    expect(screen.getByText(/\+5%/)).toBeTruthy();
  });

  it("onClick 있으면 role=button + 클릭 이벤트", () => {
    const onClick = vi.fn();
    render(<KPICard label="라벨" value="값" onClick={onClick} />);
    const card = screen.getByRole("button");
    expect(card).toBeTruthy();
    fireEvent.click(card);
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("onClick 없으면 role=button 없음", () => {
    render(<KPICard label="라벨" value="값" />);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("dl/dt/dd 시맨틱 구조", () => {
    const { container } = render(<KPICard label="라벨" value="값" />);
    expect(container.querySelector("dl")).not.toBeNull();
    expect(container.querySelector("dt")).not.toBeNull();
    expect(container.querySelector("dd")).not.toBeNull();
  });
});
