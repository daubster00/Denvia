import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ChatInput } from "../ChatInput";
import { useSessionStore } from "@/stores/session-store";

// matchMedia 기본 모킹 — 데스크톱 가정 (자동 포커스 허용)
beforeEach(() => {
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
});

describe("ChatInput — hero variant + interactive=false (비로그인 readonly)", () => {
  it("readonly input이 렌더되고 클릭 시 로그인 팝업이 오픈된다", () => {
    render(<ChatInput variant="hero" />);
    const input = screen.getByRole("textbox", {
      name: "질문 입력 — 로그인 후 이용 가능",
    });
    expect(input.hasAttribute("readonly")).toBe(true);
    fireEvent.click(input);
    expect(useSessionStore.getState().isPopupOpen).toBe(true);
  });

  it("interactive prop을 명시하지 않으면 default false로 readonly 동작 보존된다", () => {
    render(<ChatInput variant="hero" />);
    const input = screen.getByRole("textbox", {
      name: "질문 입력 — 로그인 후 이용 가능",
    });
    expect(input.hasAttribute("readonly")).toBe(true);
  });
});

describe("ChatInput — hero variant + interactive=true (로그인 후 활성)", () => {
  it("readonly가 제거되고 onChange가 동작한다", () => {
    const onChange = vi.fn();
    render(
      <ChatInput
        variant="hero"
        interactive
        value=""
        onChange={onChange}
      />
    );
    const textarea = screen.getByRole("textbox", { name: "질문 입력" });
    expect(textarea.hasAttribute("readonly")).toBe(false);
    fireEvent.change(textarea, { target: { value: "임플란트" } });
    expect(onChange).toHaveBeenCalledWith("임플란트");
  });

  it("Enter 입력 시 onSubmit이 호출되고 로그인 팝업은 열리지 않는다", () => {
    const onSubmit = vi.fn();
    render(
      <ChatInput
        variant="hero"
        interactive
        value="치주염 치료"
        onSubmit={onSubmit}
      />
    );
    const textarea = screen.getByRole("textbox", { name: "질문 입력" });
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false });
    expect(onSubmit).toHaveBeenCalledWith("치주염 치료");
    expect(useSessionStore.getState().isPopupOpen).toBe(false);
  });
});

describe("ChatInput — inline variant (활성 textarea)", () => {
  it("Shift+Enter는 전송하지 않는다", () => {
    const onSubmit = vi.fn();
    render(<ChatInput variant="inline" value="줄바꿈" onSubmit={onSubmit} />);
    const textarea = screen.getByRole("textbox", { name: "질문 입력" });
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: true });
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("loading=true이면 Enter 전송이 차단된다", () => {
    const onSubmit = vi.fn();
    render(
      <ChatInput
        variant="inline"
        value="질문"
        onSubmit={onSubmit}
        loading
      />
    );
    const textarea = screen.getByRole("textbox", { name: "질문 입력" });
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false });
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
