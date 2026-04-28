import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QuestionReFrame } from "../QuestionReFrame";

describe("QuestionReFrame", () => {
  const defaultOptions = ["상악 전치", "하악 구치", "어금니"];

  it("Section message 헤드라인이 렌더된다", () => {
    const onPickOption = vi.fn();
    render(<QuestionReFrame options={defaultOptions} onPickOption={onPickOption} />);
    expect(screen.getByText("정보가 조금 더 필요해요")).toBeDefined();
  });

  it("3개 chip 버튼이 렌더된다", () => {
    const onPickOption = vi.fn();
    render(<QuestionReFrame options={defaultOptions} onPickOption={onPickOption} />);
    for (const opt of defaultOptions) {
      expect(screen.getByRole("button", { name: new RegExp(opt) })).toBeDefined();
    }
  });

  it("4개 옵션 케이스에서 4개 chip 버튼이 렌더된다", () => {
    const options4 = ["상악 전치", "하악 구치", "어금니", "사랑니"];
    const onPickOption = vi.fn();
    render(<QuestionReFrame options={options4} onPickOption={onPickOption} />);
    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(4);
  });

  it("각 chip의 aria-label이 올바르게 설정된다", () => {
    const onPickOption = vi.fn();
    render(<QuestionReFrame options={defaultOptions} onPickOption={onPickOption} />);
    for (const opt of defaultOptions) {
      expect(
        screen.getByRole("button", { name: `이 후속 질문으로 다시 물어보기: ${opt}` })
      ).toBeDefined();
    }
  });

  it("컨테이너에 role='status' + aria-live='polite'가 있다 (a11y)", () => {
    const onPickOption = vi.fn();
    const { container } = render(<QuestionReFrame options={defaultOptions} onPickOption={onPickOption} />);
    const statusDiv = container.querySelector("[role='status']");
    expect(statusDiv).not.toBeNull();
    expect(statusDiv?.getAttribute("aria-live")).toBe("polite");
  });

  it("chip 클릭 시 onPickOption(option)이 호출된다", () => {
    const onPickOption = vi.fn();
    render(<QuestionReFrame options={defaultOptions} onPickOption={onPickOption} />);
    const firstBtn = screen.getByRole("button", { name: new RegExp(defaultOptions[0]) });
    fireEvent.click(firstBtn);
    expect(onPickOption).toHaveBeenCalledWith(defaultOptions[0]);
    expect(onPickOption).toHaveBeenCalledTimes(1);
  });

  it("follow_up_question 본문이 컴포넌트 내부에 렌더되지 않는다 (UI/DB SoT 보장)", () => {
    // QuestionReFrame은 followUpQuestion prop 자체가 없음 — 본문은 ChatMessage <p>가 단독 표시
    const onPickOption = vi.fn();
    const { container } = render(
      <QuestionReFrame options={defaultOptions} onPickOption={onPickOption} />
    );
    // 컴포넌트가 받지 않은 follow_up_question 텍스트가 DOM에 노출되면 안 됨
    // (followUpQuestion prop이 없으므로 이 검증은 props 인터페이스 설계 확인)
    expect(container.querySelectorAll("p")).toHaveLength(0);
  });
});
