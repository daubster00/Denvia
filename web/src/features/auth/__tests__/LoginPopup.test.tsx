import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("@/features/auth/api", () => ({
  fetchMe: vi.fn(),
  requestPasswordReset: vi.fn(),
  sendSmsOtp: vi.fn(),
  verifySmsOtp: vi.fn(),
  lookupId: vi.fn(),
}));
import { LoginPopup } from "../LoginPopup";
import { useSessionStore } from "@/stores/session-store";

// jsdom 한계: sessionStorage 모킹
const mockStorage: Record<string, string> = {};
Object.defineProperty(window, "sessionStorage", {
  value: {
    getItem: (k: string) => mockStorage[k] ?? null,
    setItem: (k: string, v: string) => { mockStorage[k] = v; },
    removeItem: (k: string) => { delete mockStorage[k]; },
    clear: () => { Object.keys(mockStorage).forEach(k => delete mockStorage[k]); },
  },
  writable: true,
});

// matchMedia 모킹
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => {},
  }),
});

beforeEach(() => {
  useSessionStore.setState({ isPopupOpen: true, popupInitialTab: "email" });
  Object.keys(mockStorage).forEach(k => delete mockStorage[k]);
});

describe("LoginPopup", () => {
  it("이메일 탭에서 첫 렌더 시 이메일 input이 존재한다", () => {
    render(<LoginPopup />);
    expect(screen.getByLabelText(/이메일/i)).toBeDefined();
  });

  it("ESC 키로 팝업이 닫힌다", async () => {
    render(<LoginPopup />);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(useSessionStore.getState().isPopupOpen).toBe(false);
  });

  it("배경 클릭은 팝업을 닫지 않는다 (UX Spec §1439)", () => {
    render(<LoginPopup />);
    // 배경(aria-hidden overlay)은 onClick 없음
    const overlay = document.querySelector('[aria-hidden="true"]') as HTMLElement;
    expect(overlay).toBeTruthy();
    fireEvent.click(overlay);
    // 닫힘이 트리거되지 않아야 함
    expect(useSessionStore.getState().isPopupOpen).toBe(true);
  });

  it("닫기(X) 버튼 클릭 시 closePopup이 호출된다", async () => {
    const user = userEvent.setup();
    render(<LoginPopup />);
    const closeBtn = screen.getByRole("button", { name: /팝업 닫기/i });
    await user.click(closeBtn);
    expect(useSessionStore.getState().isPopupOpen).toBe(false);
  });

  it("초기 버튼 뷰에서 소셜 로그인 버튼들이 표시된다", () => {
    render(<LoginPopup />);
    expect(screen.getByRole("button", { name: /카카오로 로그인/i })).toBeDefined();
    expect(screen.getByRole("button", { name: /네이버로 로그인/i })).toBeDefined();
    expect(screen.getByRole("button", { name: /구글로 로그인/i })).toBeDefined();
  });

  it("dialog role + aria-modal + aria-labelledby가 올바르다", () => {
    render(<LoginPopup />);
    const dialog = screen.getByRole("dialog");
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(dialog.getAttribute("aria-labelledby")).toBe("login-popup-title");
  });

  it("이메일 로그인 탭 → 비밀번호 찾기 버튼 클릭 → find-password 뷰로 전환", async () => {
    const user = userEvent.setup();
    render(<LoginPopup />);

    // 이메일 로그인 탭 진입
    const emailBtn = screen.getByRole("button", { name: /이메일로 로그인/i });
    await user.click(emailBtn);

    // 비밀번호 찾기 버튼 클릭
    const findPwBtn = screen.getByRole("button", { name: /비밀번호 찾기/i });
    await user.click(findPwBtn);

    // find-password 뷰: 타이틀 변경 확인
    expect(screen.getByText("비밀번호 찾기")).toBeTruthy();
    expect(screen.getByText("임시 비밀번호 받기")).toBeTruthy();
  });

  it("이메일 로그인 탭 → 아이디 찾기 버튼 클릭 → find-id 뷰로 전환", async () => {
    const user = userEvent.setup();
    render(<LoginPopup />);

    const emailBtn = screen.getByRole("button", { name: /이메일로 로그인/i });
    await user.click(emailBtn);

    const findIdBtn = screen.getByRole("button", { name: /아이디 찾기/i });
    await user.click(findIdBtn);

    expect(screen.getByText("아이디 찾기")).toBeTruthy();
    expect(screen.getByText("인증번호 전송")).toBeTruthy();
  });

  it("find-password 뷰의 ← 버튼으로 이메일 로그인 뷰로 복귀", async () => {
    const user = userEvent.setup();
    render(<LoginPopup />);

    await user.click(screen.getByRole("button", { name: /이메일로 로그인/i }));
    await user.click(screen.getByRole("button", { name: /비밀번호 찾기/i }));

    // 뒤로가기
    await user.click(screen.getByRole("button", { name: /이전 화면으로/i }));
    expect(screen.getByText("이메일로 로그인")).toBeTruthy();
  });
});
