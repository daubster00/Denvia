import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ChatInput } from "../ChatInput";
import { useSessionStore } from "@/stores/session-store";
import { useAlertStore } from "@/stores/alert-store";

// matchMedia 기본 모킹 — 데스크톱 가정 (자동 포커스 허용)
beforeEach(() => {
  useSessionStore.setState({ isPopupOpen: false, popupInitialTab: "email" });
  useAlertStore.setState({ current: null });
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

describe("ChatInput — blockedUntil (관리자 차단)", () => {
  it("UI는 평소와 동일(placeholder=무엇이든 물어보세요)하지만 클릭(mousedown) 시 차단 안내 모달이 뜬다", () => {
    const future = new Date(Date.now() + 60 * 60 * 1000).toISOString();
    render(
      <ChatInput
        variant="inline"
        value=""
        blockedUntil={future}
        blockReason="이상 질문 패턴이 감지되었습니다."
      />,
    );
    const input = screen.getByRole("textbox", { name: "질문 입력 — 일시 제한" });
    expect(input.hasAttribute("readonly")).toBe(true);
    expect((input as HTMLTextAreaElement).placeholder).toBe("무엇이든 물어보세요");
    fireEvent.mouseDown(input);
    const alert = useAlertStore.getState().current;
    expect(alert?.title).toContain("일시 제한");
    expect(alert?.description ?? "").toContain("이상 질문 패턴");
    expect(alert?.description ?? "").toContain("해제 예정\n");
  });

  it("hero interactive 모드라도 차단 시 잠금 입력으로 덮어쓴다", () => {
    const future = new Date(Date.now() + 60 * 60 * 1000).toISOString();
    render(
      <ChatInput
        variant="hero"
        interactive
        value=""
        blockedUntil={future}
        blockReason={null}
      />,
    );
    expect(
      screen.getByRole("textbox", { name: "질문 입력 — 일시 제한" }),
    ).toBeTruthy();
  });

  it("과거 시각(만료)이면 차단을 적용하지 않는다", () => {
    const past = new Date(Date.now() - 60 * 1000).toISOString();
    render(
      <ChatInput
        variant="inline"
        value=""
        blockedUntil={past}
        blockReason="만료된 차단"
      />,
    );
    expect(screen.getByRole("textbox", { name: "질문 입력" })).toBeTruthy();
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
