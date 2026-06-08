import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { AnomalyTabs } from "../components/AnomalyTabs";

describe("AnomalyTabs", () => {
  it("renders 7 tabs (전체 + 6종)", () => {
    render(<AnomalyTabs activeType={null} onChange={() => {}} />);
    expect(screen.getByRole("tab", { name: "전체" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "로그인 무차별 시도" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "복수 IP 동시 로그인" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "반복 질의" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "계정 복구 남용" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "답변 직후 연속 질의" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "휴대폰 인증 남용" })).toBeTruthy();
  });

  it("marks active tab with aria-selected=true", () => {
    render(
      <AnomalyTabs activeType="rapid_followup_questions" onChange={() => {}} />,
    );
    const activeTab = screen.getByRole("tab", { name: "답변 직후 연속 질의" });
    expect(activeTab.getAttribute("aria-selected")).toBe("true");
    const inactive = screen.getByRole("tab", { name: "전체" });
    expect(inactive.getAttribute("aria-selected")).toBe("false");
  });

  it("invokes onChange with the clicked type", () => {
    const onChange = vi.fn();
    render(<AnomalyTabs activeType={null} onChange={onChange} />);
    fireEvent.click(screen.getByRole("tab", { name: "반복 질의" }));
    expect(onChange).toHaveBeenCalledWith("repeated_question");
  });

  it("invokes onChange(null) when 전체 clicked", () => {
    const onChange = vi.fn();
    render(
      <AnomalyTabs
        activeType="rapid_followup_questions"
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByRole("tab", { name: "전체" }));
    expect(onChange).toHaveBeenCalledWith(null);
  });
});
