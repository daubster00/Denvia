/**
 * ChatMessage reframe 통합 테스트 — Story 2.6
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ChatMessage } from "../ChatMessage";
import type { QAMessage } from "@/stores/qa-store";

// AnswerFeedback이 useQuery를 사용하므로 mock
vi.mock("@/features/qa/api/qa-feedback", () => ({
  submitFeedback: vi.fn(),
}));

vi.mock("@tanstack/react-query", async () => {
  const actual = await vi.importActual("@tanstack/react-query");
  return {
    ...actual,
    useMutation: () => ({ mutate: vi.fn(), isPending: false }),
  };
});

function makeAssistantMsg(overrides?: Partial<QAMessage>): QAMessage {
  return {
    id: "asst-1",
    role: "assistant",
    content: "기본 답변 내용입니다.",
    status: "complete",
    timestamp: "2026-01-01T00:00:00.000Z",
    ...overrides,
  };
}

describe("ChatMessage — reframe 통합 (Story 2.6)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("reframe이 없으면 QuestionReFrame 컴포넌트가 렌더되지 않는다", () => {
    const msg = makeAssistantMsg();
    const onPickReframeOption = vi.fn();
    render(<ChatMessage message={msg} onPickReframeOption={onPickReframeOption} />);
    // QuestionReFrame의 헤드라인이 없어야 함
    expect(screen.queryByText("새 질문에 포함해보세요")).toBeNull();
  });

  it("message.reframe != null + onPickReframeOption 있으면 QuestionReFrame이 렌더된다", () => {
    const msg = makeAssistantMsg({
      content: "어느 치아인지 알려주세요?",
      reframe: {
        followUpQuestion: "어느 치아인지 알려주세요?",
        options: ["상악 전치", "하악 구치", "어금니"],
      },
    });
    const onPickReframeOption = vi.fn();
    render(<ChatMessage message={msg} onPickReframeOption={onPickReframeOption} />);
    expect(screen.getByText("새 질문에 포함해보세요")).toBeDefined();
    expect(screen.getByRole("button", { name: /상악 전치/ })).toBeDefined();
  });

  it("message.content(<p>)가 followUpQuestion을 1회만 표시한다 (중복 렌더 금지)", () => {
    const followUpQuestion = "어느 치아인지 알려주세요?";
    const msg = makeAssistantMsg({
      content: followUpQuestion,
      reframe: {
        followUpQuestion,
        options: ["상악 전치", "하악 구치", "어금니"],
      },
    });
    const onPickReframeOption = vi.fn();
    const { container } = render(
      <ChatMessage message={msg} onPickReframeOption={onPickReframeOption} />
    );
    // <p> 태그에서 followUpQuestion이 1회만 표시되어야 함
    const paragraphs = container.querySelectorAll("p");
    const matchingP = Array.from(paragraphs).filter((p) =>
      p.textContent === followUpQuestion
    );
    expect(matchingP).toHaveLength(1);
  });

  it("onPickReframeOption이 없으면 reframe이 있어도 QuestionReFrame이 렌더되지 않는다", () => {
    const msg = makeAssistantMsg({
      reframe: {
        followUpQuestion: "어느 치아인지?",
        options: ["상악 전치", "하악 구치", "어금니"],
      },
    });
    render(<ChatMessage message={msg} />);
    // onPickReframeOption prop 미전달 → QuestionReFrame 미렌더
    expect(screen.queryByText("새 질문에 포함해보세요")).toBeNull();
  });

  it("chip 클릭 시 onPickReframeOption이 option값으로 호출된다", () => {
    const msg = makeAssistantMsg({
      content: "어느 치아인지?",
      reframe: {
        followUpQuestion: "어느 치아인지?",
        options: ["상악 전치", "하악 구치", "어금니"],
      },
    });
    const onPickReframeOption = vi.fn();
    render(<ChatMessage message={msg} onPickReframeOption={onPickReframeOption} />);
    const btn = screen.getByRole("button", { name: /상악 전치/ });
    fireEvent.click(btn);
    expect(onPickReframeOption).toHaveBeenCalledWith("상악 전치");
  });
});
