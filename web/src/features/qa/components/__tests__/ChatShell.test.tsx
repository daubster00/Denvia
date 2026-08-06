import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { ChatShell } from "../ChatShell";
import { useQAStore } from "@/stores/qa-store";
import { useSessionStore } from "@/stores/session-store";

// Story 2.3: QuotaLock 등 child가 useRouter를 사용하므로 mock 필요
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

beforeEach(() => {
  useQAStore.setState({ messages: [] });
  useSessionStore.setState({ isPopupOpen: false, popupInitialTab: "email" });
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (q: string) => ({
      matches: false,
      media: q,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      onchange: null,
      dispatchEvent: () => false,
    }),
  });
  // jsdom에 scrollIntoView 미정의 — 빈 stub 주입
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (Element.prototype as any).scrollIntoView = vi.fn();
});

const noop = () => {};

describe("ChatShell — hero/inline 자동 전환 (AC-1)", () => {
  it("messages가 0개이면 hero variant 렌더 + 메시지 영역(role=log) 미렌더", () => {
    render(
      <ChatShell
        inputValue=""
        onInputChange={noop}
        onSubmit={noop}
        isStreaming={false}
      />
    );
    expect(screen.getByRole("textbox", { name: "질문 입력" })).toBeDefined();
    expect(screen.queryByRole("log")).toBeNull();
  });

  it("messages가 1개 이상이면 inline variant 렌더 + 메시지 영역 노출", () => {
    useQAStore.setState({
      messages: [
        {
          id: "u1",
          role: "user",
          content: "임플란트 보험 적용 기준?",
          status: "complete",
          timestamp: "2026-04-27T00:00:00.000Z",
        },
      ],
    });
    render(
      <ChatShell
        inputValue=""
        onInputChange={noop}
        onSubmit={noop}
        isStreaming={false}
      />
    );
    expect(screen.getByRole("log", { name: "대화 내역" })).toBeDefined();
    expect(screen.getByText("임플란트 보험 적용 기준?")).toBeDefined();
    expect(screen.getByRole("textbox", { name: "질문 입력" })).toBeDefined();
  });

  it("clearMessages 호출 후 hero variant로 자동 복귀한다 (Story 2.5 reset 연동)", () => {
    useQAStore.setState({
      messages: [
        {
          id: "u1",
          role: "user",
          content: "치주염",
          status: "complete",
          timestamp: "2026-04-27T00:00:00.000Z",
        },
      ],
    });
    const { rerender } = render(
      <ChatShell
        inputValue=""
        onInputChange={noop}
        onSubmit={noop}
        isStreaming={false}
      />
    );
    expect(screen.queryByRole("log")).not.toBeNull();

    // F-306 reset 시뮬레이션
    useQAStore.getState().clearMessages();
    rerender(
      <ChatShell
        inputValue=""
        onInputChange={noop}
        onSubmit={noop}
        isStreaming={false}
      />
    );
    expect(screen.queryByRole("log")).toBeNull();
  });

  it("error 상태의 assistant 메시지에는 onRetry가 전달된다", () => {
    const onRetry = vi.fn();
    useQAStore.setState({
      messages: [
        {
          id: "u1",
          role: "user",
          content: "Q",
          status: "complete",
          timestamp: "2026-04-27T00:00:00.000Z",
        },
        {
          id: "a1",
          role: "assistant",
          content: "임플란트 보험은",
          status: "error",
          errorMessage: "인터넷 연결이 끊겨 답변이 중단됐어요. 다시 시도해 주세요.",
          timestamp: "2026-04-27T00:00:00.000Z",
        },
      ],
    });
    render(
      <ChatShell
        inputValue=""
        onInputChange={noop}
        onSubmit={noop}
        isStreaming={false}
        onRetry={onRetry}
      />
    );
    const retryBtn = screen.getByRole("button", { name: "다시 시도" });
    retryBtn.click();
    expect(onRetry).toHaveBeenCalled();
  });
});
